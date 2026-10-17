"""Download and verify study archives from completed main-branch collection runs.

Uses gh's injected authentication. Never accepts or prints credential values.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

from cel.artifacts import file_sha256, write_json_atomic
from cel.study import DEFAULT_PLAN, load_plan, verify_archive

WORKFLOW = '.github/workflows/live-study.yml'


def api_json(endpoint, *, paginate=False):
    args = ['gh', 'api']
    if paginate:
        args += ['--paginate', '--slurp']
    return json.loads(subprocess.check_output([*args, endpoint], text=True))


def download_zip(repository, artifact_id, path):
    with path.open('xb') as stream:
        subprocess.run(['gh', 'api', f'repos/{repository}/actions/artifacts/{artifact_id}/zip'], stdout=stream, check=True)


def expected_names(plan):
    names = {}
    day = date.fromisoformat(plan['start_date_utc'])
    while day <= date.fromisoformat(plan['end_date_utc']):
        for slot in plan['slots_utc']:
            session = f'{day}-{slot}'
            names[plan.get('artifact_prefix', 'btc-study-session-') + session] = session
        day += timedelta(days=1)
    return names


def verify_run(repository, artifact, run, *, workflow=WORKFLOW):
    source = artifact['workflow_run']
    if (run.get('id') != source['id'] or run.get('path') != workflow
            or run.get('head_branch') != 'main' or source.get('head_branch') != 'main'
            or (run.get('head_repository') or {}).get('full_name', '').lower() != repository.lower()
            or run.get('event') not in ('schedule', 'workflow_dispatch')
            or run.get('status') != 'completed'
            or run.get('head_sha') != source.get('head_sha')
            or not isinstance(run.get('head_sha'), str)
            or not re.fullmatch('[0-9a-f]{40}', run['head_sha'])):
        raise ValueError(f"untrusted or unfinished collection run for artifact {artifact['id']}")
    # Failed runs still carry useful blocked/ineligible attempts. Never filter
    # by success: doing so could silently discard adverse observations.


def unpack_zip(path, staging, session):
    expected = {session + '.tar.gz', session + '.tar.gz.sha256'}
    with zipfile.ZipFile(path) as zipped:
        entries = zipped.infolist()
        if len(entries) != 2 or {i.filename for i in entries} != expected:
            raise ValueError('artifact label/archive names or checksum pair do not match')
        if sum(i.file_size for i in entries) > 2_000_000_000:
            raise ValueError('study artifact exceeds size bound')
        if any((i.external_attr >> 16) & 0o170000 == 0o120000 for i in entries):
            raise ValueError('artifact contains a symbolic link')
        for item in entries:
            with zipped.open(item) as source, (staging / item.filename).open('xb') as target:
                shutil.copyfileobj(source, target)
    return staging / (session + '.tar.gz')


def download(repository, out, plan_path=DEFAULT_PLAN):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('invalid repository name')
    plan, _ = load_plan(plan_path)
    names = expected_names(plan)
    pages = api_json(f'repos/{repository}/actions/artifacts?per_page=100', paginate=True)
    artifacts = [a for page in pages for a in page['artifacts'] if a['name'] in names]
    seen = set()
    runs = {}
    for artifact in artifacts:
        if artifact['name'] in seen:
            raise ValueError('duplicate study artifact names; reconcile all attempts instead of choosing a retry')
        seen.add(artifact['name'])
        if artifact['expired']:
            raise ValueError(f"study artifact {artifact['id']} expired; use the independent archived copy")
        if type(artifact['id']) is not int or artifact['id'] <= 0:
            raise ValueError('invalid artifact ID')
        run_id = (artifact.get('workflow_run') or {}).get('id')
        if type(run_id) is not int or run_id <= 0:
            raise ValueError('invalid workflow run ID')
        if run_id not in runs:
            runs[run_id] = api_json(f'repos/{repository}/actions/runs/{run_id}')
        verify_run(repository, artifact, runs[run_id], workflow=plan.get('collection_workflow', WORKFLOW))
    out.mkdir(parents=True, exist_ok=True)
    for artifact in artifacts:
        session = names[artifact['name']]
        filenames = [session + suffix for suffix in ('.tar.gz', '.tar.gz.sha256', '.provenance.json')]
        if any((out / name).exists() for name in filenames):
            raise FileExistsError(f'output already contains {session}')
        with tempfile.TemporaryDirectory(prefix='.study-', dir=out) as temporary:
            staging = Path(temporary)
            zipped = staging / 'download.zip'
            download_zip(repository, artifact['id'], zipped)
            archive = unpack_zip(zipped, staging, session)
            manifest = verify_archive(archive)
            run = runs[artifact['workflow_run']['id']]
            if (manifest['session_id'] != session or manifest['plan_sha256'] != file_sha256(plan_path)
                    or manifest['collector_commit'] != run['head_sha'] or manifest['collector_dirty'] is not False):
                raise ValueError('archive session, frozen plan, or collector revision conflicts with source run')
            receipt = {'repository': repository, 'artifact_id': artifact['id'], 'run_id': run['id'],
                       'head_sha': run['head_sha'], 'workflow': run['path'], 'event': run['event'],
                       'conclusion': run.get('conclusion'), 'session_id': session,
                       'archive_sha256': file_sha256(archive), 'plan_sha256': manifest['plan_sha256']}
            write_json_atomic(staging / filenames[2], receipt)
            for name in filenames:
                with (staging / name).open('rb') as source, (out / name).open('xb') as target:
                    shutil.copyfileobj(source, target)
    return len(artifacts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plan', type=Path, default=DEFAULT_PLAN)
    args = parser.parse_args(argv)
    try:
        count = download(args.repository, args.out, args.plan)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, zipfile.BadZipFile, tarfile.TarError) as exc:
        parser.error(str(exc))
    print(f'downloaded and provenance-verified {count} study artifacts')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
