"""Retrieve both reports from one trusted completed replication-report run."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from cel.artifacts import write_json_atomic
from cel.study import DEFAULT_PLAN, load_plan
from scripts.download_study_artifacts import download_zip
from scripts.study_monitor import api_json
from scripts.verify_bundle import safe_name, verify


def verify_source(repository, run_id, run):
    if (run.get('id') != run_id or run.get('head_branch') != 'main'
            or run.get('path') != '.github/workflows/replication-report.yml'
            or run.get('event') not in ('schedule', 'workflow_dispatch')
            or run.get('status') != 'completed' or run.get('conclusion') != 'success'
            or (run.get('head_repository') or {}).get('full_name', '').lower() != repository.lower()
            or not isinstance(run.get('head_sha'), str) or not re.fullmatch('[0-9a-f]{40}', run['head_sha'])):
        raise ValueError('report run has untrusted source, state or revision')


def unpack(path, out):
    with zipfile.ZipFile(path) as zipped:
        entries = zipped.infolist()
        names = [item.filename for item in entries]
        if (len(entries) > 10000 or len(set(names)) != len(names)
                or sum(item.file_size for item in entries) > 2_000_000_000):
            raise ValueError('duplicate or oversized report artifact')
        for item in entries:
            name = item.filename.rstrip('/') if item.is_dir() else item.filename
            if (not safe_name(name) or name.split('/')[0] not in ('bundle', 'provenance')
                    or (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('unsafe report artifact entry')
        out.mkdir(parents=True, exist_ok=False)
        for item in entries:
            path = out / item.filename
            if item.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(item) as source, path.open('xb') as target:
                    shutil.copyfileobj(source, target)


def download(repository, run_id, out, *, source_repo=DEFAULT_PLAN.parents[1], now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    for pair in ('okx', 'bybit'):
        plan, _ = load_plan(DEFAULT_PLAN.with_name(f'study_v2_{pair}.json'))
        if now.date() <= date.fromisoformat(plan['end_date_utc']):
            raise ValueError('replication reports remain gated until November 23 UTC')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or type(run_id) is not int or run_id <= 0:
        raise ValueError('invalid repository or report run ID')
    run = api_json(f'repos/{repository}/actions/runs/{run_id}')
    verify_source(repository, run_id, run)
    pages = api_json(f'repos/{repository}/actions/runs/{run_id}/artifacts?per_page=100', paginate=True)
    artifacts = [a for page in pages for a in page['artifacts']]
    wanted = {f'btc-replication-v2-{pair}-report': pair for pair in ('okx', 'bybit')}
    chosen = [a for a in artifacts if a['name'] in wanted]
    if len(chosen) != 2 or {a['name'] for a in chosen} != set(wanted):
        raise ValueError('both unique venue reports from the same run are required')
    if any(a.get('expired') or type(a['id']) is not int or a['id'] <= 0 for a in chosen):
        raise ValueError('report artifact is expired or invalid')
    out.mkdir(parents=True, exist_ok=False)
    for item in chosen:
        pair = wanted[item['name']]
        with tempfile.TemporaryDirectory(prefix='.report-', dir=out) as directory:
            archive = Path(directory) / 'download.zip'
            download_zip(repository, item['id'], archive)
            unpack(archive, out / pair)
        checked = verify(out / pair / 'bundle', expected_commit=run['head_sha'], source_repo=source_repo)
        if checked['synthetic']:
            raise ValueError('synthetic bundle cannot stand in for a released empirical report')
    write_json_atomic(out / 'run-provenance.json', {'repository': repository, 'run_id': run_id,
        'head_sha': run['head_sha'], 'workflow': run['path'],
        'artifact_ids': {wanted[a['name']]: a['id'] for a in chosen}})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    download(args.repository, args.run_id, args.out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
