"""Independently restore original collection bytes for health, never alpha outcomes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from scripts.successor_claim import canonical, instant
from scripts.successor_readiness import verify_source
from scripts.successor_rehearsal import restore
from scripts.successor_study import load_registration


def run(sources, coverage_path, out):
    plan = load_registration()
    coverage = json.loads(coverage_path.read_text())
    assets = {a['name']: a for r in json.loads((sources/'releases.json').read_text()) for a in r['assets']}
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    report = dict(schema_version=1,
                  scope='Archive/source/health verification; no estimator or alpha outcomes',
                  strategy_outcomes_evaluated=0, completed=False, slots=rows)
    (out/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    for slot in coverage['slots']:
        if not slot['archive_metadata_complete']:
            continue
        name = slot['archive_candidates'][0]
        receipt_name = 'readback-' + name.removesuffix('.tar.gz') + '.json'
        receipt = json.loads((sources/'receipts'/receipt_name).read_text())
        with tempfile.TemporaryDirectory(prefix='health-restore-') as temporary:
            root = Path(temporary)
            for filename in (name, name + '.sha256'):
                asset = assets[filename]
                url = asset['browser_download_url']
                if not url.startswith('https://github.com/evananann/crypto-exec-lab/releases/download/'):
                    raise ValueError('unexpected archive destination')
                target = root/filename
                subprocess.run(['curl', '--fail', '--silent', '--show-error', '-L', '--max-time', '180', url, '-o', str(target)], check=True)
                if asset['digest'] != 'sha256:' + hashlib.sha256(target.read_bytes()).hexdigest():
                    raise ValueError('GitHub asset digest differs')
            sha = hashlib.sha256((root/name).read_bytes()).hexdigest()
            if sha != receipt['archive_sha256']:
                raise ValueError('archive differs from original preservation receipt')
            restored = root/'restored'
            assessment = restore(root/name, restored)
            manifest = json.loads((restored/'manifest.json').read_text())
            owned = json.loads((restored/'claim.json').read_text())
            trigger = json.loads((restored/'trigger.json').read_text())
            if (assessment != receipt['assessment'] or owned != receipt['claim']
                    or owned['claim_commit'] != slot['claim_commit']
                    or canonical(json.loads((restored/'protocol.json').read_text())) != canonical(plan)
                    or owned['protocol_sha256'] != hashlib.sha256(canonical(plan)).hexdigest()
                    or manifest['study_id'] != plan['study_id']
                    or manifest['session_id'] != slot['slot_id'] or manifest['phase'] != slot['phase']
                    or manifest['registration_sha256'] != hashlib.sha256(Path('configs/successor/registered_study.json').read_bytes()).hexdigest()
                    or instant(manifest['intended_start_utc']) != instant(slot['intended_start_utc'])
                    or trigger['source_commit'] != owned['source_commit']
                    or str(trigger['run_id'])+'-'+str(trigger['run_attempt']) != owned['owner_run_attempt']):
                raise ValueError('restored registration/claim/health identity mismatch')
            verify_source(restored, owned['source_commit'], require_current=True)
            rows.append(dict(slot_id=slot['slot_id'], archive_name=name, archive_sha256=sha,
                             source_commit=owned['source_commit'], assessment=assessment,
                             archive_verified=True, source_verified=True,
                             eligibility=None, sender_authentication='not_reperformed',
                             verified_at_utc=datetime.now(timezone.utc).isoformat()))
            (out/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
            print('Verified health:', slot['slot_id'], 'healthy=', assessment['collection_healthy'], flush=True)
    report['completed'] = True
    report['archives_verified'] = len(rows)
    (out/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--coverage', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run(args.sources, args.coverage, args.out)
