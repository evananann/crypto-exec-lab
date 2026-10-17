"""Verify a research bundle offline with Python 3.11+ and optional local Git sources.

Checksums establish integrity, not authorship. A trusted expected commit and
local Git repository additionally bind declared source bytes to that revision.
External market tapes are never opened through paths supplied in the report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_name(name):
    return (isinstance(name, str) and bool(name) and '\\' not in name
            and not any(ord(c) < 32 for c in name)
            and not PurePosixPath(name).is_absolute()
            and PurePosixPath(name).as_posix() == name
            and not any(part in ('.', '..') for part in name.split('/')))


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON object key')
        result[key] = value
    return result


def read_json(path, *, limit=128_000_000):
    if path.stat().st_size > limit:
        raise ValueError('JSON document exceeds verifier size bound')
    def invalid_constant(value):
        raise ValueError('nonfinite JSON number')
    return json.loads(path.read_text(), object_pairs_hook=unique_object,
                      parse_constant=invalid_constant)


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('accounting value must be finite and numeric')
    return value


def equal(actual, expected, label):
    if not math.isclose(number(actual), expected, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError('accounting mismatch: ' + label)


def accounting(row):
    cash = fees = inventory = 0.0
    previous = -1
    for fill in row['fills']:
        if fill['side'] not in ('buy', 'sell') or fill['reason'] not in ('entry', 'exit'):
            raise ValueError('invalid fill side or reason')
        ts, quote_ts = fill['ts'], fill['quote_ts']
        if (type(ts) is not int or type(quote_ts) is not int or quote_ts < 0
                or ts < previous or quote_ts > ts or row['end_ts'] is None or ts > row['end_ts']):
            raise ValueError('fill timestamp violates coverage or ordering')
        previous = ts
        size, price, fee = [number(fill[k]) for k in ('size_btc', 'price', 'fee_usdt')]
        if size <= 0 or price <= 0 or fee < 0:
            raise ValueError('invalid fill size, price or fee')
        rate = number(row['config']['entry_fee_bps' if fill['reason'] == 'entry' else 'exit_fee_bps'])
        equal(fee, size * price * rate / 10000, 'per-fill fee')
        signed = size if fill['side'] == 'buy' else -size
        inventory += signed
        cash -= signed * price + fee
        fees += fee
    equal(row['cash_usdt'], cash, 'cash')
    equal(row['fees_usdt'], fees, 'total fees')
    equal(row['inventory_btc'], inventory, 'inventory')
    trades = row['closed_trades']
    if type(row['closed_trade_count']) is not int or row['closed_trade_count'] != len(trades):
        raise ValueError('closed-trade count mismatch')
    if trades:
        equal(row['mean_closed_bps'], sum(number(t['pnl_bps']) for t in trades) / len(trades), 'mean closed return')
    elif row['mean_closed_bps'] is not None:
        raise ValueError('empty trade set must have unavailable mean')
    if abs(inventory) <= 1e-12:
        equal(row['mtm_usdt'], cash, 'flat marked value')
        equal(sum(number(t['pnl_usdt']) for t in trades), cash, 'closed-trade cash')
    if row['fill_audit']['passed'] is not True or row['fill_audit']['fills_checked'] != len(row['fills']):
        raise ValueError('missing or inconsistent recorded fill audit')


def verify(root, *, expected_commit=None, source_repo=None):
    if root.is_symlink() or not root.is_dir():
        raise ValueError('bundle root must be a regular directory')
    entries = []
    for entry in root.rglob('*'):
        if len(entries) >= 100_000:
            raise ValueError('bundle exceeds verifier entry bound')
        if entry.is_symlink() or not (entry.is_file() or entry.is_dir()):
            raise ValueError('bundle contains a symlink or special entry')
        entries.append(entry)
    index = read_json(root / 'checksums.json', limit=16_000_000)
    if not isinstance(index, dict) or not index:
        raise ValueError('missing completion inventory')
    for name, value in index.items():
        if not safe_name(name) or name == 'checksums.json' or not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
            raise ValueError('invalid inventory path or digest')
    files = {p.relative_to(root).as_posix() for p in entries if p.is_file()}
    if files != {*index, 'checksums.json'}:
        raise ValueError('bundle membership mismatch')
    for name, value in index.items():
        if digest(root / name) != value:
            raise ValueError('bundle checksum mismatch: ' + name)
    data = read_json(root / 'experiments.json')
    if data['schema_version'] != 1 or type(data['synthetic']) is not bool:
        raise ValueError('unsupported report schema')
    rows = [*data['roundtrips'], *data['baselines']]
    for row in rows:
        accounting(row)
    if data['synthetic']:
        if len(data['inputs']) != 1 or data['inputs'][0]['sha256'] != index.get('synthetic.jsonl'):
            raise ValueError('synthetic input digest mismatch')
    if expected_commit is not None:
        if not re.fullmatch('[0-9a-f]{40}', expected_commit) or data['git_commit'] != expected_commit:
            raise ValueError('expected commit mismatch')
    verified_sources = 0
    if source_repo is not None:
        if expected_commit is None or data['git_dirty'] is not False:
            raise ValueError('source verification requires an expected commit and clean recorded tree')
        sources = data['sources_sha256']
        if not isinstance(sources, dict) or not sources:
            raise ValueError('missing source inventory')
        for name, value in sources.items():
            if not safe_name(name) or not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
                raise ValueError('invalid source path or digest')
            # Compare committed blobs, not current working-tree files. Never
            # follow absolute external paths from an untrusted report.
            try:
                contents = subprocess.check_output(['git', '-C', str(source_repo), 'cat-file',
                    'blob', expected_commit + ':' + name], stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError as exc:
                raise ValueError('declared source missing from expected commit: ' + name) from exc
            if hashlib.sha256(contents).hexdigest() != value:
                raise ValueError('source differs from expected commit: ' + name)
            verified_sources += 1
    return {'files_verified': len(index), 'accounting_rows_verified': len(rows),
            'synthetic': data['synthetic'], 'recorded_commit': data['git_commit'],
            'source_blobs_verified': verified_sources,
            'scope': 'Integrity and accounting; external tape provenance and live execution remain unverified.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--expected-commit')
    parser.add_argument('--source-repo', type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify(args.bundle, expected_commit=args.expected_commit, source_repo=args.source_repo)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
