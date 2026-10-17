"""Preserve original Actions archives as nonexpiring GitHub Release assets.

Includes failed attempts and preflights. Every published copy is downloaded
again and restored before success. No outcomes are calculated or published.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
from urllib.parse import quote
import zipfile

from cel.artifacts import file_sha256, write_json_atomic
from cel.study import load_plan, restore_archive, session_slot, verify_archive, verify_directory
from scripts.download_study_artifacts import download_zip
from scripts.study_monitor import PLANS, api_json, instant


def verify_source(repository, artifact, run, plan):
    source = artifact.get('workflow_run') or {}
    if (type(artifact.get('id')) is not int or artifact['id'] <= 0
            or type(source.get('id')) is not int or source['id'] <= 0
            or run.get('id') != source['id'] or run.get('status') != 'completed'
            or run.get('path') != plan.get('collection_workflow', '.github/workflows/live-study.yml')
            or run.get('event') not in ('push', 'schedule', 'workflow_dispatch')
            or run.get('head_branch') != 'main' or source.get('head_branch') != 'main'
            or (run.get('head_repository') or {}).get('full_name', '').lower() != repository.lower()
            or run.get('head_sha') != source.get('head_sha')
            or not isinstance(run.get('head_sha'), str) or not re.fullmatch('[0-9a-f]{40}', run['head_sha'])):
        raise ValueError('untrusted or unfinished collection source')


def unpack(path, out):
    with zipfile.ZipFile(path) as zipped:
        entries = zipped.infolist()
        names = [item.filename for item in entries]
        if (len(entries) != 2 or len(set(names)) != 2
                or sum(item.file_size for item in entries) > 2_000_000_000):
            raise ValueError('archive artifact must have one bounded checksum pair')
        archives = [name for name in names if re.fullmatch(r'[A-Za-z0-9-]+\.tar\.gz', name)]
        if len(archives) != 1 or set(names) != {archives[0], archives[0] + '.sha256'}:
            raise ValueError('unsafe or mismatched archive filenames')
        for item in entries:
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('symbolic link in artifact')
            with zipped.open(item) as source, (out / item.filename).open('xb') as target:
                shutil.copyfileobj(source, target)
    return out / archives[0]


def validate_attempt(archive, plan_path, artifact, run):
    plan, _ = load_plan(plan_path)
    item = verify_archive(archive)
    if (item['plan_sha256'] != file_sha256(plan_path) or item['collector_commit'] != run['head_sha']
            or item['collector_dirty'] is not False or archive.name != item['session_id'] + '.tar.gz'):
        raise ValueError('archive plan, name or collector differs from source')
    with tarfile.open(archive, 'r:gz') as tar:
        if tar.extractfile('plan.json').read() != plan_path.read_bytes():
            raise ValueError('archived frozen plan differs')
    prefix = plan.get('artifact_prefix', 'btc-study-session-')
    named = artifact['name'][len(prefix):]
    if item['phase'] == 'preflight':
        if not named.startswith('preflight-') or item['status'] not in ('blocked', 'ineligible', 'preflight_passed'):
            raise ValueError('invalid preflight label or state')
    else:
        if run['event'] == 'push' or named != item['session_id'] or item['status'] not in ('blocked', 'ineligible', 'eligible'):
            raise ValueError('invalid observation source, label or state')
        slot = named.rsplit('-', 1)[1]
        identifier, phase = session_slot(plan, instant(item['started_at_utc']), slot)
        if identifier != named or phase != item['phase']:
            raise ValueError('observation falls outside its frozen slot')
    with tempfile.TemporaryDirectory(prefix='source-restore-') as directory:
        restored = restore_archive(archive, Path(directory))
        verify_directory(restored, plan_path)
    return item


def create_release(repository, plan, revision):
    tag = 'study-archive-' + plan['study_id']
    pages = api_json(f'repos/{repository}/releases?per_page=100', paginate=True)
    matching = [r for page in pages for r in page if r.get('tag_name') == tag]
    if len(matching) > 1:
        raise ValueError('ambiguous archive release')
    if matching:
        release = matching[0]
        if release.get('draft'):
            raise ValueError('existing archive release is unexpectedly a draft')
        return tag, release
    payload = {'tag_name': tag, 'target_commitish': revision,
               'name': 'Study archives: ' + plan['study_id'], 'draft': False,
               'prerelease': True, 'make_latest': 'false',
               'body': 'Original public-data study archives, checksums and provenance. Includes failed attempts. '
                       'No automatic expiry; not a strategy-results release. No claim of eligible collection or profitability.'}
    with tempfile.TemporaryDirectory(prefix='release-metadata-') as directory:
        body = Path(directory) / 'release.json'
        write_json_atomic(body, payload)
        release = json.loads(subprocess.check_output(['gh', 'api', '--method', 'POST',
            f'repos/{repository}/releases', '--input', str(body)], text=True))
    return tag, release


def publish_and_verify(repository, tag, release, archive, receipt, plan_path):
    identifier = release.get('id')
    if type(identifier) is not int or identifier <= 0:
        raise ValueError('invalid archive release ID')
    pages = api_json(f'repos/{repository}/releases/{identifier}/assets?per_page=100', paginate=True)
    assets = [a for page in pages for a in page]
    names = [a['name'] for a in assets]
    if len(set(names)) != len(names):
        raise ValueError('duplicate remote asset names')
    prefix = f"{receipt['study_id']}-run-{receipt['run_id']}-artifact-{receipt['artifact_id']}-"
    base = prefix + archive.name
    with tempfile.TemporaryDirectory(prefix='release-roundtrip-') as directory:
        root = Path(directory)
        local = root / 'upload'
        remote = root / 'download'
        local.mkdir()
        remote.mkdir()
        shutil.copyfile(archive, local / base)
        shutil.copyfile(archive.with_suffix('.gz.sha256'), local / (base + '.sha256'))
        write_json_atomic(local / (base + '.provenance.json'), receipt)
        for path in sorted(local.iterdir()):
            if path.name not in names:
                # No --clobber: evidence can never be replaced by this workflow.
                subprocess.run(['gh', 'release', 'upload', tag, str(path), '--repo', repository], check=True)
            subprocess.run(['gh', 'release', 'download', tag, '--repo', repository,
                            '--pattern', path.name, '--dir', str(remote)], check=True)
            if file_sha256(remote / path.name) != file_sha256(path):
                raise ValueError('release copy differs; existing asset was not overwritten')
        copied = remote / base
        manifest = verify_archive(copied)
        restored = restore_archive(copied, root / 'restore')
        verify_directory(restored, plan_path)
        if manifest['session_id'] != receipt['session_id']:
            raise ValueError('restored release session differs')
    return f'https://github.com/{repository}/releases/download/{quote(tag, safe="")}/{quote(base, safe="")}'


def preserve(repository, *, plan_paths=PLANS):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('invalid repository')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('invalid current revision')
    plans = [(path, load_plan(path)[0]) for path in plan_paths]
    pages = api_json(f'repos/{repository}/actions/artifacts?per_page=100', paginate=True)
    artifacts = [a for page in pages for a in page['artifacts']]
    records, problems = [], []
    releases, runs = {}, {}
    for path, plan in plans:
        prefix = plan.get('artifact_prefix', 'btc-study-session-')
        for artifact in artifacts:
            if not artifact.get('name', '').startswith(prefix):
                continue
            stage = 'source_verification'
            try:
                if artifact.get('expired'):
                    stage = 'expired_source'
                    raise ValueError('original artifact expired; verify existing release copy separately')
                run_id = (artifact.get('workflow_run') or {}).get('id')
                if type(run_id) is not int or run_id <= 0:
                    raise ValueError('invalid source run')
                if run_id not in runs:
                    runs[run_id] = api_json(f'repos/{repository}/actions/runs/{run_id}')
                run = runs[run_id]
                verify_source(repository, artifact, run, plan)
                with tempfile.TemporaryDirectory(prefix='preserve-attempt-') as directory:
                    stage = 'source_download'
                    root = Path(directory)
                    zipped = root / 'artifact.zip'
                    download_zip(repository, artifact['id'], zipped)
                    archive = unpack(zipped, root)
                    stage = 'archive_verification'
                    item = validate_attempt(archive, path, artifact, run)
                    receipt = {'schema_version': 1, 'study_id': plan['study_id'], 'repository': repository,
                               'artifact_id': artifact['id'], 'run_id': run_id, 'head_sha': run['head_sha'],
                               'workflow': run['path'], 'event': run['event'], 'conclusion': run.get('conclusion'),
                               'session_id': item['session_id'], 'status': item['status'],
                               'archive_sha256': file_sha256(archive), 'plan_sha256': file_sha256(path),
                               'original_archive_name': archive.name}
                    if plan['study_id'] not in releases:
                        stage = 'release_creation'
                        releases[plan['study_id']] = create_release(repository, plan, revision)
                    tag, release = releases[plan['study_id']]
                    stage = 'release_upload_or_roundtrip'
                    url = publish_and_verify(repository, tag, release, archive, receipt, path)
                    records.append({**receipt, 'archive_url': url, 'download_and_restore_verified': True})
            except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError,
                    tarfile.TarError, zipfile.BadZipFile):
                # Only bounded fixed messages are public. Full CLI logs retain
                # diagnosis; no raw remote exception enters annotations.
                problems.append({'study_id': plan['study_id'], 'artifact_id': artifact.get('id'),
                                 'state': 'not_preserved_or_not_verified', 'stage': stage})
    return {'as_of_utc': datetime.now(timezone.utc).isoformat(), 'repository': repository,
            'verified_copies': len(records), 'archives': records, 'problems': problems,
            'retention': 'No automatic expiry. Same repository/provider; deletion or account loss remains possible.',
            'scope': 'Original archives and restore integrity only; no outcome evaluation or collection eligibility claim.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        result = preserve(args.repository)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError):
        result = {'verified_copies': 0, 'archives': [], 'problems': [
            {'study_id': 'inventory', 'artifact_id': None, 'stage': 'inventory_or_plan_setup',
             'state': 'not_preserved_or_not_verified'}]}
    write_json_atomic(args.out / 'preservation.json', result)
    for problem in result['problems'][:10]:
        identifier = problem['artifact_id'] if type(problem['artifact_id']) is int else 'unknown'
        print(f"::error title=Archive preservation::{problem['study_id']} artifact {identifier}: {problem['stage']} failed")
    print(f"::notice title=Archive preservation::{result['verified_copies']} original archives downloaded and restored from Releases; {len(result['problems'])} problems.")
    print(f"{result['verified_copies']} verified off-machine copies")
    return 1 if result['problems'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
