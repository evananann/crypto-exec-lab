"""Read-only run/job/gate evidence; never infer a missing cron or dispatch input."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from cel.study import load_plan
from scripts.study_monitor import PLANS, api_json

WORKFLOWS = {'live-study.yml':'frozen live study', 'replication-study.yml':'preregistered replication collection'}
GATES = {'Check fixed study dates and slot before installing','Enforce this pair\'s frozen UTC window'}
COLLECT = {'Collect one session without inspecting holdout outcomes','Record without inspecting outcomes'}


def instant(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)


def run_evidence(run, jobs, repository):
    if (run.get('head_branch') != 'main' or run.get('path') not in
            {'.github/workflows/'+name for name in WORKFLOWS} or
            run.get('event') not in ('push','schedule','workflow_dispatch') or
            (run.get('head_repository') or {}).get('full_name','').lower() != repository.lower() or
            type(run.get('id')) is not int or run['id'] <= 0):
        raise ValueError('untrusted collection run')
    created, started = run.get('created_at'), run.get('run_started_at')
    delay = (instant(started)-instant(created)).total_seconds() if started and created else None
    if delay is not None and delay < 0:
        raise ValueError('run starts before creation')
    summaries = []
    for job in jobs:
        gate = [{'name':s['name'],'conclusion':s.get('conclusion')} for s in (job.get('steps') or []) if s.get('name') in GATES]
        collect = [{'name':s['name'],'conclusion':s.get('conclusion')} for s in (job.get('steps') or []) if s.get('name') in COLLECT]
        summaries.append({'job_id':job['id'],'name':job['name'], 'status':job.get('status'),
                          'conclusion':job.get('conclusion'),'started_at':job.get('started_at'),
                          'completed_at':job.get('completed_at'),'gate_steps':gate,'collection_steps':collect,
                          'collection_observation':('not executed: collection step skipped' if collect and
                              all(s['conclusion']=='skipped' for s in collect) else
                              'collection step completed' if any(s['conclusion']=='success' for s in collect) else
                              'not established from available steps')})
    return {'run_id':run['id'],'run_url':f'https://github.com/{repository}/actions/runs/{run["id"]}',
            'event':run['event'],'created_at':created,'run_started_at':started,
            'creation_to_run_start_seconds':delay,'conclusion':run.get('conclusion'),
            'source_commit':run.get('head_sha'),'run_attempt':run.get('run_attempt'),'jobs':summaries,
            'intended_cron_or_dispatch_slot':'unknown: not exposed by run metadata',
            'root_cause':'unknown',
            'limitation':'Creation-to-start excludes any delay before GitHub created the run. A successful gate step is not its output. A completed collection step still needs a verified archive.'}


def inspect(repository):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('invalid repository')
    for path in PLANS:
        load_plan(path)
    records = []
    for workflow in WORKFLOWS:
        # The studies have bounded dates and a short run history. Bound API
        # cost explicitly; do not describe this as a complete historical crawl.
        data = api_json(f'repos/{repository}/actions/workflows/{workflow}/runs?branch=main&per_page=100')
        for run in data['workflow_runs']:
            pages = api_json(f'repos/{repository}/actions/runs/{run["id"]}/jobs?filter=latest&per_page=100',paginate=True)
            jobs = [job for page in pages for job in page['jobs']]
            records.append(run_evidence(run,jobs,repository))
    return {'schema_version':1,'as_of_utc':datetime.now(timezone.utc).isoformat(),
            'repository':repository,'runs':records,'coverage':'Latest 100 main runs per collector workflow; latest-attempt jobs only.',
            'scope':'Trigger, timing and job-step metadata only. No logs, raw errors, prices or outcomes.'}


def demo():
    return {'schema_version':1,'synthetic':True,'runs':[run_evidence(
        {'id':7,'head_branch':'main','head_repository':{'full_name':'owner/repo'},
         'path':'.github/workflows/live-study.yml','event':'schedule','head_sha':'a'*40,
         'created_at':'2026-10-17T17:51:00Z','run_started_at':'2026-10-17T17:51:05Z','conclusion':'success'},
        [{'id':8,'name':'collect','steps':[{'name':next(iter(sorted(GATES))),'conclusion':'success'},
          {'name':'Collect one session without inspecting holdout outcomes','conclusion':'skipped'}]}],'owner/repo')]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--repository')
    mode.add_argument('--demo',action='store_true')
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    result = demo() if args.demo else inspect(args.repository)
    if args.out.exists():
        parser.error('choose a new output file')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    for record in sorted(result['runs'],key=lambda r:r['run_id'],reverse=True)[:10]:
        skipped = sum(job['collection_observation'].startswith('not executed:') for job in record['jobs'])
        print(f'::notice title=Collection timeline::run={record["run_id"]} event={record["event"]} collection_steps_skipped={skipped} creation_to_start_seconds={record["creation_to_run_start_seconds"]}')
    print(f'Published {len(result["runs"])} trigger/job timelines; unknown causes retained')


if __name__=='__main__':
    main()
