"""Dispatch only the three approved UTC intents; cron delivery itself remains unproven."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from uuid import uuid4

from scripts.successor_claim import api, canonical, instant
from scripts.successor_dispatch import dispatch

PLAN = Path('configs/successor/trials_20261020.json')
PLAN_SHA256 = 'fc42e1cd343b22625f44b4c98f88ee0f041159898743597534ba50d96bd93103'
PROTOCOL = Path('configs/successor/protocol.json')


def load_trials():
    raw = PLAN.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PLAN_SHA256:
        raise ValueError('approved trial plan changed; do not move a missed trial')
    plan = json.loads(raw)
    protocol = json.loads(PROTOCOL.read_text())
    if hashlib.sha256(canonical(protocol)).hexdigest() != plan['protocol_sha256']:
        raise ValueError('approved trials refer to another protocol')
    trials = plan['trials']
    if len(trials) != 3 or len({t['trial_id'] for t in trials}) != 3 or len({t['cron'] for t in trials}) != 3:
        raise ValueError('trial identity or cron is ambiguous')
    for trial in trials:
        intended = instant(trial['intended_start_utc'])
        expected = f'{intended.minute} {intended.hour} {intended.day} {intended.month} *'
        if expected != trial['cron'] or intended.microsecond or intended.second:
            raise ValueError('cron differs from explicit intended UTC instant')
    return plan, protocol


def select_trial(plan, cron, now, tolerance):
    matches = [trial for trial in plan['trials'] if trial['cron'] == cron]
    if len(matches) != 1:
        raise ValueError('unknown scheduled intent')
    trial = matches[0]
    delay = (instant(now)-instant(trial['intended_start_utc'])).total_seconds()
    return trial, 0 <= delay <= tolerance, delay


def reserve_request(repository, plan, trial, source, owner, *, request=api):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('invalid repository')
    if not re.fullmatch(r'[0-9a-f]{40}',source) or not re.fullmatch(r'[1-9][0-9]*-[1-9][0-9]*',owner):
        raise ValueError('invalid source or request owner')
    if not owner.endswith('-1'):
        raise ValueError('approved request reruns are not permitted')
    body = {'plan_sha256':PLAN_SHA256,'trial_id':trial['trial_id'],
            'intended_start_utc':trial['intended_start_utc'],'source_commit':source,'owner':owner,
            'dispatch_id':uuid4().hex}
    parent = request(f'repos/{repository}/git/commits/{source}')
    commit = request(f'repos/{repository}/git/commits',{
        'message':'Approved successor dispatch\n'+canonical(body).decode(),
        'tree':parent['tree']['sha'],'parents':[source]})
    ref = 'refs/tags/successor-dispatches/'+plan['plan_id']+'/'+trial['trial_id']
    result = request(f'repos/{repository}/git/refs',{'ref':ref,'sha':commit['sha']})
    if result.get('ref') != ref or result.get('object',{}).get('sha') != commit['sha']:
        raise ValueError('dispatch request ownership not established')
    return body | {'request_ref':ref,'request_commit':commit['sha']}


def authenticate_request(repository, trial, dispatch_id, *, request=api):
    """Verify that this receipt ID came from the approved scheduled parent, not a manual substitute."""
    if not dispatch_id or not re.fullmatch(r'[0-9a-f]{32}',dispatch_id):
        return False
    plan, _ = load_trials()
    ref = 'tags/successor-dispatches/'+plan['plan_id']+'/'+trial['trial_id']
    target = request(f'repos/{repository}/git/ref/{ref}')
    commit = request(f'repos/{repository}/git/commits/{target["object"]["sha"]}')
    prefix = 'Approved successor dispatch\n'
    if not commit.get('message','').startswith(prefix):
        return False
    body = json.loads(commit['message'][len(prefix):])
    if (body.get('plan_sha256') != PLAN_SHA256 or body.get('trial_id') != trial['trial_id'] or
            body.get('intended_start_utc') != trial['intended_start_utc'] or body.get('dispatch_id') != dispatch_id or
            not re.fullmatch(r'[1-9][0-9]*-[1-9][0-9]*',body.get('owner',''))):
        return False
    owner, attempt = body['owner'].split('-')
    parent = request(f'repos/{repository}/actions/runs/{owner}/attempts/{attempt}')
    return (parent.get('event') == 'schedule' and parent.get('head_branch') == 'main' and
            parent.get('path') == '.github/workflows/successor-planned-trials.yml' and
            parent.get('head_sha') == body.get('source_commit') and parent.get('conclusion') == 'success' and
            (parent.get('head_repository') or {}).get('full_name','').lower() == repository.lower())


def planned_status(records, *, now):
    plan, protocol = load_trials()
    rows = []
    for trial in plan['trials']:
        intended = instant(trial['intended_start_utc'])
        matching = [r for r in records if r.get('intended_start_utc') and
                    instant(r['intended_start_utc']) == intended and r.get('event') == 'workflow_dispatch']
        state = 'awaiting_verified_archive' if instant(now) <= intended + timedelta(
            seconds=protocol['maximum_start_lateness_seconds'] + protocol['recording_seconds'] + 300) else 'overdue_without_verified_archive'
        if len(matching) > 1:
            state = 'ambiguous'
        elif matching:
            row = matching[0]
            passed = (row.get('planned_request_verified') is True and
                      row.get('authenticated_remote_restore') is True and
                      row.get('qualification_compatible',True) is True and
                      row.get('source_run_conclusion') == 'success' and
                      row.get('assessment',{}).get('collection_healthy') is True and
                      row.get('assessment',{}).get('timing',{}).get('timing_qualified') is True)
            state = 'qualified' if passed else 'not_qualified'
        rows.append(trial | {'state':state})
    return {'plan_id':plan['plan_id'],'plan_sha256':PLAN_SHA256,'trials':rows,
            'all_named_trials_qualified':all(row['state']=='qualified' for row in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate',action='store_true')
    parser.add_argument('--cron')
    parser.add_argument('--repository')
    parser.add_argument('--owner')
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    plan, protocol = load_trials()
    args.out.mkdir(parents=True,exist_ok=False)
    (args.out/'approved-plan.json').write_bytes(PLAN.read_bytes())
    if args.validate:
        for trial in plan['trials']:
            print(f'::notice title=Approved prospective trial::{trial["trial_id"]} intended_utc={trial["intended_start_utc"]}')
        return 0
    now = datetime.now(timezone.utc).isoformat()
    trial, accepted, delay = select_trial(plan,args.cron,now,protocol['maximum_start_lateness_seconds'])
    result = {'plan_sha256':PLAN_SHA256,'trial':trial,'gate_checked_at_utc':now,
              'lateness_seconds':delay,'gate_accepted':accepted,'request_acknowledged':False,
              'collection_verified':False,'delivery_error_category':None}
    if accepted:
        try:
            source = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
            receipt = reserve_request(args.repository,plan,trial,source,args.owner)
            (args.out/'request-owner.json').write_text(json.dumps(receipt,indent=2)+'\n')
            # The one-shot dispatcher checks the window again after ownership acquisition.
            result['request_acknowledged'] = dispatch(args.repository,trial['intended_start_utc'],args.out/'dispatch.jsonl',dispatch_id=receipt['dispatch_id'])
        except Exception as exc:
            # Retain the failed/uncertain request, never expose a raw API body or retry.
            result['delivery_error_category'] = type(exc).__name__
    (args.out/'delivery.json').write_text(json.dumps(result,indent=2)+'\n')
    if not accepted:
        print('::warning title=Prospective trial delivery::Late, early or stale-year cron; no request submitted and no retry performed')
        return 0
    print('::notice title=Prospective trial delivery::request_acknowledged='+str(result['request_acknowledged'])+'; collection_verified=False')
    return 0 if result['request_acknowledged'] else 1


if __name__=='__main__':
    raise SystemExit(main())
