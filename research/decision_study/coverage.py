"""Metadata-only slot ownership inventory. Never reads market tapes or outcomes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


def inventory(plan, refs, now):
    if now.utcoffset() is None:
        raise ValueError('timezone-aware as-of time required')
    claims = {}
    for line in refs.splitlines():
        parts = line.split()
        if len(parts) != 2 or not re.fullmatch('[0-9a-f]{40}', parts[0]):
            raise ValueError('malformed Git reference listing')
        sha, ref = parts
        prefix = 'refs/tags/successor-claims/' + plan['study_id'] + '/'
        if ref.startswith(prefix):
            stamp = ref[len(prefix):]
            time = datetime.strptime(stamp, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            if time in claims:
                raise ValueError('duplicate slot claim')
            claims[time] = sha
    rows = []
    planned_times = set()
    for slot in plan['planned_slots']:
        time = datetime.fromisoformat(slot['intended_start_utc'].replace('Z', '+00:00'))
        planned_times.add(time)
        rows.append(slot | {'elapsed': time <= now, 'claim_commit': claims.get(time),
                            'ownership_state': 'claimed_unverified' if time in claims else 'no_claim_observed',
                            'capture_verified': None, 'archive_verified': None})
    if set(claims) - planned_times:
        raise ValueError('claims outside registered slots')
    elapsed = [r for r in rows if r['elapsed']]
    return {'schema_version': 1, 'as_of_utc': now.isoformat(), 'study_id': plan['study_id'],
            'scope': 'Git reference ownership metadata only; claims are not capture, health or archive verification',
            'planned_slots': len(rows), 'elapsed_slots': len(elapsed),
            'elapsed_claims': sum(r['claim_commit'] is not None for r in elapsed),
            'elapsed_without_observed_claim': sum(r['claim_commit'] is None for r in elapsed),
            'capture_and_archive_verification': 'unavailable: authenticated Actions API access blocked',
            'outcomes_read': False, 'slots': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    registration = Path('configs/successor/registered_study.json')
    refs = subprocess.check_output(['git', 'ls-remote', '--tags', 'origin', 'refs/tags/successor-claims/*'], text=True)
    report = inventory(json.loads(registration.read_text()), refs, datetime.now(timezone.utc))
    report['registration_sha256'] = hashlib.sha256(registration.read_bytes()).hexdigest()
    report['refs_sha256'] = hashlib.sha256(refs.encode()).hexdigest()
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'refs.txt').write_text(refs)
    (args.out/'coverage.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
