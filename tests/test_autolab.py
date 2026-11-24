"""Restart, dependency and evidence-integrity boundaries of the research lab."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from research.autolab import controller as lab


def plan():
    return {'tasks': [{'id': 'first', 'depends_on': []}, {'id': 'second', 'depends_on': ['first']}],
            'research_queue': []}


class AutolabTests(unittest.TestCase):
    def test_reuses_only_verified_receipts_and_new_inputs_create_new_run(self):
        with TemporaryDirectory() as directory:
            handlers = {'first': Mock(return_value={'n': 1}), 'second': Mock(return_value={'n': 2})}
            store = Path(directory)
            one, state = lab.execute(store, plan(), {'input': 'a'}, handlers)
            self.assertEqual(state['status'], 'COMPLETE')
            two, cached = lab.execute(store, plan(), {'input': 'a'}, handlers)
            self.assertEqual(set(cached['task_modes'].values()), {'VERIFIED_REUSE'})
            self.assertEqual(one, two)
            self.assertEqual(handlers['first'].call_count, 1)
            three, _ = lab.execute(store, plan(), {'input': 'b'}, handlers)
            self.assertNotEqual(one, three)
            self.assertEqual(handlers['first'].call_count, 2)
            self.assertFalse(state['deployment_authorized'])

    def test_failure_blocks_dependents_and_retry_keeps_original_failure(self):
        with TemporaryDirectory() as directory:
            handlers = {'first': Mock(side_effect=ValueError('private token content')), 'second': Mock(return_value={})}
            run, state = lab.execute(Path(directory), plan(), {}, handlers)
            self.assertEqual(state['task_statuses']['second'], 'BLOCKED_DEPENDENCY')
            self.assertNotIn('private token content', (run/'first.1.json').read_text())
            handlers['second'].assert_not_called()
            failed = (run/'first.1.json').read_bytes()
            handlers['first'].side_effect = None
            handlers['first'].return_value = {}
            _, state = lab.execute(Path(directory), plan(), {}, handlers)
            self.assertEqual(state['status'], 'COMPLETE')
            self.assertEqual((run/'first.1.json').read_bytes(), failed)
            self.assertEqual(len(state['attempts']['first']), 2)

    def test_interruption_resumes_completed_tasks(self):
        with TemporaryDirectory() as directory:
            handlers = {'first': Mock(return_value={}), 'second': Mock(side_effect=KeyboardInterrupt)}
            with self.assertRaises(KeyboardInterrupt):
                lab.execute(Path(directory), plan(), {}, handlers)
            self.assertFalse((Path(directory)/'.lock').exists())
            handlers['second'].side_effect = None
            handlers['second'].return_value = {}
            _, state = lab.execute(Path(directory), plan(), {}, handlers)
            self.assertEqual(state['status'], 'COMPLETE')
            self.assertEqual(handlers['first'].call_count, 1)

    def test_corrupt_receipt_and_existing_lock_are_not_silently_reset(self):
        with TemporaryDirectory() as directory:
            store = Path(directory)
            handlers = {'first': lambda p: {}, 'second': lambda p: {}}
            run, _ = lab.execute(store, plan(), {}, handlers)
            (run/'first.1.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'missing or corrupt'):
                lab.execute(store, plan(), {}, handlers)
            (store/'.lock').touch()
            with self.assertRaises(FileExistsError):
                lab.execute(store, plan(), {}, handlers)
            self.assertTrue((store/'.lock').exists())

    def test_nonfinite_results_cannot_pass(self):
        with TemporaryDirectory() as directory:
            _, state = lab.execute(Path(directory), plan(), {},
                                   {'first': lambda p: {'value': float('nan')}, 'second': lambda p: {}})
            self.assertEqual(state['status'], 'FAILED')
            self.assertEqual(state['task_statuses']['second'], 'BLOCKED_DEPENDENCY')

    def test_plan_rejects_unknown_tasks_and_bad_dependencies(self):
        original = lab.load_plan()
        with TemporaryDirectory() as directory:
            path = Path(directory)/'plan.json'
            for kind in ('unknown', 'dependency', 'removed_gate', 'unbounded'):
                changed = json.loads(json.dumps(original))
                if kind == 'unknown':
                    changed['tasks'][0]['id'] = 'shell'
                elif kind == 'dependency':
                    changed['tasks'][0]['depends_on'] = ['execution_mechanics']
                elif kind == 'removed_gate':
                    changed['tasks'][1]['depends_on'] = []
                else:
                    changed['synthetic_cases'] = 100000
                path.write_text(json.dumps(changed))
                with patch.object(lab, 'PLAN', path), self.assertRaises(ValueError):
                    lab.load_plan()

    def test_changed_inputs_during_execution_do_not_complete(self):
        with TemporaryDirectory() as directory:
            inputs = {'input': 'original'}
            def mutate(config):
                inputs['input'] = 'changed'
                return {}
            dependent = Mock(return_value={})
            with self.assertRaisesRegex(ValueError, 'inputs changed during execution'):
                lab.execute(Path(directory), plan(), {'input': 'original'},
                            {'first': mutate, 'second': dependent}, current_bindings=lambda: inputs)
            dependent.assert_not_called()
            journal = next(Path(directory).glob('*/journal.json'))
            self.assertEqual(json.loads(journal.read_text())['status'], 'RUNNING')

    def test_tampered_released_evidence_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for report in lab.REPORTS:
                folder = root/'reports'/report
                folder.mkdir(parents=True)
                (folder/'evidence.json').write_text('{}')
                (folder/'checksums.json').write_text(json.dumps({'evidence.json': '0'*64}))
            with patch.object(lab, 'ROOT', root), self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                lab.released_integrity({})

    def test_actual_evidence_is_verified_and_scope_stays_explicit(self):
        config = lab.load_plan()
        self.assertEqual(lab.frozen_integrity(config)['verified_source_bindings'], 184)
        self.assertEqual(len(lab.released_integrity(config)['verified_files_by_report']), 3)
        results = lab.latency_reproduction(config)
        self.assertEqual(results['overlapping_signals'], 11441)
        self.assertEqual(results['usable_slots'], 22)
        self.assertGreater(results['trace_cells_recomputed'], 0)
        self.assertLess(results['mean_entry_notional_bps_50ms_5bps_per_fill'], 0)
        result = lab.execution_mechanics(config)
        self.assertEqual(result['synthetic_cases'], 1000)
        self.assertEqual(result['market_observations'], 0)
