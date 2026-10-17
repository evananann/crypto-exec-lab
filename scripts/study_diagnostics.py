"""Publish bounded collection health annotations, never market outcomes or raw errors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


def diagnostic(manifest):
    status = manifest.get('status')
    if status not in ('blocked', 'ineligible', 'eligible', 'preflight_passed'):
        status = 'unknown'
    factor = manifest.get('verified_contract_value_btc')
    verified = type(factor) in (int, float) and 0 < factor < float('inf')
    parts = [f'status={status}', f'instrument_verified={verified}']
    health = manifest.get('health') or {}
    for venue in ('binance', 'okx'):
        metrics = (health.get('venues') or {}).get(venue, {})
        for field in ('bbo', 'span_ms', 'max_silence_ms'):
            value = metrics.get(field)
            text = str(value) if type(value) is int and 0 <= value <= 10**15 else 'unavailable'
            parts.append(f'{venue}.{field}={text}')
    # Do not echo raw exceptions: they may contain URLs, headers or arbitrary
    # remote text. Only fixed categories and recognized HTTP status codes leave
    # the private diagnostic archive.
    errors = ' '.join(str(e) for e in manifest.get('errors', [])).lower()
    codes = sorted(set(re.findall(r'(?<!\d)(?:400|401|403|404|407|429|451|500|502|503|504)(?!\d)', errors)))
    if codes:
        parts.append('http_codes=' + ','.join(codes))
    for label, markers in (
        ('proxy_error', ('proxy', 'connect 403')),
        ('tls_error', ('certificate', 'ssl', 'tls')),
        ('timeout', ('timed out', 'timeout')),
        ('dns_error', ('name resolution', 'getaddrinfo')),
        ('parse_error', ('json', 'invalid', 'parse')),
    ):
        if any(marker in errors for marker in markers):
            parts.append(label)
    problems = ' '.join(str(e) for e in health.get('problems', [])).lower()
    for label in ('insufficient observed span', 'quote silence', 'sequence regression',
                  'unverified btc quantity units', 'timestamp regression', 'workers did not stop'):
        if label in problems:
            parts.append(label)
    return '; '.join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args(argv)
    manifests = list(args.root.glob('*/manifest.json'))
    if len(manifests) != 1:
        message = 'No unique session manifest; inspect setup or collection logs and preserve all attempts.'
    else:
        try:
            message = diagnostic(json.loads(manifests[0].read_text()))
        except (OSError, ValueError, TypeError, AttributeError):
            message = 'Unreadable session manifest; inspect the original diagnostic archive.'
    # Every component above is fixed text, a bounded integer, or an allowlisted
    # status/code, so untrusted workflow commands cannot be injected here.
    print('::warning title=Public feed health::' + message)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
