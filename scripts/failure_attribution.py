"""Conservative, health-only attribution from checksum-verified study archives.

Preserves observations and unknown causes. Does not evaluate market outcomes,
contact exchanges, or infer an exchange outage from silence or HTTP status.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import tarfile

from cel.artifacts import file_sha256
from cel.study import load_plan, verify_archive
from scripts.study_monitor import PLANS


def classify(manifest, metadata=None, *, metadata_name='recorder metadata'):
    observations = []
    def add(code, layer, ref):
        observations.append({'code':code, 'observed_layer':layer, 'evidence_ref':ref})
    sources = [('manifest.json',manifest)]
    if metadata is not None:
        sources.append((metadata_name,metadata))
    for source, data in sources:
        errors = data.get('errors',[])
        if not isinstance(errors,list) or any(not isinstance(e,str) for e in errors):
            raise ValueError('diagnostic errors must be a list of strings')
        for i, error in enumerate(errors):
            text = error.lower()
            ref = source+f'#/errors/{i}'
            # Explicit CONNECT/tunnel language is needed to attribute the
            # observed rejection to the proxy path. Generic 403 is insufficient.
            if ('403' in text and ('failed connect via proxy' in text or
                                    'tunnel connection failed' in text)):
                add('proxy_connect_rejected','network_proxy',ref)
            elif '403' in text:
                add('http_403_origin_unknown','access_path_unknown',ref)
            elif 'timed out' in text or 'timeout' in text:
                add('timeout_origin_unknown','unknown',ref)
            elif 'certificate verify failed' in text or 'certificate_verify_failed' in text:
                add('tls_verification_failed','tls_path_unknown',ref)
            elif error:
                add('unclassified_recorded_error','unknown',ref)
    if metadata is not None and metadata.get('workers_still_running'):
        add('recorder_workers_not_stopped','recorder_shutdown',metadata_name+'#/workers_still_running')
    health = manifest.get('health') or {}
    for i, problem in enumerate(health.get('problems',[])):
        text = str(problem).lower()
        code = ('sequence_regression' if 'sequence regression' in text else
                'quantity_units_unverified' if 'quantity' in text or 'units' in text else
                'insufficient_observed_span' if 'insufficient observed span' in text else
                'quote_silence' if 'quote silence' in text else 'other_health_gate_failure')
        add(code,'collection_quality',f'manifest.json#/health/problems/{i}')
    return {'observations':observations,
            'observed_layers':sorted({o['observed_layer'] for o in observations}),
            'root_cause':'unknown',
            'failure_evidence':'recorded' if observations else 'none in supplied diagnostics',
            'interpretation':'Observed failure layer or symptom only. Underlying policy, provider, exchange, scheduler and code causes remain unproven; no outage or successful-sample inference.'}


def inspect(source):
    archives = sorted(source.rglob('*.tar.gz'))
    if not archives:
        raise ValueError('no archives found')
    known = {}
    for path in PLANS:
        plan, _ = load_plan(path)
        known[file_sha256(path)] = plan['study_id']
    records = []
    for path in archives:
        item = verify_archive(path)
        if (item['plan_sha256'] not in known or
                item['files'].get('plan.json') != item['plan_sha256']):
            raise ValueError('unrecognized frozen plan or archived-plan binding')
        identifier = item['session_id']
        if not re.fullmatch(r'(?:preflight-\d{8}T\d{6,12}Z|\d{4}-\d{2}-\d{2}-(?:am|pm))',identifier):
            raise ValueError('unrecognized session identifier')
        with tarfile.open(path,'r:gz') as archive:
            names = [n for n in archive.getnames() if n.endswith('.meta.json')]
            if len(names)>1:
                raise ValueError('ambiguous recorder metadata')
            metadata = None
            if names:
                if archive.getmember(names[0]).size>1_000_000:
                    raise ValueError('recorder metadata exceeds diagnostic size limit')
                metadata = json.load(archive.extractfile(names[0]))
        records.append({'study_id':known[item['plan_sha256']], 'session_id':identifier,
                        'archive_sha256':file_sha256(path), 'original_status':item['status'],
                        'plan_sha256':item['plan_sha256'], 'collector_commit':item.get('collector_commit'),
                        'collector_dirty':item.get('collector_dirty'),
                        'phase':item['phase'], 'metadata_available':metadata is not None,
                        'recorded_event_count':(item.get('health') or {}).get('events'),
                        'attribution':classify(item,metadata,metadata_name=names[0] if names else 'recorder metadata')})
    counts = Counter(code for row in records for code in row['attribution']['observed_layers'])
    return {'schema_version':1,'as_of_utc':datetime.now(timezone.utc).isoformat(),
            'script_sha256':file_sha256(Path(__file__)),'archives_verified':len(records),
            'archives_by_observed_layer':dict(sorted(counts.items())), 'records':records,
            'scope':'Archive digests and diagnostic metadata only. Raw error strings, prices, markouts and PnL are not emitted. Multiple symptoms and unknown root causes are retained.',
            'coverage_limitation':'This is an archive inventory, not the planned-slot inventory. Missing runs/artifacts have no archive to attribute; use the operations monitor and preserve unknown cause.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.resolve().is_relative_to(args.source.resolve()):
        parser.error('choose output outside the archive evidence source')
    result=inspect(args.source)
    args.out.mkdir(parents=True,exist_ok=False)
    (args.out/'attribution.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# Observed failure layers','',
           'Underlying root causes remain unknown unless established by separate evidence.','',
           '| Study | Session | Original status | Observed layers |', '| --- | --- | --- | --- |']
    for row in result['records']:
        layers=', '.join(row['attribution']['observed_layers']) or 'none in supplied diagnostics'
        lines.append(f"| {row['study_id']} | {row['session_id']} | {row['original_status']} | {layers} |")
    lines+=['',result['coverage_limitation']]
    (args.out/'attribution.md').write_text('\n'.join(lines)+'\n')
    print(f"Verified {result['archives_verified']} archives; retained observations and unknown root causes")


if __name__=='__main__':
    main()
