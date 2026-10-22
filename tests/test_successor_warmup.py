from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.successor_claim import instant
from scripts.successor_warmup import load_plan, prepare, wait_until, verify_success


class WarmRetryTests(unittest.TestCase):
    def test_only_first_attempt_and_future_bounded_intent_can_prepare(self):
        plan=load_plan()
        start=instant(plan['intended_start_utc'])
        for seconds,attempt,allowed in [(1,'1',True),(3600,'1',True),(3601,'1',False),(0,'1',False),(-1,'1',False),(60,'2',False)]:
            now=(start-timedelta(seconds=seconds)).isoformat()
            if allowed:
                receipt=prepare(plan,now,attempt)
                self.assertEqual(receipt['intended_start_utc'],plan['intended_start_utc'])
                self.assertEqual(receipt['prepared_seconds_before_start'],seconds)
            else:
                with self.assertRaises(ValueError):
                    prepare(plan,now,attempt)

    def test_preinstalled_runner_waits_for_original_time_in_bounded_chunks(self):
        plan=load_plan()
        start=instant(plan['intended_start_utc'])
        current=[start-timedelta(seconds=65)]
        sleeps=[]
        def sleep(seconds):
            sleeps.append(seconds)
            current[0]+=timedelta(seconds=seconds)
        receipt=wait_until(plan,clock=lambda:current[0],sleep=sleep)
        self.assertEqual(sleeps,[30,30,5])
        self.assertEqual(receipt['lateness_seconds'],0)
        self.assertEqual(receipt['intended_start_utc'],plan['intended_start_utc'])

    def test_sleep_overshoot_is_failure_not_a_new_intent(self):
        plan=load_plan()
        start=instant(plan['intended_start_utc'])
        clock=iter([start-timedelta(seconds=1),start+timedelta(seconds=301)])
        with self.assertRaisesRegex(ValueError,'missed the original'):
            wait_until(plan,clock=lambda:next(clock),sleep=lambda _:None)

    def test_tampered_plan_is_rejected(self):
        with patch.object(Path,'read_bytes',return_value=b'{}'):
            with self.assertRaisesRegex(ValueError,'plan changed'):
                load_plan()

    def test_green_backup_without_healthy_on_time_data_is_not_success(self):
        plan=load_plan()
        result={'remote_restored':True,'assessment':{'collection_healthy':True,'timing':{'timing_qualified':True,'intended_start_utc':plan['intended_start_utc']}}}
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'readback.json'
            path.write_text(json.dumps(result))
            verify_success(path)
            result['assessment']['collection_healthy']=False
            path.write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,'not successful'):
                verify_success(path)
            result['assessment']['collection_healthy']=True
            result['assessment']['timing']['intended_start_utc']='2026-10-20T03:17:00Z'
            path.write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,'another intent'):
                verify_success(path)
