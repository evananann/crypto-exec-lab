"""Join frozen slots to saved ownership/run/archive metadata, without outcomes."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from research.decision_study.coverage import inventory
from scripts.successor_study import load_registration, study_namespace


def build(sources, now):
    plan = load_registration()
    refs = subprocess.check_output(['git', 'for-each-ref', '--format=%(objectname) %(refname)',
                                    'refs/tags/successor-claims/' + plan['study_id']], text=True)
    coverage = inventory(plan, refs, now)
    runs = json.loads((sources / 'successor-runs.json').read_text())
    releases = json.loads((sources / 'releases.json').read_text())
    by_id = {str(r['id']): r for r in runs['workflow_runs']}
    assets = [a for r in releases for a in r['assets']]
    names = {a['name'] for a in assets}
    for slot in coverage['slots']:
        owner = None
        if slot['claim_commit']:
            message = subprocess.check_output(['git', 'show', '-s', '--format=%B',
                                               slot['claim_commit']], text=True)
            owner = json.loads(message[message.index('{'):])
            stamp = slot['intended_start_utc'].replace('Z', '+00:00')
            if (owner['repository'] != 'evananann/crypto-exec-lab'
                    or datetime.fromisoformat(owner['intended_start_utc']) != datetime.fromisoformat(stamp)):
                raise ValueError('claim does not match slot or repository')
        run = by_id.get(owner['owner_run_attempt'].split('-')[0]) if owner else None
        authenticated = bool(run and run['path'] == '.github/workflows/successor-study.yml'
                             and run['head_branch'] == 'main' and run['event'] == 'workflow_dispatch'
                             and run['status'] == 'completed'
                             and run.get('actor', {}).get('login') == 'github-actions[bot]'
                             and run.get('head_repository', {}).get('full_name') == 'evananann/crypto-exec-lab'
                             and run['head_sha'] == owner['source_commit']
                             and str(run['run_attempt']) == owner['owner_run_attempt'].split('-')[1])
        prefix = study_namespace(plan, slot)
        candidates = [a['name'] for a in assets if a['name'].startswith(prefix + '-')
                      and a['name'].endswith('.tar.gz')]
        allowance = datetime.fromisoformat(slot['intended_start_utc'].replace('Z', '+00:00')) + timedelta(seconds=plan['maximum_start_lateness_seconds'])
        reason = ('not_yet_due' if now <= allowance else
                  'no_ownership_claim_observed_cause_unknown' if not owner else
                  'owner_run_metadata_unverified' if not authenticated else
                  'archive_not_listed' if not candidates else
                  'archive_metadata_present_bytes_health_and_eligibility_unverified')
        complete = len(candidates) == 1 and {candidates[0] + '.sha256', 'readback-' + candidates[0].removesuffix('.tar.gz') + '.json'} <= names
        receipt = None
        receipt_name = 'readback-' + candidates[0].removesuffix('.tar.gz') + '.json' if complete else None
        receipt_path = sources / 'receipts' / receipt_name if receipt_name else None
        if receipt_path and receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            metadata = next(a for a in assets if a['name'] == receipt_name)
            if (metadata.get('digest') != 'sha256:' + hashlib.sha256(receipt_path.read_bytes()).hexdigest()
                    or not authenticated or receipt['source_commit'] != owner['source_commit']
                    or receipt['archive_name'] != candidates[0]
                    or any(receipt['claim'].get(k) != v for k, v in owner.items())
                    or receipt['claim']['claim_commit'] != slot['claim_commit']
                    or receipt['repository'] != owner['repository']):
                raise ValueError('receipt metadata authentication failed')
            reason = 'receipt_reports_health_archive_bytes_not_independently_reverified'
        slot.update(owner=owner, owner_run_metadata_verified=authenticated,
                    owner_run_url=run['html_url'] if run else None,
                    workflow_conclusion=run['conclusion'] if run else None,
                    capture_attempted=True if receipt else None,
                    capture_attempt_basis='preservation receipt' if receipt else 'unknown; ownership alone is insufficient',
                    archive_candidates=candidates, archive_metadata_complete=complete,
                    receipt_reported_health=receipt['assessment'] if receipt else None,
                    receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest() if receipt else None,
                    collection_health=None, eligible=None, missing_reason=reason)
    coverage.update(capture_and_archive_verification='Metadata join only; archive bytes and health not inspected',
                    unknowns_are_not_zero_returns=True,
                    reason_counts=dict(Counter(s['missing_reason'] for s in coverage['slots'])),
                    run_inventory_complete=len(runs['workflow_runs']) == runs['total_count'],
                    source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted(sources.glob('*.json'))},
                    refs_sha256=hashlib.sha256(refs.encode()).hexdigest())
    return coverage, refs


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report, refs = build(args.sources, datetime.now(timezone.utc))
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'coverage.json').write_text(json.dumps(report, indent=2) + '\n')
    (args.out / 'refs.txt').write_text(refs)
