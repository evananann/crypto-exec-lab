"""Trace a pre-study exploratory abstention to archived wire messages and cash."""
from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

from research.decision_study.historical import load_quotes
from research.decision_study.pipeline import Config, Replay, digest
from scripts.successor_recorder import normalize

ROOT = Path(__file__).resolve().parents[2]


def build(cache, out):
    trial = json.loads((ROOT/'reports/prepared_cohort_20261022/verification.json').read_text())['trials'][0]
    run_id = trial['run_id']
    archive = cache/f'rehearsal-{run_id}-1.tar.gz'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != trial['archive_sha256']:
        raise ValueError('unapproved historical archive')
    restored = cache/f'{run_id}-validated'
    with tarfile.open(archive) as tar:
        checksums = json.load(tar.extractfile('checksums.json'))
    for name, sha in checksums.items():
        if Path(name).name != name or hashlib.sha256((restored/name).read_bytes()).hexdigest() != sha:
            raise ValueError('restored member differs from authenticated archive')
    config = Config(**json.loads((ROOT/'research/decision_study/historical_plan.json').read_text())['config'])
    tapes, _ = load_quotes(restored)
    replay = Replay(tapes['okx'], tapes['binance'], config)
    start = max(t[0].time_ms for t in tapes.values()) + config.lookback_ms
    time = ((start + 9999)//10000)*10000
    opportunities = [(str(run_id)+'-'+str(time), time)]
    ledger = replay.ledgers(opportunities)
    replay.audit(opportunities, ledger)
    if any(row['status'] != 'ABSTAIN' for row in ledger):
        raise ValueError('this trace is specified for the first historical abstention')
    features = []
    for venue, rawvenue in [('follower', 'okx'), ('leader', 'binance')]:
        for at in (time-config.lookback_ms, time):
            quote = replay.quote(venue, at)
            features.append(dict(venue=rawvenue, queried_at_ms=at, quote=asdict(quote)))
    selected = {}
    with (restored/'events.jsonl').open() as stream:
        for index, line in enumerate(stream):
            event = json.loads(line)
            for feature in features:
                quote = feature['quote']
                if (event['kind']=='bbo' and event['venue']==feature['venue']
                        and event['local_ts']==quote['time_ms']):
                    # Last received record in a millisecond is the frozen pilot convention.
                    feature['event_index'] = index
                    selected[index] = event
    wanted = {f['event_index'] for f in features}
    selected = {i: selected[i] for i in wanted}
    provenance = {}
    with (restored/'provenance.jsonl').open() as stream:
        for index, line in enumerate(stream):
            if index in wanted:
                provenance[index] = json.loads(line)
    factor = json.loads((restored/'instruments.jsonl').read_text().splitlines()[0])['factor_btc']
    wires = {}
    event_index = 0
    with (restored/'wire.jsonl').open() as stream:
        for wire_index, line in enumerate(stream):
            wire = json.loads(line)
            for event, source in normalize(wire['payload'], wire['local_ts'], wire['venue'], factor):
                if event_index in wanted:
                    if event.to_dict() != selected[event_index]:
                        raise ValueError('wire reparse differs from selected event')
                    if provenance[event_index]['connection_id'] != wire['connection_id']:
                        raise ValueError('connection provenance differs')
                    wires[event_index] = dict(wire_index=wire_index, wire=wire,
                                               exchange_timestamp_source=source)
                event_index += 1
            if len(wires)==len(wanted):
                break
    if set(wires)!=wanted:
        raise ValueError('missing raw packet')
    for feature in features:
        event = selected[feature['event_index']]
        if str(event['bid']) != feature['quote']['bid'] or str(event['ask']) != feature['quote']['ask']:
            raise ValueError('feature does not equal last received quote')
    result = dict(schema_version=1, evidence='real pre-study exploratory abstention; not a successor result',
                  original_run_id=run_id, archive_sha256=trial['archive_sha256'],
                  collector_source_commit=trial['source_commit'], member_sha256=checksums,
                  config=asdict(config), features=features,
                  events=[dict(event_index=i, event=selected[i], provenance=provenance[i], **wires[i]) for i in sorted(wanted)],
                  ledger=ledger, ledger_sha256=digest(ledger),
                  accounting=dict(orders=0, fills=0, gross_usd='0', fees_usd='0', net_usd='0', turnover_usd='0', residual_btc='0'),
                  limitation='No trade occurred. No confidence interval, execution calibration or successor eligibility is inferred.')
    out.write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    build(a.cache,a.out)
