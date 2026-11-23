import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from research.roadmap.formal_decision import ROOT, compile_decision


class FormalDecisionTests(unittest.TestCase):
    def test_failed_qualification_cannot_become_a_deployment_or_alpha_claim(self):
        source = ROOT / 'reports/formal_decision_20261123'
        mapping = {'original-order-audit.json': 'first-regression-audit.json',
            'long-capture.json': 'result.json', 'short-capture.json': 'pipeline-proof/result.json',
            'restart-diagnostic.json': 'pipeline-proof/restart-diagnostic.json',
            'activity.json': 'faulted-activity-v2/summary.json', 'transport-probe.json': 'transport-probe.json'}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for original, target in mapping.items():
                p = root / target
                p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / original, p)
            result = compile_decision(root, root / 'memo')
            self.assertEqual(result['deployment_decision'], 'DO_NOT_DEPLOY')
            self.assertEqual(result['original_scientific_conclusion'],
                             'inconclusive_missing_coverage_or_precision')
            self.assertEqual(result['incremental_binance_value'], 'UNESTABLISHED')
            self.assertEqual(result['execution_outcomes_computed'], 0)
            self.assertFalse(result['deployment_authorized'])
            p = root / mapping['activity.json']
            invalid = json.loads(p.read_text())
            invalid['execution_outcomes_computed'] = 1
            p.write_text(json.dumps(invalid))
            with self.assertRaisesRegex(ValueError, 'diagnostic scope differs'):
                compile_decision(root, root / 'invalid-memo')


if __name__ == '__main__':
    unittest.main()
