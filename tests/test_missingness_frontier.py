from decimal import Decimal
from itertools import product
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.roadmap.missingness_frontier import ROOT, analyze, source_records

PLAN = ['2026-01-01-am', '2026-01-01-pm', '2026-01-02-am', '2026-01-02-pm']


class MissingnessFrontierTests(unittest.TestCase):
    def test_occupied_day_and_complete_calendar_weights_are_distinct(self):
        result = analyze(PLAN, {PLAN[0]: '-4', PLAN[1]: '-6', PLAN[2]: '-2'})
        self.assertEqual(Decimal(result['observed_equal_occupied_day_mean_bps']), Decimal('-3.5'))
        self.assertEqual(Decimal(result['observed_equal_slot_mean_bps']), Decimal('-4'))
        self.assertEqual(Decimal(result['common_missing_mean_needed_for_zero_bps']), Decimal('12'))

    def test_stratified_frontier_respects_missing_am_and_pm_counts(self):
        result = analyze(PLAN, {PLAN[0]: '-4', PLAN[3]: '-6'})
        self.assertEqual(result['strata']['am']['unavailable'], 1)
        self.assertEqual(result['strata']['pm']['unavailable'], 1)
        self.assertEqual(Decimal(result['pm_needed_if_missing_am_matches_observed_am_bps']), Decimal('14'))
        zero = next(r for r in result['fixed_assumption_scenarios']
                    if r['assumed_missing_am_mean_bps'] == r['assumed_missing_pm_mean_bps'] == '5')
        self.assertEqual(Decimal(zero['hypothetical_complete_schedule_mean_bps']), 0)

    def test_conditional_region_endpoints_are_attainable_on_complete_days(self):
        observed = {PLAN[0]: Decimal('-4'), PLAN[3]: Decimal('-6')}
        result = analyze(PLAN, observed)
        region = result['conditional_identification_regions'][1]  # fixed +/-2 scenario
        complete_means = []
        for a, b in product((Decimal('-2'), Decimal('2')), repeat=2):
            filled = observed | {PLAN[1]: a, PLAN[2]: b}
            day1 = (filled[PLAN[0]] + filled[PLAN[1]]) / 2
            day2 = (filled[PLAN[2]] + filled[PLAN[3]]) / 2
            complete_means.append((day1 + day2) / 2)
        self.assertEqual(Decimal(region['sharp_complete_schedule_lower_bps']), min(complete_means))
        self.assertEqual(Decimal(region['sharp_complete_schedule_upper_bps']), max(complete_means))
        self.assertEqual(result['without_outcome_bounds'], 'UNBOUNDED')

    def test_fully_observed_calendar_has_no_missing_mean_frontier(self):
        result = analyze(PLAN, {k: '-3' for k in PLAN})
        self.assertEqual(result['without_outcome_bounds'], 'POINT_IDENTIFIED')
        self.assertIsNone(result['common_missing_mean_needed_for_zero_bps'])
        self.assertIsNone(result['pm_needed_if_missing_am_matches_observed_am_bps'])
        for r in result['conditional_identification_regions']:
            self.assertEqual(Decimal(r['sharp_complete_schedule_lower_bps']), Decimal('-3'))
            self.assertEqual(r['sharp_complete_schedule_lower_bps'], r['sharp_complete_schedule_upper_bps'])

    def test_all_missing_does_not_invent_observed_stratum_means(self):
        result = analyze(PLAN, {})
        self.assertIsNone(result['strata']['am']['observed_mean_bps'])
        self.assertIsNone(result['strata']['pm']['observed_mean_bps'])
        self.assertIsNone(result['observed_equal_occupied_day_mean_bps'])
        self.assertIsNone(result['pm_needed_if_missing_am_matches_observed_am_bps'])

    def test_invalid_calendars_or_outcomes_fail(self):
        for plan, outcomes in [(PLAN + [PLAN[0]], {}), (PLAN[:-1], {}),
                               (PLAN, {'unknown': '1'}), (PLAN, {PLAN[0]: True}),
                               (PLAN, {PLAN[0]: float('nan')}), (PLAN, {PLAN[0]: 'inf'}),
                               (PLAN, {PLAN[0]: 'bad'})]:
            with self.subTest(plan=plan, outcomes=outcomes), self.assertRaises(ValueError):
                analyze(plan, outcomes)

    def test_release_gate_precedes_any_archive_read(self):
        with patch('research.empirical_note.current_plan', return_value=None):
            with self.assertRaisesRegex(ValueError, 'release gated'):
                source_records(Path('/nonexistent/no-early-read'))

    def test_archive_digest_checked_before_parsing(self):
        with TemporaryDirectory() as directory:
            p = Path(directory) / 'bad.tar.gz'
            p.write_bytes(b'not the authenticated report')
            with self.assertRaisesRegex(ValueError, 'differs from authenticated'):
                source_records(p)

    def test_published_source_rows_reproduce_stratified_finding(self):
        p = ROOT / 'reports/missingness_frontier_20261123/sensitivity.json'
        published = json.loads(p.read_text())
        rows = published['rows']
        result = analyze([r['slot_id'] for r in rows],
                         {r['slot_id']: r['mean_bps'] for r in rows if r['mean_bps'] is not None})
        self.assertEqual(result, published['phases']['full'])
        self.assertEqual(result['strata']['am']['unavailable'], 6)
        self.assertEqual(result['strata']['pm']['unavailable'], 27)
        self.assertGreater(Decimal(result['pm_needed_if_missing_am_matches_observed_am_bps']), Decimal('5'))
        self.assertFalse(published['deployment_authorized'])
        self.assertFalse(published['missing_outcomes_estimated'])


if __name__ == '__main__':
    unittest.main()
