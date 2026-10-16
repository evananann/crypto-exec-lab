"""Download this repository's dated study archives using injected gh authentication.

Used by the report workflow after the holdout release. No tokens are printed,
stored, or accepted as command-line arguments.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository):
        parser.error('invalid repository name')
    pages = json.loads(subprocess.check_output([
        'gh', 'api', '--paginate', '--slurp', f'repos/{args.repository}/actions/artifacts?per_page=100',
    ], text=True))
    args.out.mkdir(parents=True, exist_ok=True)
    count = 0
    for artifact in (a for page in pages for a in page['artifacts']):
        if artifact['expired'] or not re.fullmatch(r'btc-study-session-2026-10-(?:1[7-9]|2[0-3])-(?:am|pm)', artifact['name']):
            continue
        identifier = int(artifact['id'])
        download = args.out / f'artifact-{identifier}.zip'
        with download.open('xb') as stream:
            subprocess.run(['gh', 'api', f'repos/{args.repository}/actions/artifacts/{identifier}/zip'], stdout=stream, check=True)
        with zipfile.ZipFile(download) as zipped:
            entries = zipped.infolist()
            if len(entries) > 4 or sum(i.file_size for i in entries) > 2_000_000_000:
                raise ValueError('unexpected study artifact size/membership')
            for item in entries:
                if Path(item.filename).name != item.filename or not re.fullmatch(r'2026-10-\d{2}-(?:am|pm)\.tar\.gz(?:\.sha256)?', item.filename):
                    raise ValueError('unexpected study artifact filename')
                with zipped.open(item) as source, (args.out / item.filename).open('xb') as target:
                    shutil.copyfileobj(source, target)
        download.unlink()
        count += 1
    print(f'downloaded {count} study artifacts')


if __name__ == '__main__':
    main()
