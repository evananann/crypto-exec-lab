"""Daily raw cohorts and fixed controls use explicitly synthetic recordings."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import gzip
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.autolab import cohort, secondary, paired_review
from research.autolab import controller as lab
from research.autolab.qualification import digest, load_hypothesis, HYPOTHESIS
from tests import test_raw_replay as recordings


def retime_synthetic(spool, days):
    # Fixture construction only: no production timestamp repair exists.
    for segment in spool.glob('*.jsonl.gz'):
        with gzip.open(segment, 'rt') as stream:
            rows = [json.loads(line) for line in stream]
        for row in rows:
            row['local_utc_ns'] += days*86400*10**9
        with gzip.open(segment, 'wt') as stream:
            for row in rows:
                stream.write(json.dumps(row)+'\n')
        path = spool/(segment.name.removesuffix('.jsonl.gz')+'.manifest.json')
        metadata = json.loads(path.read_text())
        metadata['sha256'] = digest(segment)
        path.write_text(json.dumps(metadata))


def fixture(root, *, total_days=2, captured=(0, 1)):
    hypothesis = load_hypothesis()
    value = {'schema_version': 1, 'hypothesis_sha256': digest(HYPOTHESIS),
             'design_sha256': hypothesis['design_sha256'],
             'calendar': [(date(2030, 1, 1)+timedelta(days=i)).isoformat() for i in range(total_days)], 'captures': []}
    for day in captured:
        directory = root/f'day-{day}'
        directory.mkdir()
        spool, _, _ = recordings.fixture(directory)
        if day:
            retime_synthetic(spool, day)
        value['captures'].append({'utc_date': value['calendar'][day], 'spool': f'day-{day}/spool',
                                  'metadata': f'day-{day}/metadata'})
    path = root/'cohort.json'
    path.write_text(json.dumps(value))
    return path


class CohortControlsTests(unittest.TestCase):
    def test_two_daily_captures_with_reset_monotonic_clocks_reconstruct_in_calendar_order(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            ledger = root/'ledger.jsonl.gz'
            built = cohort.assess(manifest, build_to=ledger)
            self.assertEqual(built['status'], 'COHORT_LEDGER_BUILT', built)
            self.assertEqual(built['counts']['grid_rows'], 17280)
            self.assertEqual(len(built['sources']), 2)
            self.assertTrue(built['all_declared_sources_qualified'])
            sessions = [value['capture_session'] for value in built['sources'].values()]
            self.assertNotEqual(sessions[0], sessions[1])
            verified = cohort.assess(manifest, ledger=ledger)
            self.assertTrue(verified['raw_replay_matched'])
            self.assertFalse(verified['confirmatory_inference_valid'])
            rows = list(paired_review.load_items(ledger))
            self.assertEqual(rows[8640]['pair']['utc_date'], '2030-01-02')
            reviewed = paired_review.review(rows, ['2030-01-01', '2030-01-02'])
            self.assertTrue(reviewed['audit_passed'])

    def test_missing_and_faulted_days_are_preserved_without_zero_pnl_imputation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root, total_days=3, captured=(0, 2))
            status = next((root/'day-0/spool').glob('*.status.json'))
            value = json.loads(status.read_text())
            value['faults'] = ['transport_error']
            status.write_text(json.dumps(value))
            ledger = root/'ledger.jsonl.gz'
            result = cohort.assess(manifest, build_to=ledger)
            self.assertEqual(result['counts']['grid_rows'], 25920)
            self.assertFalse(result['all_declared_sources_qualified'])
            self.assertEqual(result['sources']['2030-01-02']['status'], 'NO_DECLARED_CAPTURE')
            for i, row in enumerate(paired_review.load_items(ledger)):
                if i >= 17280:
                    break
                self.assertFalse(row['pair']['jointly_eligible'])
                self.assertIsNone(row['pair']['candidate_net_usdt'])
            self.assertFalse(result['enrolled'])

    def test_duplicate_dates_reused_sources_and_path_escape_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            original = json.loads(manifest.read_text())
            for kind in ('duplicate_date', 'source_alias', 'traversal', 'absolute', 'flag'):
                value = deepcopy(original)
                if kind == 'duplicate_date':
                    value['captures'][1]['utc_date'] = value['captures'][0]['utc_date']
                elif kind == 'source_alias':
                    value['captures'][1]['spool'] = value['captures'][0]['spool']
                    value['captures'][1]['metadata'] = value['captures'][0]['metadata']
                elif kind == 'traversal':
                    value['captures'][0]['spool'] = '../elsewhere'
                elif kind == 'absolute':
                    value['captures'][0]['spool'] = '/tmp/unreviewed'
                else:
                    value['enrolled'] = True
                manifest.write_text(json.dumps(value))
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    cohort.load_manifest(manifest)

    def test_reused_capture_identity_cannot_masquerade_as_another_date(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root, captured=(0,))
            shutil.copytree(root/'day-0', root/'day-1')
            retime_synthetic(root/'day-1/spool', 1)
            value = json.loads(manifest.read_text())
            value['captures'].append({'utc_date': '2030-01-02', 'spool': 'day-1/spool', 'metadata': 'day-1/metadata'})
            manifest.write_text(json.dumps(value))
            target = root/'duplicate-session.jsonl.gz'
            result = cohort.assess(manifest, build_to=target)
            self.assertFalse(result['grid_complete'])
            self.assertFalse(target.exists())
            self.assertTrue(target.with_name(target.name+'.partial').exists())

    def test_dropped_or_reordered_rows_fail_even_on_missing_dates(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root, captured=(0,))
            ledger = root/'ledger.jsonl.gz'
            cohort.assess(manifest, build_to=ledger)
            rows = list(paired_review.load_items(ledger))
            recordings.write_items(root/'dropped.jsonl.gz', rows[:8641]+rows[8642:])
            result = cohort.assess(manifest, ledger=root/'dropped.jsonl.gz')
            self.assertEqual(result['status'], 'COHORT_LEDGER_MISMATCH')
            self.assertFalse(result['raw_replay_matched'])

    def test_source_changes_prevent_publishing_derived_cohort(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root, total_days=1, captured=(0,))
            original = cohort.daily_views
            def changing(*args):
                yield from original(*args)
                manifest.write_text(manifest.read_text()+'\n')
            ledger = root/'changed.jsonl.gz'
            with patch.object(cohort, 'daily_views', side_effect=changing):
                result = cohort.assess(manifest, build_to=ledger)
            self.assertFalse(result['grid_complete'])
            self.assertFalse(ledger.exists())

    def test_directory_presence_is_part_of_restart_fingerprint(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root, total_days=1, captured=())
            value = json.loads(manifest.read_text())
            value['captures'] = [{'utc_date': '2030-01-01', 'spool': 'missing/spool', 'metadata': 'missing/metadata'}]
            manifest.write_text(json.dumps(value))
            before = cohort.source_bindings(manifest)
            (root/'missing/spool').mkdir(parents=True)
            (root/'missing/metadata').mkdir()
            self.assertNotEqual(before, cohort.source_bindings(manifest))

    def test_fixed_sweep_primary_parity_and_activity_controls(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            ledger = root/'ledger.jsonl.gz'
            cohort.assess(manifest, build_to=ledger)
            primary = paired_review.review(paired_review.load_items(ledger), ['2030-01-01', '2030-01-02'])
            result = secondary.run(manifest)
            self.assertEqual(len(result['cells']), 18)
            self.assertEqual(len(result['controls']), 5)
            self.assertEqual(result['primary_cell'], '50/1000')
            self.assertAlmostEqual(float(result['cells']['50/1000']['paired_mean_incremental_usdt']),
                                   float(primary['analysis']['paired_mean_incremental_usdt']), places=12)
            self.assertEqual(Decimal(result['controls']['zero_leader']['paired_mean_incremental_usdt']), 0)
            for row in result['activity_checks'].values():
                for kind, counts in row['control_candidates'].items():
                    if kind != 'sign_inversion':
                        self.assertEqual(counts, row['original_candidate'])
                    else:
                        self.assertEqual(sum(v for key, v in counts.items() if key != 0),
                                         sum(v for key, v in row['original_candidate'].items() if key != 0))
            eligible = {row['eligible_opportunities'] for row in result['cells'].values()}
            self.assertEqual(len(eligible), 1)
            self.assertTrue(any(row['unknown_pairs'] for row in result['cells'].values()))
            self.assertFalse(result['confirmatory_inference_valid'])
            self.assertFalse(result['deployment_authorized'])

    def test_missing_day_secondary_means_and_leave_one_out_remain_unknown(self):
        with TemporaryDirectory() as directory:
            manifest = fixture(Path(directory), captured=(0,))
            result = secondary.run(manifest)
            missing = result['daily']['2030-01-02']
            self.assertEqual(missing['unavailable_feature_rows'], 8640)
            self.assertIsNone(missing['cells']['50/1000']['paired_mean_incremental_usdt'])
            self.assertIsNone(result['leave_one_date_out_primary_incremental_usdt']['2030-01-01'])

    def test_secondary_protocol_is_fixed_and_cannot_choose_a_winner(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'protocol.json'
            for kind in ('delay', 'seed', 'bounds', 'boolean'):
                value = json.loads(secondary.PROTOCOL.read_text())
                if kind == 'delay':
                    value['delays_ms'] = [50]
                elif kind == 'seed':
                    value['placebo_seed'] = 99
                elif kind == 'boolean':
                    value['delays_ms'][0] = False
                else:
                    value['unknown_eligible_delta_bounds_usdt'] = ['0', '1']
                path.write_text(json.dumps(value))
                with patch.object(secondary, 'PROTOCOL', path), self.assertRaises(ValueError):
                    secondary.protocol()

    def test_lab_can_review_a_matched_cohort_without_promoting_it(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root/'data/raw/trial'
            stage.mkdir(parents=True)
            manifest = fixture(stage, total_days=1, captured=(0,))
            ledger = stage/'ledger.jsonl.gz'
            cohort.assess(manifest, build_to=ledger)
            calendar = stage/'calendar.json'
            calendar.write_text('["2030-01-01"]')
            config = {'cohort_manifest': 'data/raw/trial/cohort.json',
                      'paired_evidence': {'ledger': 'data/raw/trial/ledger.jsonl.gz', 'calendar': 'data/raw/trial/calendar.json'}}
            with patch.object(lab, 'ROOT', root):
                result = lab.paired_evaluation(config)
            self.assertEqual(result['empirical_status'], 'EXPLORATORY_UNENROLLED')
            self.assertTrue(result['raw_grid_verification']['raw_replay_matched'])
            self.assertEqual(len(result['secondary_review']['cells']), 18)
            self.assertFalse(result['deployment_authorized'])
