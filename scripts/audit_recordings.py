"""Read-only normalized-recording integrity audit. Health only; no markouts."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from cel.artifacts import file_sha256
from cel.ingest.instruments import contract_value_btc
from cel.ingest.jsonl import iter_events
from cel.ingest.replay import replay_list
from cel.study import load_plan, restore_archive, verify_archive, verify_directory
from scripts.study_monitor import PLANS


def audit(directory, plan_path):
    manifest = verify_directory(directory,plan_path)
    plan, _ = load_plan(plan_path)
    tape = directory/'tape.jsonl'
    if not tape.exists():
        return {'session':manifest['session_id'],'status':manifest['status'],'tape_available':False}
    before = file_sha256(tape)
    events = list(iter_events(tape))
    replayed, replay = replay_list(tape)
    counts = Counter(e.venue for e in events)
    kinds = Counter(e.kind for e in events)
    timestamps, quote_times, equal_clocks = defaultdict(list), defaultdict(list), Counter()
    for event in events:
        timestamps[event.venue].append(event.local_ts)
        if event.kind=='bbo':
            quote_times[event.venue].append(event.local_ts)
        equal_clocks[event.venue] += event.local_ts == event.exchange_ts
    metadata_paths = list(directory.glob('*.meta.json'))
    if len(metadata_paths)>1:
        raise ValueError('ambiguous recorder metadata')
    metadata = json.loads(metadata_paths[0].read_text()) if metadata_paths else None
    reconciliation = None
    if metadata is not None:
        reconciliation = {'total_matches':metadata['events']==len(events) if 'events' in metadata else None,
                          'venue_counts_match':metadata['by_venue']==dict(counts) if 'by_venue' in metadata else None,
                          'kind_counts_match':metadata['by_kind']==dict(kinds) if 'by_kind' in metadata else None}
    instrument = None
    if (directory/'instrument.json').exists():
        value = contract_value_btc(json.loads((directory/'instrument.json').read_text()))
        instrument = {'verified_btc_per_contract':value,
                      'manifest_conversion_matches':value==manifest.get('verified_contract_value_btc'),
                      'temporal_stability':'unverified: one archived metadata snapshot cannot establish whole-session stability'}
    def stats(values):
        return {'events':len(values), 'equal_timestamp_neighbors':sum(a==b for a,b in zip(values,values[1:])),
                'timestamp_regressions':sum(b<a for a,b in zip(values,values[1:])),
                'maximum_forward_gap_ms':max((b-a for a,b in zip(values,values[1:])),default=None)}
    if file_sha256(tape)!=before:
        raise ValueError('recording changed during audit')
    return {'session':manifest['session_id'],'phase':manifest['phase'],'status':manifest['status'],
            'tape_available':True,'input_sha256':before,'raw_normalized_events':len(events),
            'replayed_events':len(replayed),'duplicate_trades_removed':replay.duplicate_trades_dropped,
            'replay_count_matches':len(replayed)+replay.duplicate_trades_dropped==len(events),
            'recorder_count_reconciliation':reconciliation,'clock_metrics':{v:stats(t) for v,t in timestamps.items()},
            'bbo_clock_metrics':{v:stats(t) for v,t in quote_times.items()},
            'exchange_equals_local_count':dict(equal_clocks),
            'fallback_provenance':'unknown: equal clock values can be true equality or fallback; no per-row fallback flag exists',
            'quantity_units':dict(Counter(e.quantity_unit for e in events)),
            'reconnect_observation':{'opened_counts':metadata.get('opened',{}) if metadata else None,
                'segment_assignment':'unavailable: normalized rows do not carry connection/session IDs'},
            'instrument':instrument,
            'pair':plan['leader']+'->'+plan['follower'],
            'scope':'Recorded counters and clock symptoms; no latency, outage, complete coverage or profitable execution inference.'}


def inspect(source):
    known = {}
    for path in PLANS:
        load_plan(path)
        known[file_sha256(path)] = path
    rows = []
    for archive in sorted(source.rglob('*.tar.gz')):
        item = verify_archive(archive)
        if item['plan_sha256'] not in known:
            raise ValueError('unknown frozen plan')
        with tempfile.TemporaryDirectory(prefix='recording-integrity-') as temp:
            restored = restore_archive(archive,Path(temp))
            rows.append({'archive_sha256':file_sha256(archive),**audit(restored,known[item['plan_sha256']])})
    if not rows:
        raise ValueError('no archived recordings')
    return {'schema_version':1,'as_of_utc':datetime.now(timezone.utc).isoformat(), 'recordings':rows,
            'outcomes_evaluated':False,'limitations':['Original websocket payloads are not preserved.',
            'Connection segmentation, timestamp fallback identity and intraday metadata stability cannot be reconstructed from absent fields.',
            'Original statuses are retained; this diagnostic does not upgrade preflights or repair missing data.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    if args.out.exists() or args.out.resolve().is_relative_to(args.source.resolve()):
        parser.error('choose a new output file outside the evidence source')
    result = inspect(args.source)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(f'Audited {len(result["recordings"])} archived recordings; no outcomes evaluated')


if __name__=='__main__':
    main()
