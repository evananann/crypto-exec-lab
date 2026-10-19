"""Atomic GitHub reference claims. No force update, deletion, or expired-owner takeover."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def instant(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('timezone-aware intended start required')
    return result.astimezone(timezone.utc)


def slot_identity(protocol_id, intended_start):
    if not re.fullmatch(r'[a-z0-9-]{1,80}', protocol_id):
        raise ValueError('invalid protocol ID')
    intended = instant(intended_start)
    if intended.microsecond:
        raise ValueError('intended start must be a whole UTC second')
    return protocol_id + '/' + intended.strftime('%Y%m%dT%H%M%SZ')


def api(endpoint, payload=None):
    args = ['gh', 'api', endpoint]
    if payload is not None:
        args += ['--method', 'POST', '--input', '-']
    result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                            text=True, capture_output=True)
    if result.returncode:
        # Do not publish raw API errors, headers, credentials or proxy details.
        match = re.search(r'HTTP (\d{3})', result.stderr)
        status = match.group(1) if match else 'unknown'
        raise RuntimeError('GitHub API operation failed; HTTP status=' + status)
    return json.loads(result.stdout)


def claim(repository, protocol, intended_start, source_commit, owner, *, request=api):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('invalid repository')
    if not re.fullmatch(r'[0-9a-f]{40}', source_commit) or not re.fullmatch(r'[0-9]+-[0-9]+', owner):
        raise ValueError('invalid source revision or run/attempt owner')
    identity = slot_identity(protocol['protocol_id'], intended_start)
    record = {'schema_version': 1, 'repository': repository, 'slot_id': identity,
              'intended_start_utc': instant(intended_start).isoformat(),
              'source_commit': source_commit, 'owner_run_attempt': owner,
              'protocol_sha256': hashlib.sha256(canonical(protocol)).hexdigest()}
    parent = request(f'repos/{repository}/git/commits/{source_commit}')
    unique_commit = request(f'repos/{repository}/git/commits', {
        'message': 'Successor slot ownership\n' + canonical(record).decode(),
        'tree': parent['tree']['sha'], 'parents': [source_commit]})
    ref = 'refs/tags/successor-claims/' + identity
    result = request(f'repos/{repository}/git/refs', {'ref': ref, 'sha': unique_commit['sha']})
    if result.get('ref') != ref or result.get('object', {}).get('sha') != unique_commit['sha']:
        raise ValueError('claim receipt does not establish this owner')
    return record | {'claim_ref': ref, 'claim_commit': unique_commit['sha'],
                     'claimed_at_utc': datetime.now(timezone.utc).isoformat()}


def verify_claim(receipt, *, request=api):
    repository = receipt['repository']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('invalid repository')
    ref = receipt['claim_ref']
    if not ref.startswith('refs/tags/successor-claims/') or '..' in ref:
        raise ValueError('invalid claim reference')
    current = request(f'repos/{repository}/git/ref/{ref.removeprefix("refs/")}')
    if current.get('object', {}).get('sha') != receipt['claim_commit']:
        raise ValueError('claim ownership changed or unavailable')
    commit = request(f'repos/{repository}/git/commits/{receipt["claim_commit"]}')
    expected = {k: receipt[k] for k in ('schema_version', 'repository', 'slot_id',
                'intended_start_utc', 'source_commit', 'owner_run_attempt', 'protocol_sha256')}
    if commit['message'] != 'Successor slot ownership\n' + canonical(expected).decode():
        raise ValueError('claim owner metadata mismatch')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--intended-start', required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('claim output must be new')
    result = claim(args.repository, json.loads(args.protocol.read_text()), args.intended_start,
                   args.source_commit, args.owner)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
