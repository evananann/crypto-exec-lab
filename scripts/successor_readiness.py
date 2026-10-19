"""Authenticate durable rehearsal evidence before allowing a prospective study freeze."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from scripts.successor_claim import api, canonical, instant, verify_claim
from scripts.successor_rehearsal import PROTOCOL, STORAGE_TAG, digest, restore, write, storage_assets


def summarize(records, protocol):
    identities = [row['slot_id'] for row in records]
    if len(identities) != len(set(identities)):
        raise ValueError('duplicate claimed slot in readiness evidence')
    qualified = [row for row in records if row['authenticated_remote_restore'] is True and
                 row['assessment']['collection_healthy'] is True and
                 row['assessment']['timing']['timing_qualified'] is True and
                 row['event'] == 'workflow_dispatch' and row.get('qualification_compatible', True) and
                 row.get('source_run_conclusion', 'success') == 'success']
    dates = sorted({instant(row['intended_start_utc']).date().isoformat() for row in qualified})
    prospective = sorted([row for row in records if row['event'] == 'workflow_dispatch'],
                         key=lambda row: (row.get('run_created_at_utc', row.get('intended_start_utc') or ''), row.get('run_attempt', 1)))
    latest = prospective[-protocol['minimum_rehearsals']:]
    latest_dates = {instant(row['intended_start_utc']).date().isoformat() for row in latest if row in qualified}
    ready = (len(latest) == protocol['minimum_rehearsals'] and all(row in qualified for row in latest)
             and len(latest_dates) >= protocol['minimum_distinct_utc_dates'])
    return {'schema_version': 1, 'as_of_utc': datetime.now(timezone.utc).isoformat(),
            'protocol_sha256': hashlib.sha256(canonical(protocol)).hexdigest(),
            'activation_ready': ready, 'study_activated': False,
            'attempts_examined': len(records), 'qualifying_prospective_rehearsals': len(qualified),
            'qualifying_utc_dates': dates, 'records': records,
            'remaining': [] if ready else ['Need the latest three prospective attempts all healthy, on time and remotely restored, over at least two UTC dates'],
            'limitation': 'Observed prospective timing success is not a scheduler SLA. Transport-only rehearsals never qualify.'}


def verify_source(directory, revision, *, require_current=True):
    source = json.loads((directory / 'source.json').read_text())
    if source.get('commit') != revision or source.get('dirty') is not False:
        raise ValueError('source identity differs from trusted run')
    for name, expected in source['files_sha256'].items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or (require_current and (not path.is_file() or digest(path) != expected)):
            raise ValueError('rehearsal code changed; repeat qualification with the current source')
        committed = subprocess.check_output(['git', 'show', revision + ':' + name])
        if hashlib.sha256(committed).hexdigest() != expected:
            raise ValueError('source hash differs from committed blob')


def inspect(repository):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('invalid repository')
    protocol = json.loads(PROTOCOL.read_text())
    storage = api(f'repos/{repository}/releases/tags/{STORAGE_TAG}')
    if storage.get('draft') or not storage.get('prerelease'):
        raise ValueError('unexpected archive release state')
    assets = storage_assets(repository, storage)
    attempts = []
    for asset in assets:
        match = re.fullmatch(r'rehearsal-([0-9]+-[0-9]+)\.tar\.gz', asset['name'])
        if match:
            owner = match.group(1)
            own_names = {asset['name'],asset['name']+'.sha256','successor-readback-'+owner+'.json'}
            attempts.append({'tag_name':STORAGE_TAG,'owner':owner,'prerelease':True,'draft':False,
                             'assets':[a for a in assets if a['name'] in own_names]})
    runs = api(f'repos/{repository}/actions/workflows/successor-rehearsal.yml/runs?branch=main&per_page=100')['workflow_runs']
    if len(runs) >= 100:
        raise ValueError('run inventory may be truncated; reconcile before activation')
    trusted_runs = {}
    for run in runs:
        if (run.get('path') != '.github/workflows/successor-rehearsal.yml' or run.get('head_branch') != 'main' or
                (run.get('head_repository') or {}).get('full_name', '').lower() != repository.lower() or
                run.get('event') not in ('push', 'workflow_dispatch')):
            raise ValueError('untrusted rehearsal inventory')
        count = run.get('run_attempt', 1)
        if type(count) is not int or not 1 <= count <= 10:
            raise ValueError('attempt history requires manual reconciliation')
        for attempt in range(1, count + 1):
            owner = f'{run["id"]}-{attempt}'
            trusted_runs[owner] = run
    records, seen = [], set()
    for release in attempts:
        if release.get('draft') or not release.get('prerelease'):
            raise ValueError('unexpected rehearsal release state')
        tag = release['tag_name']
        owner = release['owner']
        archive_name = 'rehearsal-' + owner + '.tar.gz'
        receipt_name = 'successor-readback-' + owner + '.json'
        assets = release.get('assets', [])
        names = [item['name'] for item in assets]
        if (len(names) != 3 or set(names) != {archive_name, archive_name + '.sha256', receipt_name} or
                sum(item.get('size', 0) for item in assets) > 2_010_000_000):
            raise ValueError('incomplete, unexpected or oversized rehearsal assets')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in sorted(names):
                subprocess.run(['gh', 'release', 'download', tag, '--repo', repository, '--pattern', name, '--dir', str(root)],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            archives = list(root.glob('*.tar.gz'))
            if len(archives) != 1:
                raise ValueError('one original rehearsal archive required')
            archive = archives[0]
            restored = root / 'restored'
            assessment = restore(archive, restored)
            claim = json.loads((restored / 'claim.json').read_text())
            trigger = json.loads((restored / 'trigger.json').read_text())
            manifest = json.loads((restored / 'manifest.json').read_text())
            # A release interrupted before its remote-restore receipt is not qualified.
            receipt_path = root / receipt_name
            if not receipt_path.is_file():
                raise ValueError('remote restore receipt missing; interrupted preservation requires diagnosis')
            receipt = json.loads(receipt_path.read_text())
            if (receipt.get('archive_sha256') != digest(archive) or receipt.get('remote_restored') is not True or
                    receipt.get('claim') != claim or receipt.get('assessment') != assessment or
                    receipt.get('repository') != repository or receipt.get('release_tag') != tag or
                    receipt.get('archive_name') != archive_name or receipt.get('receipt_asset_name') != receipt_name):
                raise ValueError('receipt does not bind the downloaded original and recomputed assessment')
            archived_protocol = json.loads((restored / 'protocol.json').read_text())
            if claim['repository'] != repository or claim['protocol_sha256'] != hashlib.sha256(canonical(archived_protocol)).hexdigest():
                raise ValueError('claim repository or archived protocol differs')
            compatible = canonical(archived_protocol) == canonical(protocol)
            verify_claim(claim)
            owner = claim['owner_run_attempt']
            if owner != release['owner']:
                raise ValueError('asset namespace differs from original owner')
            if owner not in trusted_runs or owner in seen:
                raise ValueError('orphan or repeated rehearsal release')
            seen.add(owner)
            run_id, attempt = owner.split('-')
            run = api(f'repos/{repository}/actions/runs/{run_id}/attempts/{attempt}')
            if (run.get('path') != '.github/workflows/successor-rehearsal.yml' or run.get('head_branch') != 'main' or
                    run.get('head_sha') != claim['source_commit'] or run.get('status') != 'completed' or
                    (run.get('head_repository') or {}).get('full_name','').lower() != repository.lower() or
                    run.get('event') not in ('push', 'workflow_dispatch') or
                    run.get('conclusion') not in ('success', 'failure', 'cancelled', 'timed_out', 'action_required', 'neutral', 'skipped', 'stale')):
                raise ValueError('untrusted or incomplete rehearsal run')
            verify_source(restored, run['head_sha'], require_current=False)
            committed_protocol = json.loads(subprocess.check_output(['git', 'show', run['head_sha'] + ':' + str(PROTOCOL)]))
            if canonical(committed_protocol) != canonical(archived_protocol):
                raise ValueError('archived protocol differs from its authenticated source')
            if compatible and run['event'] == 'workflow_dispatch':
                try:
                    verify_source(restored, run['head_sha'], require_current=True)
                except ValueError:
                    compatible = False  # Preserve earlier source-bound trials; require new matching qualification.
            if (instant(trigger['intended_start_utc']) != instant(claim['intended_start_utc']) or
                    instant(manifest['intended_start_utc']) != instant(claim['intended_start_utc']) or
                    trigger['run_id'] != int(run_id) or trigger['event'] != run['event'] or
                    str(trigger['run_attempt']) != attempt or trigger['source_commit'] != run['head_sha']):
                raise ValueError('trigger/claim/manifest disagreement')
            records.append({'slot_id': claim['slot_id'], 'intended_start_utc': claim['intended_start_utc'],
                            'source_commit': run['head_sha'], 'event': run['event'], 'release_tag': tag,
                            'run_created_at_utc': run['created_at'], 'run_attempt': int(attempt),
                            'qualification_compatible': compatible, 'source_run_conclusion': run['conclusion'],
                            'authenticated_remote_restore': True, 'assessment': assessment})
    for owner, run in trusted_runs.items():
        if owner in seen:
            continue
        records.append({'slot_id': 'unverified-attempt-' + owner, 'intended_start_utc': None,
                        'run_created_at_utc': run['created_at'], 'run_attempt': int(owner.split('-')[1]),
                        'event': run['event'], 'authenticated_remote_restore': False,
                        'assessment': {'collection_healthy': False, 'timing': {'timing_qualified': False}},
                        'reason': 'No authenticated remote archive/receipt; may be running, skipped or interrupted'})
    return summarize(records, protocol)


def registration(readiness, start_date, now, protocol):
    """Produce a prospective freeze document only after authenticated readiness succeeds."""
    if readiness.get('activation_ready') is not True:
        raise ValueError('activation blocked: prospective rehearsal gate has not passed')
    if readiness['protocol_sha256'] != hashlib.sha256(canonical(protocol)).hexdigest():
        raise ValueError('readiness refers to another protocol')
    day = datetime.strptime(start_date, '%Y-%m-%d').date()
    current = instant(now).date()
    if not current < day <= current + timedelta(days=30):
        raise ValueError('study must start on a future UTC date within 30 days')
    end = day + timedelta(days=27)
    reference = Path('configs/study_v2_okx.json')
    method = json.loads(reference.read_text())
    return {'schema_version': 1, 'study_id': 'btc-successor-v3-' + day.strftime('%Y%m%d'),
            'state': 'freeze_prepared_requires_committed_registration_before_collection',
            'start_date_utc': str(day), 'development_end_date_utc': str(day + timedelta(days=20)),
            'end_date_utc': str(end), 'outcome_release_date_utc': str(end + timedelta(days=1)),
            'slots_utc': {'am':'03:17','pm':'15:17'}, 'seconds': 900,
            'maximum_start_lateness_seconds': protocol['maximum_start_lateness_seconds'],
            'inherited_method_plan_sha256': digest(reference),
            'hypothesis': method['hypothesis'], 'primary_outcome': method['primary_outcome'],
            'decision_rule': method['decision_rule'],
            'protocol_sha256': readiness['protocol_sha256'], 'rehearsal_readiness': readiness,
            'activation_note': 'A committed prospective registration and a study-specific collector/report integration are still required. This document alone does not activate collection.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--prepare-start-date')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('choose a new evidence file')
    result = inspect(args.repository)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write(args.out, result)
    if args.prepare_start_date:
        prepared = registration(result, args.prepare_start_date, datetime.now(timezone.utc).isoformat(),
                                json.loads(PROTOCOL.read_text()))
        write(args.out.with_name(args.out.stem + '-registration.json'), prepared)
    print('::notice title=Successor activation::ready=' + str(result['activation_ready']) + '; study_activated=False')


if __name__ == '__main__':
    main()
