"""Bridge approved public-feed archives through Git blobs to a Release worker.

The cloud connection can write GitHub API objects but cannot authenticate against
uploads.github.com. A repository worker uses its own scoped token for that step.
Public data objects are unreferenced blobs; raw tapes never enter commit history.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile

REPO = 'evananann/crypto-exec-lab'
LIMIT = 128_000_000


def gh(*args, payload=None):
    r = subprocess.run(['gh', *args], input=payload, capture_output=True, text=True, timeout=180)
    if r.returncode:
        raise RuntimeError('GitHub transfer failed; response suppressed to protect signed URLs')
    return r.stdout


def checked_archive(path):
    if path.is_symlink() or path.stat().st_size > LIMIT:
        raise ValueError('archive exceeds public transfer bound')
    with tarfile.open(path, 'r:gz') as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        if len(members) > 1000 or len(set(names)) != len(names) or sum(m.size for m in members) > LIMIT:
            raise ValueError('duplicate or oversized archive membership')
        for m in members:
            p = PurePosixPath(m.name)
            if (not m.isfile() or p.is_absolute() or any(x in ('.', '..') for x in m.name.split('/'))
                    or '\\' in m.name or len(p.parts) > 2
                    or (len(p.parts) == 2 and p.parts[0] not in ('spool', 'source'))):
                raise ValueError('unsafe public archive member')
            if len(p.parts) == 1 and m.name not in {
                    'config.json', 'main.log', 'restart.log', 'qualification-protocol.json',
                    'qualification-report.json'}:
                raise ValueError('unapproved public archive root member')


def put_blob(body):
    payload = json.dumps({'encoding': 'base64', 'content': base64.b64encode(body).decode()})
    return gh('api', f'repos/{REPO}/git/blobs', '--method', 'POST', '--input', '-', '--jq', '.sha',
              payload=payload).strip()


def stage(archive, checksums, receipt):
    if receipt.exists():
        raise FileExistsError('never overwrite transfer staging receipt')
    checked_archive(archive)
    manifest = {'schema_version': 1, 'scope': 'Approved public-feed rehearsal archive only', 'files': []}
    for path in (archive, checksums):
        if path.name not in ('qualification.tar.gz', 'checksums.json') or path.is_symlink():
            raise ValueError('only approved archive and checksum asset names allowed')
        body = path.read_bytes()
        if len(body) > LIMIT:
            raise ValueError('asset too large')
        parts = []
        for start in range(0, len(body), 500_000):
            part = body[start:start + 500_000]
            parts.append({'blob': put_blob(part), 'sha256': hashlib.sha256(part).hexdigest(), 'bytes': len(part)})
        manifest['files'].append({'name': path.name, 'sha256': hashlib.sha256(body).hexdigest(),
                                  'bytes': len(body), 'parts': parts})
    raw = json.dumps(manifest, sort_keys=True).encode()
    result = {'manifest_blob': put_blob(raw), 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
              'scope': manifest['scope'], 'files': [{k: v for k, v in f.items() if k != 'parts'}
                                                  for f in manifest['files']]}
    receipt.write_text(json.dumps(result, indent=2) + '\n')
    return result


def get_blob(identifier):
    if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{40}', identifier):
        raise ValueError('exact Git blob identity required')
    data = json.loads(gh('api', f'repos/{REPO}/git/blobs/{identifier}'))
    body = base64.b64decode(data['content'].replace('\n', ''), validate=True)
    if len(body) > 1_000_000 or hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest() != identifier:
        raise ValueError('Git blob identity or size mismatch')
    return body


def receive(blob, expected, tag, out):
    if not re.fullmatch('qualification-cloud-[A-Za-z0-9-]+', tag):
        raise ValueError('isolated public qualification release required')
    raw = get_blob(blob)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('manifest SHA256 mismatch')
    manifest = json.loads(raw)
    if (manifest.get('schema_version') != 1 or manifest.get('scope') != 'Approved public-feed rehearsal archive only'
            or {f['name'] for f in manifest['files']} != {'qualification.tar.gz', 'checksums.json'}
            or len(manifest['files']) != 2):
        raise ValueError('unapproved transfer manifest')
    out.mkdir(parents=True, exist_ok=False)
    for f in manifest['files']:
        if len(f['parts']) > 260 or not 0 < f['bytes'] <= LIMIT:
            raise ValueError('bounded asset parts required')
        h, total = hashlib.sha256(), 0
        with (out / f['name']).open('xb') as target:
            for part in f['parts']:
                data = get_blob(part['blob'])
                if len(data) != part['bytes'] or hashlib.sha256(data).hexdigest() != part['sha256']:
                    raise ValueError('transfer part differs')
                total += len(data)
                if total > LIMIT:
                    raise ValueError('transfer bound exceeded')
                target.write(data)
                h.update(data)
        if total != f['bytes'] or h.hexdigest() != f['sha256']:
            raise ValueError('assembled asset differs')
    checked_archive(out / 'qualification.tar.gz')
    index = json.loads((out / 'checksums.json').read_text())
    with tarfile.open(out / 'qualification.tar.gz', 'r:gz') as archive:
        if {m.name for m in archive.getmembers()} != set(index):
            raise ValueError('archive inventory differs from checksums')
        for m in archive.getmembers():
            with archive.extractfile(m) as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != index[m.name]:
                    raise ValueError('original archive member differs')
    assets = json.loads(gh('release', 'view', tag, '--repo', REPO, '--json', 'assets'))['assets']
    readback = out / 'readback'
    readback.mkdir()
    for f in manifest['files']:
        if f['name'] not in {a['name'] for a in assets}:
            gh('release', 'upload', tag, str(out / f['name']), '--repo', REPO)
        gh('release', 'download', tag, '--pattern', f['name'], '--dir', str(readback), '--repo', REPO)
        if hashlib.sha256((readback / f['name']).read_bytes()).hexdigest() != f['sha256']:
            raise ValueError('remote asset readback differs; never overwrite it')
    result = {'status': 'REMOTE_READBACK_VERIFIED', 'manifest_blob': blob, 'manifest_sha256': expected,
              'release_url': f'https://github.com/{REPO}/releases/tag/{tag}',
              'assets': [{k: v for k, v in f.items() if k != 'parts'} for f in manifest['files']],
              'members_verified': len(index), 'worm_or_object_lock': False,
              'scientific_enrollment': False, 'production_host_qualified': False,
              'scope': 'Authenticated repository worker assembled public blobs, verified every member, '
                       'uploaded without replacement and downloaded exact remote assets. '
                       'Integrity/readback, not immutable storage or UTC qualification.'}
    (out / 'preservation.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['stage', 'receive'])
    p.add_argument('--archive', type=Path)
    p.add_argument('--checksums', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--manifest-blob')
    p.add_argument('--manifest-sha256')
    p.add_argument('--tag')
    a = p.parse_args()
    if a.mode == 'stage':
        result = stage(a.archive, a.checksums, a.out)
    else:
        result = receive(a.manifest_blob, a.manifest_sha256, a.tag, a.out)
    print(json.dumps(result))
