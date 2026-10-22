"""Prepare and wait on a committed future intent, never infer one from arrival time."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from scripts.successor_claim import instant

PLAN = Path('configs/successor/warm_retry_20261022.json')
PLAN_SHA256 = '3db9a3fe754997cdb46bd3760578a5aa843e1a454880599be54d5138f53d0849'


def load_plan():
    raw = PLAN.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PLAN_SHA256:
        raise ValueError('warm retry plan changed')
    plan = json.loads(raw)
    if not 0 < plan['maximum_warmup_seconds'] <= 3600:
        raise ValueError('unbounded warmup')
    return plan


def prepare(plan, now, attempt):
    delay = (instant(plan['intended_start_utc']) - instant(now)).total_seconds()
    if str(attempt) != '1' or not 0 < delay <= plan['maximum_warmup_seconds']:
        raise ValueError('retry must be prepared before its fixed start on the first attempt')
    return {'plan_sha256':PLAN_SHA256,'intended_start_utc':plan['intended_start_utc'],
            'prepared_at_utc':now,'prepared_seconds_before_start':delay,
            'trigger_method':'prestarted_runner_committed_intent','qualification':'diagnostic_only'}


def wait_until(plan, *, clock=lambda: datetime.now(timezone.utc), sleep=time.sleep):
    # Require the installed runner to be ready before the intended time too.
    ready = clock()
    prepare(plan, ready.isoformat(), '1')
    target = instant(plan['intended_start_utc'])
    while True:
        now = clock()
        delay = (target-now).total_seconds()
        if delay <= 0:
            if -delay > 300:
                raise ValueError('warm runner missed the original start window')
            return {'dependencies_ready_at_utc':ready.isoformat(),'released_at_utc':now.isoformat(),
                    'intended_start_utc':plan['intended_start_utc'],'lateness_seconds':-delay}
        sleep(min(delay,30))


def verify_success(path, *, intended=None):
    receipt = json.loads(path.read_text())
    result = receipt['assessment']
    if receipt.get('remote_restored') is not True or result.get('collection_healthy') is not True or result.get('timing',{}).get('timing_qualified') is not True:
        raise ValueError('retry not successful: require healthy on-time data and remote restore')
    if instant(result['timing']['intended_start_utc']) != instant(intended or load_plan()['intended_start_utc']):
        raise ValueError('retry readback belongs to another intent')
    print('::notice title=Warm collection verified::on_time=True collection_healthy=True remote_restored=True; authenticate cohort separately')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','wait','verify'])
    args=parser.parse_args()
    qualification=os.environ.get('QUALIFICATION_TRIAL')
    if args.command=='verify':
        intended=None
        if qualification:
            from scripts.successor_qualification import trial_for
            intended=trial_for(qualification)[1]['intended_start_utc']
        verify_success(Path('data/raw/successor-attempt/remote-readback.json'),intended=intended)
        return
    if qualification:
        if os.environ.get('GITHUB_ACTOR')!='github-actions[bot]' or os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch':
            raise ValueError('qualification collector requires the automated dispatcher actor')
        from scripts.successor_qualification import PLAN as QPLAN, PLAN_SHA256 as QSHA, prepare_trial, trial_for
        campaign,trial=trial_for(qualification)
        out=Path('data/raw/successor-warmup')
        if args.command=='prepare':
            receipt=prepare_trial(qualification,os.environ['GITHUB_REPOSITORY'],os.environ['GITHUB_SHA'],
                os.environ['GITHUB_RUN_ATTEMPT'],os.environ['QUALIFICATION_INTENDED'],
                os.environ['QUALIFICATION_DISPATCH_ID'],datetime.now(timezone.utc).isoformat())
            out.mkdir(parents=True,exist_ok=False)
            (out/'prepared.json').write_text(json.dumps(receipt,indent=2)+'\n')
            (out/'plan.json').write_bytes(QPLAN.read_bytes())
            with open(os.environ['GITHUB_OUTPUT'],'a') as stream:
                stream.write('warm=true\nintended='+trial['intended_start_utc']+'\n')
        else:
            prepared=json.loads((out/'prepared.json').read_text())
            if prepared['plan_sha256']!=QSHA or prepared['trial_id']!=qualification:
                raise ValueError('qualification preparation differs')
            ready=wait_until(trial | {'maximum_warmup_seconds':campaign['maximum_warmup_seconds']})
            ready.update(plan_sha256=QSHA,trial_id=qualification,dispatch_id=prepared['dispatch_id'])
            (out/'ready.json').write_text(json.dumps(ready,indent=2)+'\n')
        return
    if args.command=='prepare':
        warm=False
        if os.environ.get('GITHUB_EVENT_NAME')=='push':
            changed=subprocess.check_output(['git','diff-tree','--no-commit-id','--name-only','-r','HEAD'],text=True).splitlines()
            warm=str(PLAN) in changed
        with open(os.environ['GITHUB_OUTPUT'],'a') as stream:
            stream.write('warm='+str(warm).lower()+'\n')
            if warm:
                plan=load_plan()
                receipt=prepare(plan,datetime.now(timezone.utc).isoformat(),os.environ['GITHUB_RUN_ATTEMPT'])
                out=Path('data/raw/successor-warmup')
                out.mkdir(parents=True,exist_ok=False)
                (out/'prepared.json').write_text(json.dumps(receipt,indent=2)+'\n')
                (out/'plan.json').write_bytes(PLAN.read_bytes())
                stream.write('intended='+plan['intended_start_utc']+'\n')
        return
    plan=load_plan()
    out=Path('data/raw/successor-warmup')
    prepared=json.loads((out/'prepared.json').read_text())
    if prepared['plan_sha256']!=PLAN_SHA256:
        raise ValueError('prepared plan differs')
    receipt=wait_until(plan)
    (out/'ready.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':
    main()
