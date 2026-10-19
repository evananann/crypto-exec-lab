from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.successor_trials import load_trials, select_trial, reserve_request, planned_status
from test_successor import FakeGitHub


class ApprovedTrialTests(unittest.TestCase):
    def test_approved_instants_match_three_promised_shanghai_times(self):
        from zoneinfo import ZoneInfo
        from scripts.successor_claim import instant
        plan, _ = load_trials()
        local = [instant(t['intended_start_utc']).astimezone(ZoneInfo('Asia/Shanghai')).isoformat() for t in plan['trials']]
        self.assertEqual(local,['2026-10-20T11:17:00+08:00','2026-10-20T23:17:00+08:00','2026-10-21T11:17:00+08:00'])

    def test_late_am_cron_cannot_become_pm_or_next_year_trial(self):
        plan, protocol = load_trials()
        for now, allowed in [('2026-10-20T03:16:59Z',False),('2026-10-20T03:17:00Z',True),
                             ('2026-10-20T03:22:00Z',True),('2026-10-20T03:22:01Z',False),
                             ('2026-10-20T15:17:00Z',False),('2027-10-20T03:17:00Z',False)]:
            trial, accepted, _ = select_trial(plan,'17 3 20 10 *',now,protocol['maximum_start_lateness_seconds'])
            self.assertEqual(trial['trial_id'],'oct20-am')
            self.assertIs(accepted,allowed)

    def test_concurrent_request_owners_cannot_both_submit(self):
        plan, _ = load_trials()
        api = FakeGitHub()
        def compete(owner):
            try:
                return reserve_request('owner/repo',plan,plan['trials'][0],'a'*40,owner,request=api)
            except RuntimeError:
                return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(compete,['100-1','101-1']))
        self.assertEqual(sum(result is not None for result in results),1)
        self.assertEqual(len(api.refs),1)
        self.assertIn('refs/tags/successor-dispatches/successor-qualification-20261020/oct20-am',api.refs)

    def test_missed_trial_remains_overdue_without_fabricating_an_attempt(self):
        result=planned_status([],now='2026-10-20T04:00:00Z')
        self.assertEqual([t['state'] for t in result['trials']],['overdue_without_verified_archive','awaiting_verified_archive','awaiting_verified_archive'])
        self.assertFalse(result['all_named_trials_qualified'])

    def test_matching_dates_and_every_named_trial_required(self):
        plan,_=load_trials()
        records=[{'event':'workflow_dispatch','intended_start_utc':t['intended_start_utc'],
                  'authenticated_remote_restore':True,'qualification_compatible':True,'planned_request_verified':True,
                  'source_run_conclusion':'success','assessment':{'collection_healthy':True,'timing':{'timing_qualified':True}}}
                 for t in plan['trials']]
        self.assertTrue(planned_status(records,now='2026-10-21T04:00:00Z')['all_named_trials_qualified'])
        records[0]['intended_start_utc']='2026-10-19T03:17:00Z'
        result=planned_status(records,now='2026-10-21T04:00:00Z')
        self.assertFalse(result['all_named_trials_qualified'])
        self.assertEqual(result['trials'][0]['state'],'overdue_without_verified_archive')

    def test_changed_plan_rejected_before_any_dispatch(self):
        with patch.object(Path,'read_bytes',return_value=b'{}'):
            with self.assertRaisesRegex(ValueError,'approved trial plan changed'):
                load_trials()

    def test_source_bundle_binds_trial_plan_and_scheduled_workflow(self):
        from scripts.successor_rehearsal import source_identity
        with patch('scripts.successor_rehearsal.subprocess.check_output',side_effect=['a'*40+'\n','']):
            files=source_identity()['files_sha256']
        self.assertIn('configs/successor/trials_20261020.json',files)
        self.assertIn('.github/workflows/successor-planned-trials.yml',files)

    def test_late_job_records_warning_without_reserving_or_dispatching(self):
        from scripts.successor_trials import main
        import sys
        with TemporaryDirectory() as tmp:
            args=['successor_trials','--cron','17 3 20 10 *','--repository','owner/repo','--owner','1-1','--out',str(Path(tmp)/'receipt')]
            with patch.object(sys,'argv',args),patch('scripts.successor_trials.select_trial',return_value=({'trial_id':'oct20-am'},False,10000)),patch('scripts.successor_trials.reserve_request') as reserve,patch('scripts.successor_trials.dispatch') as send:
                self.assertEqual(main(),0)
                reserve.assert_not_called()
                send.assert_not_called()
            result=json.loads((Path(tmp)/'receipt'/'delivery.json').read_text())
            self.assertFalse(result['request_acknowledged'])

    def test_uncertain_request_is_written_and_not_retried(self):
        from scripts.successor_trials import main
        import sys
        plan,_=load_trials()
        with TemporaryDirectory() as tmp:
            out=Path(tmp)/'receipt'
            args=['successor_trials','--cron','17 3 20 10 *','--repository','owner/repo','--owner','1-1','--out',str(out)]
            with patch.object(sys,'argv',args),patch('scripts.successor_trials.select_trial',return_value=(plan['trials'][0],True,1)),patch('scripts.successor_trials.reserve_request',side_effect=RuntimeError('uncertain response')) as reserve,patch('scripts.successor_trials.dispatch') as send:
                self.assertEqual(main(),1)
                reserve.assert_called_once()
                send.assert_not_called()
            result=json.loads((out/'delivery.json').read_text())
            self.assertEqual(result['delivery_error_category'],'RuntimeError')
            self.assertFalse(result['request_acknowledged'])

    def test_parent_request_id_must_match_successful_scheduled_main_run(self):
        from scripts.successor_trials import authenticate_request
        plan,_=load_trials()
        api=FakeGitHub()
        receipt=reserve_request('owner/repo',plan,plan['trials'][0],'a'*40,'100-1',request=api)
        parent={'event':'schedule','head_branch':'main','path':'.github/workflows/successor-planned-trials.yml',
                'head_sha':'a'*40,'conclusion':'success','head_repository':{'full_name':'owner/repo'}}
        def request(endpoint):
            return parent if '/actions/runs/' in endpoint else api(endpoint)
        self.assertTrue(authenticate_request('owner/repo',plan['trials'][0],receipt['dispatch_id'],request=request))
        self.assertFalse(authenticate_request('owner/repo',plan['trials'][0],'f'*32,request=request))
        parent['event']='workflow_dispatch'
        self.assertFalse(authenticate_request('owner/repo',plan['trials'][0],receipt['dispatch_id'],request=request))

    def test_manual_success_on_same_date_does_not_prove_scheduled_delivery(self):
        plan,_=load_trials()
        records=[{'event':'workflow_dispatch','intended_start_utc':t['intended_start_utc'],
                  'authenticated_remote_restore':True,'qualification_compatible':True,
                  'source_run_conclusion':'success','assessment':{'collection_healthy':True,'timing':{'timing_qualified':True}}}
                 for t in plan['trials']]
        self.assertFalse(planned_status(records,now='2026-10-21T04:00:00Z')['all_named_trials_qualified'])

    def test_manual_rerun_cannot_initiate_another_request(self):
        plan,_=load_trials()
        with patch('scripts.successor_trials.api') as api:
            with self.assertRaisesRegex(ValueError,'reruns'):
                reserve_request('owner/repo',plan,plan['trials'][0],'a'*40,'100-2',request=api)
            api.assert_not_called()
