"""Streaming, byte-preserving diagnosis of recorded timestamp order."""

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil

from research.continuous_capture import strict_json


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def scan(path, *, example_limit=8):
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular original tape required')
    before = sha256(path)
    counts, transitions = Counter(), Counter()
    previous, per_stream, examples = {}, {}, []
    offset = 0
    opener = gzip.open if path.name.endswith('.gz') else open
    with opener(path, 'rb') as stream:
        for line_number, line in enumerate(stream, 1):
            start = offset
            offset += len(line)
            if not line.strip():
                continue
            row = strict_json(line)
            counts['records'] += 1
            fields = [name for name in ('local_ts', 'receive_monotonic_ns',
                                        'writer_start_monotonic_ns') if name in row]
            identity = '/'.join(str(row.get(k, 'unknown')) for k in
                                ('venue', 'feed', 'capture_session_id', 'connection_id', 'kind'))
            trace = {'line_1based': line_number, 'uncompressed_byte_offset': start,
                     'identity': identity,
                     'record': {k: row[k] for k in ('venue', 'feed', 'kind', 'local_ts',
                        'exchange_ts', 'seq', 'receive_monotonic_ns', 'writer_start_monotonic_ns',
                        'capture_session_id', 'connection_id') if k in row}}
            for field in fields:
                stamp = row[field]
                if type(stamp) is not int or stamp < 0:
                    raise ValueError('nonnegative integer timestamp required')
                old = previous.get(field)
                if old is not None and stamp < old['record'][field]:
                    counts[field + '_adjacent_regressions'] += 1
                    transitions[old['identity'] + ' -> ' + identity] += 1
                    if len(examples) < example_limit:
                        examples.append({'field': field, 'backward_amount': old['record'][field] - stamp,
                                         'unit': 'ms' if field == 'local_ts' else 'ns',
                                         'previous': old, 'current': trace})
                key = (field, identity)
                if key in per_stream and stamp < per_stream[key]:
                    counts[field + '_same_stream_regressions'] += 1
                previous[field], per_stream[key] = trace, stamp
    if sha256(path) != before:
        raise ValueError('input changed during diagnosis')
    return {'source_sha256': before, 'source_bytes': path.stat().st_size,
            'counts': dict(counts), 'regressing_transitions': dict(transitions),
            'first_examples': examples, 'original_bytes_unchanged': True,
            'scope': 'Recorded order only. No sorting, inferred clock repair or statistical outcomes.',
            'causal_identification': 'Legacy events have no callback/parse/write timestamps. '
             'Cross-thread overtaking is compatible with regressions, but an individual cause '
             'cannot be established from event timestamps alone.'}


def released_first(cache, out, *, until_regression=False):
    # Original release/source gates precede archive listing or traversal.
    from research.empirical_note import current_plan
    from scripts.successor_study import download_verified
    plan = current_plan(datetime.now(timezone.utc))
    if plan is None:
        raise ValueError('original outcomes remain release gated')
    cache.mkdir(parents=True, exist_ok=False)
    inventory, audited = [], []
    with closing(download_verified(plan, 'evananann/crypto-exec-lab', cache)) as originals:
        for original in originals:
            inventory.append({k: v for k, v in original.items() if k != 'tape'})
            if original['eligible']:
                tape = Path(original['tape'])
                result = scan(tape)
                audited.append({'slot_id': original['slot_id'], 'source_sha256': result['source_sha256'],
                                'counts': result['counts']})
                if until_regression and not result['first_examples']:
                    continue
                result.update(original=inventory[-1], inventory_before_selection=inventory,
                              audited_eligible=audited,
                              selection='Chronological eligible originals through the first regression' if until_regression
                              else 'Earliest eligible original slot; deterministic diagnostic sample, not a cohort estimate.')
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
                shutil.copyfile(tape, cache / 'original-diagnostic-tape.jsonl')
                return result
    raise ValueError('no eligible original archive available')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--path', type=Path)
    mode.add_argument('--released-first-cache', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--until-regression', action='store_true')
    args = p.parse_args()
    if args.out.exists():
        p.error('refuse to overwrite diagnostic evidence')
    if args.path:
        args.out.write_text(json.dumps(scan(args.path), indent=2) + '\n')
    else:
        released_first(args.released_first_cache, args.out, until_regression=args.until_regression)
