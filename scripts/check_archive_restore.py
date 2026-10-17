"""Restore every preserved archive into temporary storage and verify its files.

No outcome evaluation or network calls. Source archives are never modified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from cel.artifacts import file_sha256, write_json_atomic
from cel.study import DEFAULT_PLAN, load_plan, restore_archive, verify_archive, verify_directory


def check(source):
    paths = sorted(source.rglob('*.tar.gz'))
    if not paths:
        raise ValueError('no archives found')
    known = {}
    for path in DEFAULT_PLAN.parent.glob('study_v*.json'):
        plan, _ = load_plan(path)
        known[file_sha256(path)] = (path, plan)
    records, seen = [], set()
    with tempfile.TemporaryDirectory(prefix='restore-drill-') as temporary:
        for archive in paths:
            before = file_sha256(archive)
            item = verify_archive(archive)
            if item['plan_sha256'] not in known:
                raise ValueError('archive uses an unrecognized plan')
            plan_path, plan = known[item['plan_sha256']]
            identity = (item['plan_sha256'], item['session_id'])
            if identity in seen:
                raise ValueError('duplicate attempt; reconcile without selecting a retry')
            seen.add(identity)
            restored = restore_archive(archive, Path(temporary) / plan['study_id'])
            checked = verify_directory(restored, plan_path)
            if file_sha256(archive) != before:
                raise ValueError('source archive changed during restore')
            records.append({'study_id': plan['study_id'], 'session_id': item['session_id'],
                            'archive_sha256': before, 'restored_files': len(checked['files']) + 1,
                            'original_status': item['status']})
    return {'as_of_utc': datetime.now(timezone.utc).isoformat(), 'archives_verified': len(records),
            'records': records, 'scope': 'Temporary restore and file integrity; not durable storage or collection eligibility.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    if args.out and (args.out.exists() or args.out.resolve().is_relative_to(args.source.resolve())):
        parser.error('choose a new report path outside the evidence source')
    result = check(args.source)
    if args.out:
        write_json_atomic(args.out, result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
