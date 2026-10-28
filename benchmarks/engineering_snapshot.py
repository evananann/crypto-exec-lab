"""Convert measured coverage JSON into a dated, source-bound summary and badges."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def badge(label, value, color):
    left, right = len(label)*7+12, len(value)*7+12
    return f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{escape(label+": "+value)}" width="{left+right}" height="22"><rect width="{left+right}" height="22" rx="3" fill="{color}"/><path d="M0 0h{left}v22H0z" fill="#444"/><g fill="#fff" font-family="DejaVu Sans,Verdana,sans-serif" font-size="11" text-anchor="middle"><text x="{left/2}" y="15">{escape(label)}</text><text x="{left+right/2}" y="15">{escape(value)}</text></g></svg>\n'


def snapshot(coverage_path, output):
    report = json.loads(coverage_path.read_text())
    files = {name: {'summary': value['summary'],
                    'sha256': hashlib.sha256((ROOT/name).read_bytes()).hexdigest()}
             for name, value in report['files'].items()}
    test_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted((ROOT/'tests').glob('test_*.py'))}
    result = {'as_of_utc': datetime.now(timezone.utc).isoformat(),
              'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'tracked_changes': bool(subprocess.check_output(['git', 'diff', 'HEAD', '--name-only'], cwd=ROOT, text=True).strip()),
              'coverage_version': report['meta']['version'], 'branch_measurement': report['meta']['branch_coverage'],
              'totals': report['totals'], 'files': files, 'test_source_sha256': test_hashes,
              'scope': 'Measured parent-process unittest coverage for cel, research and scripts. Combined line/branch percent; not proof of behavior, not coverage of uninstrumented subprocesses/notebooks/live feeds. Snapshot, not a 95% claim.'}
    output.mkdir(parents=True, exist_ok=True)
    (output/'coverage-summary.json').write_text(json.dumps(result, indent=2)+'\n')
    percent = report['totals']['percent_covered']
    (output/'coverage.svg').write_text(badge('coverage snapshot', f'{percent:.1f}%', '#217c42' if percent >= 90 else '#926500'))
    (output/'python.svg').write_text(badge('Python CI', '3.11 | 3.12 | 3.13', '#24629a'))
    (output/'frozen.svg').write_text(badge('source binding', 'SHA-256', '#24629a'))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--coverage-json', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = snapshot(a.coverage_json, a.output)
    print('Measured combined line/branch coverage:', round(result['totals']['percent_covered'], 2))
