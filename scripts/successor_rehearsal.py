"""Source-bound successor infrastructure rehearsal and independent archive restore.

This does not collect a frozen v1/v2 observation or estimate any market outcome.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

from cel.ingest.instruments import contract_value_btc
from cel.ingest.schema import Event
from scripts.successor_claim import api, canonical, instant, verify_claim
from scripts.successor_recorder import InstrumentSampler, ProvenanceRecorder, normalize, specification

PROTOCOL = Path('configs/successor/protocol.json')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def source_identity():
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], text=True).strip():
        raise ValueError('clean committed source required for a live rehearsal')
    files = sorted([*Path('cel').rglob('*.py'), *Path('scripts').glob('successor_*.py'),
                    PROTOCOL, Path('uv.lock'), Path('.github/workflows/successor-rehearsal.yml')])
    return {'commit': revision, 'dirty': False, 'files_sha256': {str(p): digest(p) for p in files}}


def gate(protocol, intended_start, now, mode):
    intended, current = instant(intended_start), instant(now)
    delay = (current - intended).total_seconds()
    if mode not in ('transport_only', 'prospective'):
        raise ValueError('unknown rehearsal mode')
    allowed = mode == 'transport_only' or 0 <= delay <= protocol['maximum_start_lateness_seconds']
    return {'accepted': allowed, 'mode': mode, 'intended_start_utc': intended.isoformat(),
            'checked_at_utc': current.isoformat(), 'lateness_seconds': delay,
            'timing_qualified': mode == 'prospective' and allowed}


def json_rows(path):
    if not path.exists():
        return
    with path.open() as stream:
        for line in stream:
            yield json.loads(line)


def assess(directory):
    """Recompute provenance and health from restored bytes, not producer success flags."""
    protocol = json.loads((directory / 'protocol.json').read_text())
    manifest = json.loads((directory / 'manifest.json').read_text())
    issues = []
    if manifest['requested_seconds'] != protocol['recording_seconds']:
        issues.append('duration request differs from protocol')
    if manifest.get('collection_error_category'):
        issues.append('collector did not complete')
    record = json.loads((directory / 'recorder.json').read_text()) if (directory / 'recorder.json').exists() else {}
    duration = record.get('duration_seconds', 0)
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < protocol['recording_seconds']:
        issues.append('recorded duration insufficient')
    if record.get('workers_still_running'):
        issues.append('recorder workers still running')
    event_path, provenance_path = directory / 'events.jsonl', directory / 'provenance.jsonl'
    events = [Event.from_dict(row) for row in json_rows(event_path)]
    provenance = list(json_rows(provenance_path))
    connections = json.loads((directory / 'connections.json').read_text()) if (directory / 'connections.json').exists() else {}
    if any(connections.get('parse_errors', {}).values()):
        issues.append('message parse or persistence errors')
    connection_ids = {item['connection_id']: item['venue'] for item in connections.get('connections', [])}
    if len(connection_ids) != len(connections.get('connections', [])):
        issues.append('duplicate connection identity')
    if len(events) != len(provenance) or record.get('events') != len(events):
        issues.append('event/provenance/recorder count mismatch')
    fallback = 0
    for index, (event, row) in enumerate(zip(events, provenance)):
        if (row.get('event_index') != index or row.get('venue') != event.venue or
                connection_ids.get(row.get('connection_id')) != event.venue or
                row.get('timestamp_fallback') is not (row.get('exchange_timestamp_source') == 'local_receive')):
            issues.append('event provenance identity mismatch')
            break
        if row['timestamp_fallback']:
            fallback += 1
    if fallback:
        issues.append('exchange timestamp fallback observed')
    snapshots = list(json_rows(directory / 'instruments.jsonl'))
    specs, factors, stamps = [], [], []
    for item in snapshots:
        if 'payload' not in item:
            issues.append('instrument snapshot unavailable')
            continue
        factors.append(contract_value_btc(item['payload']))
        specs.append(specification(item['payload']))
        stamps.append(instant(item['observed_at_utc']))
    if len(specs) < 3 or any(spec != specs[0] for spec in specs):
        issues.append('instrument snapshots insufficient or specification changed')
    if stamps:
        gaps = [(b-a).total_seconds() for a,b in zip(stamps, stamps[1:])]
        if any(gap < 0 or gap > protocol['metadata_interval_seconds'] + 30 for gap in gaps):
            issues.append('instrument sampling gap')
        if (stamps[-1]-stamps[0]).total_seconds() < protocol['recording_seconds']:
            issues.append('instrument snapshots do not span recording')
    # Reparse actual wire payloads independently and compare exact event/provenance sequence.
    wire_events, wire_provenance = [], []
    if factors and (directory / 'wire.jsonl').exists():
        for row in json_rows(directory / 'wire.jsonl'):
            if connection_ids.get(row['connection_id']) != row['venue']:
                issues.append('unknown wire connection')
                break
            for event, source in normalize(row['payload'], row['local_ts'], row['venue'], factors[0]):
                wire_events.append(event.to_dict())
                wire_provenance.append({'event_index': len(wire_events)-1, 'venue': event.venue,
                    'connection_id': row['connection_id'], 'exchange_timestamp_source': source,
                    'timestamp_fallback': source == 'local_receive'})
        if wire_events != [e.to_dict() for e in events] or wire_provenance != provenance:
            issues.append('wire/event/provenance reparse mismatch')
    else:
        issues.append('wire reparse unavailable')
    venues = {}
    for venue in protocol['pair']:
        bbo = [e for e in events if e.venue == venue and e.kind == 'bbo']
        times = [e.local_ts for e in bbo]
        span = times[-1]-times[0] if len(times) >= 2 else 0
        gaps = [b-a for a,b in zip(times, times[1:])]
        venues[venue] = {'bbo': len(bbo), 'span_ms': span, 'maximum_gap_ms': max(gaps, default=None)}
        if span < protocol['recording_seconds'] * 1000 * protocol['minimum_span_fraction']:
            issues.append(venue + ': insufficient quote span')
        if not gaps or min(gaps) < 0 or max(gaps) > protocol['maximum_bbo_silence_ms']:
            issues.append(venue + ': quote gap or timestamp regression')
        if any(e.quantity_unit != 'BTC' for e in bbo):
            issues.append(venue + ': unknown quantity units')
    timing = gate(protocol, manifest['intended_start_utc'], manifest['collector_started_at_utc'], manifest['mode'])
    return {'collection_healthy': not issues, 'issues': sorted(set(issues)), 'events': len(events),
            'timestamp_fallback_events': fallback, 'instrument_snapshots': len(snapshots),
            'venues': venues, 'timing': timing, 'study_observation': False,
            'scope': 'Infrastructure rehearsal only; sampled metadata cannot prove stability between snapshots.'}


def pack(directory, archive):
    files = {p.name: digest(p) for p in directory.iterdir() if p.is_file()}
    if any(p.is_dir() for p in directory.iterdir()):
        raise ValueError('nested package member')
    write(directory / 'checksums.json', files)
    with archive.open('xb') as target, tarfile.open(fileobj=target, mode='w:gz') as tar:
        for path in sorted(directory.iterdir()):
            tar.add(path, arcname=path.name, recursive=False)
    archive.with_name(archive.name + '.sha256').write_text(digest(archive) + '\n')


def restore(archive, destination):
    if archive.with_name(archive.name + '.sha256').read_text().strip() != digest(archive):
        raise ValueError('archive digest mismatch')
    destination.mkdir(exist_ok=False)
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        names = [m.name for m in members]
        if (len(names) != len(set(names)) or any(not m.isfile() or not re.fullmatch(r'[a-zA-Z0-9_.-]+', m.name) for m in members)
                or sum(m.size for m in members) > 2_000_000_000):
            raise ValueError('unsafe archive membership or size')
        for member in members:
            with (destination / member.name).open('xb') as target:
                shutil.copyfileobj(tar.extractfile(member), target)
    checksums = json.loads((destination / 'checksums.json').read_text())
    if set(checksums) | {'checksums.json'} != set(names) or 'checksums.json' in checksums:
        raise ValueError('archive membership mismatch')
    for name, expected in checksums.items():
        if digest(destination / name) != expected:
            raise ValueError('member digest mismatch')
    return assess(destination)


def collect(args):
    protocol = json.loads(PROTOCOL.read_text())
    source = source_identity()
    claim = json.loads(args.claim.read_text())
    if (claim['source_commit'] != source['commit'] or
            claim['protocol_sha256'] != hashlib.sha256(canonical(protocol)).hexdigest() or
            instant(claim['intended_start_utc']) != instant(args.intended_start)):
        raise ValueError('claim/source/protocol/intended-start mismatch')
    verify_claim(claim)
    now = datetime.now(timezone.utc).isoformat()
    decision = gate(protocol, args.intended_start, now, args.mode)
    if not decision['accepted']:
        raise ValueError('outside prospective start window; retain claim, do not retry slot')
    args.out.mkdir(parents=True, exist_ok=False)
    directory = args.out / 'recording'
    directory.mkdir()
    write(directory / 'protocol.json', protocol)
    write(directory / 'claim.json', claim)
    write(directory / 'source.json', source)
    write(directory / 'trigger.json', json.loads(args.trigger.read_text()))
    manifest = {'schema_version': 1, 'mode': args.mode, 'intended_start_utc': args.intended_start,
                'requested_seconds': protocol['recording_seconds'], 'gate': decision,
                'collector_started_at_utc': now, 'collection_error_category': None}
    sampler = InstrumentSampler(directory, protocol['metadata_interval_seconds'])
    recorder = None
    try:
        factor = sampler.sample()
        if factor is None:
            raise ValueError('instrument unavailable')
        sampler.thread.start()
        # Metadata fetch and setup consume time; enforce the window immediately before recording.
        start = datetime.now(timezone.utc).isoformat()
        if not gate(protocol, args.intended_start, start, args.mode)['accepted']:
            raise ValueError('collector setup exceeded intended start window')
        manifest['collector_started_at_utc'] = start
        recorder = ProvenanceRecorder(directory, factor)
        recorder.run(protocol['recording_seconds'])
    except Exception:
        manifest['collection_error_category'] = 'collection_or_setup_failed'
    finally:
        sampler.finish()
        if recorder and recorder.metadata_path:
            recorder.metadata_path.rename(directory / 'recorder.json')
        manifest['collector_finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        write(directory / 'manifest.json', manifest)
    result = assess(directory)
    write(directory / 'assessment.json', result)
    archive = args.out / ('rehearsal-' + claim['owner_run_attempt'] + '.tar.gz')
    pack(directory, archive)
    with tempfile.TemporaryDirectory() as temporary:
        restored = restore(archive, Path(temporary) / 'restored')
    if result != restored:
        raise ValueError('restore assessment changed')
    write(args.out / 'local-restore.json', {'archive_sha256': digest(archive), 'assessment': restored})
    print('::notice title=Successor rehearsal::collection_healthy=' + str(result['collection_healthy']) + '; study_observation=False')
    return 0  # Failed quality remains visible; backup still must preserve the failed attempt.


STORAGE_TAG = 'study-archive-btc-execution-v1'


def storage_assets(repository, release):
    identifier = release.get('id')
    if type(identifier) is not int or identifier <= 0:
        raise ValueError('invalid existing archive release')
    result = []
    for page in range(1, 11):
        items = api(f'repos/{repository}/releases/{identifier}/assets?per_page=100&page={page}')
        result.extend(items)
        if len(items) < 100:
            names = [item['name'] for item in result]
            if len(names) != len(set(names)):
                raise ValueError('duplicate remote asset names')
            return result
    raise ValueError('archive inventory exceeds bound; reconcile before publication')


def preserve(args):
    """Use the approved existing Release. No new Release creation or asset replacement."""
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository):
        raise ValueError('invalid repository')
    archives = list(args.out.glob('rehearsal-*.tar.gz'))
    if len(archives) != 1:
        raise ValueError('one original archive required')
    archive = archives[0]
    owner = archive.name.removeprefix('rehearsal-').removesuffix('.tar.gz')
    if not re.fullmatch(r'[0-9]+-[0-9]+', owner):
        raise ValueError('unsafe original archive name')
    receipt_name = 'successor-readback-' + owner + '.json'
    print('::notice title=Successor preservation stage::existing_release_inventory')
    release = api(f'repos/{args.repository}/releases/tags/{STORAGE_TAG}')
    if release.get('draft') or not release.get('prerelease') or release.get('tag_name') != STORAGE_TAG:
        raise ValueError('unexpected existing archive release state')
    assets = storage_assets(args.repository, release)
    names = {item['name'] for item in assets}
    # Each archive's source ref is separate from the shared storage Release tag.
    ref = api(f'repos/{args.repository}/git/ref/tags/successor-rehearsal-{owner}')
    if ref.get('object', {}).get('sha') != args.source_commit:
        raise ValueError('archive source tag differs from original collector')
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for local in (archive, archive.with_name(archive.name + '.sha256')):
            if local.name not in names:
                print('::notice title=Successor preservation stage::original_asset_upload')
                subprocess.run(['gh','release','upload',STORAGE_TAG,str(local),'--repo',args.repository],
                               check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            subprocess.run(['gh','release','download',STORAGE_TAG,'--repo',args.repository,
                            '--pattern',local.name,'--dir',str(root)],
                           check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if digest(root/local.name) != digest(local):
                raise ValueError('existing remote asset conflicts; never overwrite')
        remote = root/archive.name
        result = restore(remote,root/'restored')
        claim = json.loads((root/'restored'/'claim.json').read_text())
        if claim['repository'] != args.repository or claim['source_commit'] != args.source_commit:
            raise ValueError('remote source/claim mismatch')
        verify_claim(claim)
        source = json.loads((root/'restored'/'source.json').read_text())
        if source['commit'] != args.source_commit or source['dirty'] is not False:
            raise ValueError('remote source revision mismatch')
        record = {'schema_version':1,'repository':args.repository,'release_tag':STORAGE_TAG,
                  'archive_name':archive.name,'receipt_asset_name':receipt_name,
                  'archive_sha256':digest(remote),'source_commit':source['commit'],
                  'slot_id':claim['slot_id'],'claim':claim,
                  'verified_at_utc':datetime.now(timezone.utc).isoformat(),
                  'remote_restored':True,'assessment':result,
                  'scope':'Shared infrastructure storage only; not a v1 study observation'}
        if receipt_name in names:
            subprocess.run(['gh','release','download',STORAGE_TAG,'--repo',args.repository,
                            '--pattern',receipt_name,'--dir',str(root)],
                           check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            existing = json.loads((root/receipt_name).read_text())
            if {k:v for k,v in existing.items() if k != 'verified_at_utc'} != {k:v for k,v in record.items() if k != 'verified_at_utc'}:
                raise ValueError('existing remote receipt conflicts')
            record = existing
        receipt_path = args.out/'remote-readback.json'
        if receipt_path.exists():
            local_receipt = json.loads(receipt_path.read_text())
            if {k:v for k,v in local_receipt.items() if k != 'verified_at_utc'} != {k:v for k,v in record.items() if k != 'verified_at_utc'}:
                raise ValueError('local receipt conflicts')
            if receipt_name not in names:
                record = local_receipt
        else:
            write(receipt_path,record)
        if receipt_name not in names:
            upload = root/receipt_name
            write(upload,record)
            subprocess.run(['gh','release','upload',STORAGE_TAG,str(upload),'--repo',args.repository],
                           check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    print('::notice title=Successor remote restore::verified=True collection_healthy=' + str(result['collection_healthy']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    record = sub.add_parser('collect')
    record.add_argument('--mode', choices=['transport_only', 'prospective'], required=True)
    record.add_argument('--intended-start', required=True)
    record.add_argument('--claim', type=Path, required=True)
    record.add_argument('--trigger', type=Path, required=True)
    record.add_argument('--out', type=Path, required=True)
    backup = sub.add_parser('preserve')
    backup.add_argument('--out', type=Path, required=True)
    backup.add_argument('--repository', required=True)
    backup.add_argument('--source-commit', required=True)
    verify = sub.add_parser('verify')
    verify.add_argument('--archive', type=Path, required=True)
    verify.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'verify':
        args.out.mkdir(parents=True, exist_ok=False)
        result = restore(args.archive, args.out / 'restored')
        write(args.out / 'restore-assessment.json', result)
        print('Archive restored and collection health recomputed; collection_healthy=' + str(result['collection_healthy']))
        return 0
    if args.command == 'collect':
        return collect(args)
    preserve(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
