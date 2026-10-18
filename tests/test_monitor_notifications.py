from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import study_monitor as monitor


def state(*states, inventory=True):
    return {'as_of_utc':'2026-10-18T06:30:00+00:00',
            'inventory_available':inventory, 'scope':'Collection health only',
            'healthy':all(s in ('pending','running','eligible') for s in states) and inventory,
            'sessions':[{'study_id':'btc-execution-v1','session':f'2026-10-17-{i}',
                         'state':s,'run_url':None} for i,s in enumerate(states)],
            'counts':{s:states.count(s) for s in set(states)},'retention':[],
            'alerts':(['Artifact inventory unavailable'] if not inventory else [])+
                     [f'Collection state: {s}' for s in states if s not in ('pending','running','eligible')]}


class MonitorNotificationTests(unittest.TestCase):
    def test_missing_and_failed_collection_remain_unhealthy_without_failed_workflow(self):
        for status in ('missing','blocked','ineligible','expired'):
            report=state(status)
            before=deepcopy(report)
            self.assertEqual(monitor.exit_status(report,coverage_warnings=True),0)
            self.assertEqual(monitor.exit_status(report),1)
            self.assertEqual(report,before)
            self.assertFalse(report['healthy'])

    def test_inventory_or_verification_failures_still_fail(self):
        for status in ('unverified','ambiguous','overdue_running','unexpected_state'):
            self.assertEqual(monitor.exit_status(state(status),coverage_warnings=True),1)
        self.assertEqual(monitor.exit_status(state('pending',inventory=False),coverage_warnings=True),1)
        self.assertEqual(monitor.exit_status(state('missing','unverified'),coverage_warnings=True),1)

    def test_healthy_run_succeeds_and_retention_only_is_warning(self):
        report=state('pending','eligible')
        self.assertEqual(monitor.exit_status(report),0)
        report.update(healthy=False,alerts=['1 artifact expires soon'],retention=[{'artifact_id':1}])
        self.assertEqual(monitor.exit_status(report,coverage_warnings=True),0)
        self.assertEqual(monitor.exit_status(report),1)

    def run_cli(self, report, *, warnings):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        args=['--repository','evananann/crypto-exec-lab','--out',str(root/'out'),
              '--summary',str(root/'job-summary.md')]
        if warnings:
            args.append('--coverage-warnings')
        output=io.StringIO()
        with patch.object(monitor,'inspect',return_value=report),redirect_stdout(output):
            status=monitor.main(args)
        return status,output.getvalue(),root

    def test_automated_warning_cli_preserves_data_and_prominent_alerts(self):
        report=state('missing','missing')
        status,output,root=self.run_cli(report,warnings=True)
        self.assertEqual(status,0)
        self.assertIn('::warning title=Study operations::',output)
        self.assertNotIn('::error',output)
        self.assertEqual(json.loads((root/'out/status.json').read_text()),report)
        self.assertIn('Collection health: ALERT',(root/'job-summary.md').read_text())
        self.assertIn('Collection health: ALERT',(root/'out/dashboard.html').read_text())
        self.assertIn('missing',(root/'out/summary.md').read_text())

    def test_strict_cli_and_verification_errors_keep_nonzero_exit_and_error_annotations(self):
        for report,warnings in [(state('missing'),False),(state('unverified'),True),
                                (state('pending',inventory=False),True)]:
            status,output,root=self.run_cli(report,warnings=warnings)
            self.assertEqual(status,1)
            self.assertIn('::error title=Study operations::',output)
            self.assertTrue((root/'out/status.json').exists())

    def test_inspection_crash_is_not_silenced(self):
        with TemporaryDirectory() as temp,patch.object(monitor,'inspect',side_effect=RuntimeError('broken monitor')):
            with self.assertRaisesRegex(RuntimeError,'broken monitor'):
                monitor.main(['--repository','evananann/crypto-exec-lab','--out',temp+'/out','--coverage-warnings'])
