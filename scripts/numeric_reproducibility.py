"""Deterministic scientific outputs plus a standard-library cross-version verifier."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import platform
import subprocess


def fingerprint():
    from scripts.execution_assumption_audit import build
    from scripts.reference_markouts import markouts
    from scripts.crosscheck_markouts import corpus
    from scripts.order_lifecycle import Ledger, scenario_events
    from cel.experiments.precision import summarize_days
    ledger = Ledger()
    for event in scenario_events():
        ledger.apply(event)
    return {'schema_version':1,'python':platform.python_version(),
            'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'values':{'execution':build(),'reference_markouts':markouts(corpus()['buy']),
                      'lifecycle':ledger.snapshot(),
                      'seeded_day_precision':summarize_days([(f'2026-10-{day:02}',float(day%5-2))
                                                            for day in range(1,29)])},
            'scope':'Synthetic numerical agreement, not market evidence or bit-for-bit environment identity.'}


def compare(inputs, *, expected_commit):
    if len(inputs)!=3:
        raise ValueError('exactly three Python-version records required')
    records = [json.loads(path.read_text()) for path in inputs]
    versions = [record['python'].rsplit('.',1)[0] for record in records]
    if set(versions)!={'3.11','3.12','3.13'} or len(set(versions))!=3:
        raise ValueError('one record for each supported Python minor required')
    if any(r['source_commit']!=expected_commit or r['schema_version']!=1 for r in records):
        raise ValueError('numerical artifacts use a different source revision or schema')
    checked = 0
    maximum = 0.
    def walk(a,b,path='values'):
        nonlocal checked, maximum
        if type(a) is not type(b) and not (type(a) in (int,float) and type(b) in (int,float)):
            raise ValueError('numeric artifact type differs: '+path)
        if isinstance(a,dict):
            if set(a)!=set(b):
                raise ValueError('numeric artifact keys differ: '+path)
            for key in a:
                walk(a[key],b[key],path+'.'+key)
        elif isinstance(a,list):
            if len(a)!=len(b):
                raise ValueError('numeric artifact lengths differ: '+path)
            for i,(left,right) in enumerate(zip(a,b)):
                walk(left,right,path+f'[{i}]')
        elif type(a) in (int,float):
            if not math.isfinite(a) or not math.isfinite(b):
                raise ValueError('nonfinite numeric artifact')
            error = abs(a-b)
            maximum = max(maximum,error)
            checked += 1
            if error>1e-9:
                raise ValueError('numerical disagreement: '+path)
        elif a!=b:
            raise ValueError('non-numerical artifact differs: '+path)
    for record in records[1:]:
        walk(records[0]['values'],record['values'])
    return {'passed':True,'source_commit':expected_commit,'python_versions':[r['python'] for r in records],
            'numeric_values_compared':checked,'absolute_tolerance':1e-9,'maximum_absolute_difference':maximum,
            'scope':'Exact structures/strings/booleans and absolute numerical agreement on fixed synthetic outputs.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--compare-root',type=Path)
    parser.add_argument('--expected-commit')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('choose a new output file')
    if args.compare_root:
        if not args.expected_commit:
            parser.error('comparison needs expected source commit')
        result = compare(sorted(args.compare_root.rglob('numeric.json')),expected_commit=args.expected_commit)
    else:
        result = fingerprint()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print('Numeric artifacts compared' if args.compare_root else 'Wrote deterministic numerical fingerprint')


if __name__=='__main__':
    main()
