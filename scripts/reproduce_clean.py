"""Reproduce tests, a bundle and archive restoration in a fresh independent clone.

Clones committed local Git objects without hardlinks. It never copies the
working tree, credentials, untracked tapes or an existing virtual environment.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time


def reproduce(source, out, *, revision=None, benchmark=False):
    source = source.resolve()
    out = out.resolve()
    if out.is_relative_to(source) or source.is_relative_to(out):
        raise ValueError('reproduction must be outside the source checkout')
    if revision is None:
        revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('expected revision must be a full commit hash')
    out.mkdir(parents=True, exist_ok=False)
    logs = out / 'logs'
    logs.mkdir()
    clone = out / 'checkout'
    state = {'source_commit': revision, 'clone_method': 'git clone --no-local; no copied working tree or environment',
             'status': 'running', 'steps': []}
    env = os.environ.copy()
    env['MPLCONFIGDIR'] = str(out / 'matplotlib')
    env['XDG_CACHE_HOME'] = str(out / 'cache')
    env.setdefault('UV_CACHE_DIR', str(out / 'uv-cache'))

    def save():
        (out / 'result.json').write_text(json.dumps(state, indent=2) + '\n')

    def run(label, command, cwd):
        start = time.perf_counter()
        with (logs / (label + '.log')).open('w') as log:
            completed = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
        record = {'step': label, 'returncode': completed.returncode,
                  'seconds': time.perf_counter() - start, 'log': str(Path('logs') / (label + '.log'))}
        state['steps'].append(record)
        save()
        if completed.returncode:
            raise RuntimeError(label + ' failed; inspect its saved log')
        if label == 'tests':
            text = (logs / 'tests.log').read_text()
            count = re.search(r'Ran (\d+) tests?', text)
            if not count or int(count.group(1)) == 0:
                raise RuntimeError('test discovery did not execute a nonempty suite')
            record['tests_executed'] = int(count.group(1))

    save()
    try:
        run('clone', ['git', 'clone', '--no-local', str(source), str(clone)], source)
        run('checkout', ['git', 'checkout', '--detach', revision], clone)
        run('install', ['uv', 'sync', '--frozen', '--extra', 'dev', '--python', '3.12'], clone)
        python = str(clone / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))
        run('tests', [python, '-m', 'unittest', 'discover', '-s', 'tests'], clone)
        run('bundle', [python, '-m', 'cel.experiments', '--demo', '--out', 'data/raw/clean-bundle'], clone)
        run('verify', [python, '-S', 'scripts/verify_bundle.py', 'data/raw/clean-bundle',
                       '--expected-commit', revision, '--source-repo', '.'], clone)
        run('restore', [python, '-m', 'scripts.check_archive_restore', '--source', 'reports/evidence',
                        '--out', 'data/raw/restore-report.json'], clone)
        if benchmark:
            run('benchmark', [python, '-m', 'scripts.benchmark_pipeline', '--synthetic',
                              '--out', 'data/raw/performance.json'], clone)
        state['status'] = 'passed'
    except (OSError, RuntimeError) as exc:
        state['status'] = 'failed'
        state['error'] = str(exc)
    save()
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--expected-commit')
    parser.add_argument('--benchmark', action='store_true')
    args = parser.parse_args(argv)
    result = reproduce(args.source_repo, args.out, revision=args.expected_commit, benchmark=args.benchmark)
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
