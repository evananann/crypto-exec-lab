"""Recover preservation of an original rehearsal artifact; never record another market period."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
from types import SimpleNamespace
import zipfile

from scripts.download_study_artifacts import download_zip
from scripts.successor_claim import api, verify_claim
from scripts.successor_readiness import verify_source
from scripts.successor_rehearsal import preserve, restore, write


def unpack(zipped, out, archive_name):
    allowed = {'claim.json','trigger.json','assessment.json','local-restore.json','remote-readback.json',
               archive_name, archive_name+'.sha256'}
    with zipfile.ZipFile(zipped) as source:
        entries = source.infolist()
        if len(entries) > 12 or sum(e.file_size for e in entries) > 2_010_000_000:
            raise ValueError('recovery artifact exceeds bound')
        names = [e.filename for e in entries]
        if len(names) != len(set(names)):
            raise ValueError('duplicate recovery members')
        for entry in entries:
            path = Path(entry.filename)
            if (path.is_absolute() or '..' in path.parts or path.name not in allowed or
                    len(path.parts) > 2 or (len(path.parts) == 2 and path.parts[0] not in ('successor-control','successor-attempt')) or
                    (entry.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('unsafe recovery artifact member')
            target = out / path
            target.parent.mkdir(parents=True,exist_ok=True)
            with source.open(entry) as original, target.open('xb') as destination:
                shutil.copyfileobj(original,destination)


def recover(repository, run_id, out):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('invalid repository')
    if run_id is None:
        runs = api(f'repos/{repository}/actions/workflows/successor-rehearsal.yml/runs?branch=main&status=failure&per_page=20')['workflow_runs']
        if not runs:
            raise ValueError('no failed original rehearsal to recover')
        run_id = runs[0]['id']
    if type(run_id) is not int or run_id <= 0:
        raise ValueError('invalid original run ID')
    print('::notice title=Successor recovery stage::original_run_verification')
    run = api(f'repos/{repository}/actions/runs/{run_id}')
    if (run.get('path') != '.github/workflows/successor-rehearsal.yml' or run.get('head_branch') != 'main' or
            run.get('status') != 'completed' or run.get('event') not in ('push','workflow_dispatch') or
            (run.get('head_repository') or {}).get('full_name','').lower() != repository.lower()):
        raise ValueError('untrusted original rehearsal')
    attempt = run['run_attempt']
    owner = f'{run_id}-{attempt}'
    expected_name = 'successor-rehearsal-' + owner
    print('::notice title=Successor recovery stage::original_artifact_inventory')
    artifacts = api(f'repos/{repository}/actions/runs/{run_id}/artifacts?per_page=100')['artifacts']
    matching = [a for a in artifacts if a.get('name') == expected_name and not a.get('expired')]
    if len(matching) != 1:
        raise ValueError('one unexpired original artifact required')
    artifact = matching[0]
    identity = artifact.get('workflow_run')
    # This inventory is already scoped to the authenticated original run. Some
    # GitHub responses omit workflow_run; if present it must agree. The archived
    # owner/source claim is independently authenticated after download in all cases.
    if identity is not None and (identity.get('id') != run_id or identity.get('head_sha') != run['head_sha'] or identity.get('head_branch') != 'main'):
        raise ValueError('artifact provenance differs from original run')
    out.mkdir(parents=True,exist_ok=False)
    zipped = out/'original.zip'
    print('::notice title=Successor recovery stage::original_artifact_download')
    download_zip(repository,artifact['id'],zipped)
    print('::notice title=Successor recovery stage::original_artifact_unpack')
    unpack(zipped,out/'download','rehearsal-'+owner+'.tar.gz')
    archives = list((out/'download').rglob('rehearsal-'+owner+'.tar.gz'))
    if len(archives) != 1:
        raise ValueError('original archive absent or ambiguous; no recollection allowed')
    archive = archives[0]
    print('::notice title=Successor recovery stage::original_archive_restore')
    assessment = restore(archive,out/'restore')
    claim = json.loads((out/'restore'/'claim.json').read_text())
    if claim['owner_run_attempt'] != owner or claim['source_commit'] != run['head_sha'] or claim['repository'] != repository:
        raise ValueError('archive/claim/source mismatch')
    print('::notice title=Successor recovery stage::original_source_and_claim_verification')
    verify_source(out/'restore',run['head_sha'],require_current=False)
    verify_claim(claim)
    print('::notice title=Successor recovery stage::release_preservation')
    preserve(SimpleNamespace(repository=repository,out=archive.parent,source_commit=run['head_sha']))
    result = {'schema_version':1,'original_run_id':run_id,'original_attempt':attempt,
              'original_conclusion':run['conclusion'],'source_commit':run['head_sha'],
              'remote_restore_verified':True,'original_assessment':assessment,
              'new_recording_performed':False,'qualifying_prospective_success':False,
              'scope':'Preservation recovered; original failed attempt remains failed and does not qualify timing'}
    write(out/'recovery.json',result)
    print('::notice title=Successor preservation recovery::original_run=' + str(run_id) +
          ' remote_restored=True collection_healthy=' + str(assessment['collection_healthy']) + ' new_recording=False')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository',required=True)
    parser.add_argument('--run-id',type=int)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    try:
        recover(args.repository,args.run_id,args.out)
    except ValueError as exc:
        allowed = ('untrusted original rehearsal', 'one unexpired original artifact required',
                   'artifact provenance differs from original run', 'unsafe recovery artifact member',
                   'original archive absent or ambiguous; no recollection allowed',
                   'archive/claim/source mismatch', 'member digest mismatch', 'archive digest mismatch',
                   'source hash differs from committed blob', 'source identity differs from trusted run',
                   'existing remote asset conflicts; never overwrite', 'existing release tag points to another source')
        message = str(exc) if str(exc) in allowed else 'verification_failed'
        print('::error title=Successor recovery::' + message)
        raise
    except Exception as exc:
        code = re.fullmatch(r'GitHub API operation failed; HTTP status=([0-9]{3}|unknown)', str(exc))
        category = 'api_http_' + code.group(1) if code else type(exc).__name__
        print('::error title=Successor recovery::operation_failed category=' + category)
        raise


if __name__=='__main__':
    main()
