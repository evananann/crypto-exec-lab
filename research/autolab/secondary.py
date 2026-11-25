"""Fixed delay/holding sensitivities and retrospective activity controls on cohorts."""
import argparse
from collections import Counter
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

from research.autolab import cohort, raw_replay as raw
from research.autolab.qualification import digest
from research.continuous_capture import strict_json
from research.roadmap.followon import DELAYS, HORIZONS, placebo_actions
from research.roadmap import empirical_pipeline as engine

PROTOCOL = Path(__file__).with_name('secondary_protocol.json')


def protocol():
    value = strict_json(PROTOCOL.read_bytes())
    if (set(value) != {'schema_version', 'state', 'delays_ms', 'holding_after_entry_ms',
            'primary_delay_ms', 'primary_holding_ms', 'entry_fee_bps', 'exit_fee_bps',
            'placebos', 'placebo_seed', 'unknown_eligible_delta_bounds_usdt', 'interpretation'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or any(type(item) is not int for item in [*value['delays_ms'], *value['holding_after_entry_ms'],
                   value['primary_delay_ms'], value['primary_holding_ms']]) or value['state'] != 'PROPOSED_NOT_ENROLLED'
            or tuple(value['delays_ms']) != DELAYS or tuple(value['holding_after_entry_ms']) != HORIZONS
            or value['primary_delay_ms'] != 50 or value['primary_holding_ms'] != 1000
            or value['entry_fee_bps'] != '5' or value['exit_fee_bps'] != '5'
            or value['placebos'] != ['cyclic_shift', 'within_day_shuffle', 'sign_inversion', 'random_trigger']
            or type(value['placebo_seed']) is not int or value['placebo_seed'] != 7
            or value['unknown_eligible_delta_bounds_usdt'] != ['-0.10', '0.10']):
        raise ValueError('fixed proposed secondary protocol changed')
    return value


def empty():
    return {'eligible_opportunities': 0, 'known_pairs': 0, 'unknown_pairs': 0,
            'baseline_active_decisions': 0, 'candidate_active_decisions': 0,
            **{key: Decimal(0) for key in ('baseline_gross', 'candidate_gross', 'baseline_fees', 'candidate_fees',
                                         'baseline_net', 'candidate_net', 'known_entry_fees_on_unknown_pairs')}}


def add(target, rows, actions):
    target['eligible_opportunities'] += 1
    target['baseline_active_decisions'] += actions[0] != 0
    target['candidate_active_decisions'] += actions[1] != 0
    if any(row['net_usdt'] is None for row in rows):
        target['unknown_pairs'] += 1
        target['known_entry_fees_on_unknown_pairs'] += sum(Decimal(row['entry_fee_usdt']) for row in rows)
        return
    target['known_pairs'] += 1
    for policy, row in zip(('baseline', 'candidate'), rows):
        for key in ('gross', 'fees', 'net'):
            value = Decimal(row[key+'_usdt'])
            if not value.is_finite():
                raise ValueError('nonfinite execution component')
            target[policy+'_'+key] += value


def summarize(value, bounds):
    known, eligible = value['known_pairs'], value['eligible_opportunities']
    result = {key: str(v) if isinstance(v, Decimal) else v for key, v in value.items()}
    delta = value['candidate_net']-value['baseline_net']
    for policy in ('baseline', 'candidate'):
        result[policy+'_mean_net_usdt'] = str(value[policy+'_net']/known) if known else None
    result['paired_mean_incremental_usdt'] = str(delta/known) if known else None
    result['unknown_eligible_assumption_bounds'] = [
        str((delta+value['unknown_pairs']*Decimal(bound))/eligible) for bound in bounds] if eligible else None
    result['bounds_scope'] = 'Assumed delta range for unknown eligible outcomes only; excludes unknown feature/eligibility selection and is not a confidence interval.'
    return result


def run(manifest_path):
    spec = protocol()
    manifest = cohort.load_manifest(manifest_path)
    before = cohort.source_bindings(manifest_path, manifest)
    keys = [f'{delay}/{holding}' for delay in DELAYS for holding in HORIZONS]
    control_keys = ['zero_leader', *spec['placebos']]
    sums = {key: empty() for key in keys}
    controls = {key: empty() for key in control_keys}
    daily, sources, activity = {}, {}, {}
    for day, view, source, design in cohort.daily_views(manifest_path, manifest, sources):
        day_sums = {key: empty() for key in keys}
        day_controls = {key: empty() for key in control_keys}
        decisions = []
        if view is not None:
            grid, _ = raw.calendar_grid([day], 10**10)
            for midnight, _ in grid:
                for utc_ns in range(midnight, midnight+raw.DAY_NS, 10**10):
                    when = utc_ns-source['utc_minus_monotonic_ns']
                    features = view.features(when)
                    if features:
                        decisions.append((when, utc_ns//10**6, features['feature_quotes'][1]['session'], features['actions']))
            for delay in DELAYS:
                for holding in HORIZONS:
                    key = f'{delay}/{holding}'
                    variant = deepcopy(design)
                    variant['execution'].update(decision_delay_ms=delay, holding_after_entry_ms=holding)
                    replay = engine.Replay(view.books, variant)
                    for when, _, session, actions in decisions:
                        rows = [replay.execute(action, when, session) for action in actions]
                        add(day_sums[key], rows, actions)
                        add(sums[key], rows, actions)
                    del replay
            opportunities = [(str(when), utc_ms) for when, utc_ms, _, _ in decisions]
            actions = {utc_ms: selected[1] for _, utc_ms, _, selected in decisions}
            overrides = {kind: placebo_actions(opportunities, actions, kind, seed=spec['placebo_seed'])
                         for kind in spec['placebos']}
            for kind in control_keys:
                for when, utc_ms, session, chosen in decisions:
                    selected = [chosen[0], chosen[0] if kind == 'zero_leader' else overrides[kind][utc_ms]]
                    rows = [view.execute(action, when, session) for action in selected]
                    add(day_controls[kind], rows, selected)
                    add(controls[kind], rows, selected)
            activity[day] = {'original_candidate': dict(Counter(actions.values())),
                'control_candidates': {kind: dict(Counter(values.values())) for kind, values in overrides.items()}}
            del overrides
        daily[day] = {'eligible_opportunities': len(decisions), 'unavailable_feature_rows': 8640-len(decisions),
                      'cells': {key: summarize(value, spec['unknown_eligible_delta_bounds_usdt']) for key, value in day_sums.items()},
                      'controls': {key: summarize(value, spec['unknown_eligible_delta_bounds_usdt']) for key, value in day_controls.items()}}
        del view, source, decisions
    if before != cohort.source_bindings(manifest_path, manifest):
        raise ValueError('cohort sources changed during secondary review')
    primary = '50/1000'
    leave_out = {}
    for day in manifest['calendar']:
        count = sums[primary]['known_pairs']-daily[day]['cells'][primary]['known_pairs']
        day_delta = Decimal(daily[day]['cells'][primary]['candidate_net'])-Decimal(daily[day]['cells'][primary]['baseline_net'])
        delta = sums[primary]['candidate_net']-sums[primary]['baseline_net']-day_delta
        leave_out[day] = str(delta/count) if count else None
    return {'schema_version': 1, 'status': 'EXPLORATORY_SECONDARY_REVIEW', 'protocol_sha256': digest(PROTOCOL),
            'manifest_sha256': digest(manifest_path), 'primary_cell': primary,
            'cells': {key: summarize(value, spec['unknown_eligible_delta_bounds_usdt']) for key, value in sums.items()},
            'controls': {key: summarize(value, spec['unknown_eligible_delta_bounds_usdt']) for key, value in controls.items()},
            'daily': daily, 'sources': sources, 'activity_checks': activity,
            'leave_one_date_out_primary_incremental_usdt': leave_out,
            'selection': 'Every fixed case reported; no ranking, winner selection or parameter changes.',
            'placebo_scope': 'Retrospective within-day action controls may use future actions. They are not executable strategies. Sign inversion preserves activity, while other randomized/rotated controls also preserve the direction multiset.',
            'confirmatory_inference_valid': False, 'deployment_authorized': False,
            'limitations': 'Means use known complete pairs on common decision-feature eligibility. Execution coverage varies by cell. Missing features, source selection, long dependence, funding, impact and race outcomes remain unresolved.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.manifest)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'secondary.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(result['status'])


if __name__ == '__main__':
    main()
