"""Copy verified study archives to an independent mounted archive directory.

An existing mounted durable destination is required for off-machine retention.
Local copies alone do not establish durable or geographically separate storage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile

from cel.artifacts import file_sha256, write_json_atomic
from cel.study import verify_archive


def preserve(source, destination):
    source, destination = source.resolve(), destination.resolve()
    if source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError('archive source and destination must be independent directories')
    archives = sorted(source.glob('*.tar.gz'))
    if not archives:
        raise ValueError('no archives to preserve')
    # Validate every source before copying any. Never silently select a retry.
    manifests = [(p, verify_archive(p)) for p in archives]
    identifiers = [m['session_id'] for _, m in manifests]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('duplicate session attempts require reconciliation')
    for path, item in manifests:
        if path.name != item['session_id'] + '.tar.gz' or Path(item['session_id']).name != item['session_id']:
            raise ValueError('unsafe or mismatched archive session name')
    destination.mkdir(parents=True, exist_ok=True)
    inventory = []
    for archive, manifest in manifests:
        target = destination / manifest['session_id']
        checksum = archive.with_suffix(archive.suffix + '.sha256')
        receipt = source / (manifest['session_id'] + '.provenance.json')
        files = [archive, checksum] + ([receipt] if receipt.is_file() else [])
        if target.exists():
            if {p.name for p in target.iterdir()} != {p.name for p in files}:
                raise ValueError('backup membership conflicts; existing evidence was retained')
            if any(p.is_symlink() or not p.is_file() for p in target.iterdir()):
                raise ValueError('unsafe existing backup entry')
            if any(file_sha256(p) != file_sha256(target / p.name) for p in files):
                raise ValueError('backup conflicts; existing evidence was retained')
        else:
            with tempfile.TemporaryDirectory(prefix='.preserve-', dir=destination) as directory:
                staging = Path(directory) / 'session'
                staging.mkdir()
                for path in files:
                    shutil.copyfile(path, staging / path.name)
                    if file_sha256(staging / path.name) != file_sha256(path):
                        raise ValueError('copy checksum mismatch')
                verify_archive(staging / archive.name)
                staging.rename(target)
        verify_archive(target / archive.name)
        inventory.append({'session_id': manifest['session_id'], 'status': manifest['status'],
                          'archive_sha256': file_sha256(target / archive.name),
                          'plan_sha256': manifest['plan_sha256']})
    # Inventory includes only this invocation; never removes older archives.
    write_json_atomic(destination / 'latest-copy.json', {'archives': inventory,
        'retention': 'No automatic deletion. Operator must verify destination durability.'})
    return inventory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        copied = preserve(args.source, args.destination)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({'verified_copies': len(copied), 'destination': str(args.destination)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
