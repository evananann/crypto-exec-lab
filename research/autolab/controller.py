"""Run an allowlisted research DAG with content-bound, restartable receipts.

Reads committed public evidence and explicitly configured local public-feed captures. No fitting, code rewriting, trading,
credential access, raw-feed acquisition or promotion of a strategy.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]
PLAN = Path(__file__).with_name('plan.json')
REPORTS = ('formal_decision_20261123', 'missingness_frontier_20261123',
           'latency_cost_20261124', 'collector_gate_20261125')
FROZEN = (('configs/successor/registered_study.json', 'source_files_sha256'),
          ('configs/study_v2_okx.json', 'analysis_files_sha256'),
          ('configs/study_v2_bybit.json', 'analysis_files_sha256'),
          ('research/model_source_lock.json', 'files'))
TASKS = ('frozen_integrity', 'released_integrity', 'latency_reproduction', 'execution_mechanics', 'collector_readiness')
DEPENDENCIES = ([], ['frozen_integrity'], ['released_integrity'], ['frozen_integrity'], ['frozen_integrity'])


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    pending = path.with_suffix(path.suffix+'.pending')
    with pending.open('wb') as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())
    pending.replace(path)


def load_plan():
    plan = json.loads(PLAN.read_text())
    if (plan.get('schema_version') != 1 or tuple(t['id'] for t in plan['tasks']) != TASKS
            or type(plan['synthetic_seed']) is not int
            or type(plan['synthetic_cases']) is not int or not 1 <= plan['synthetic_cases'] <= 2000):
        raise ValueError('unsupported lab plan')
    if tuple(t['depends_on'] for t in plan['tasks']) != DEPENDENCIES:
        raise ValueError('mandatory integrity dependencies changed')
    capture_paths(plan)
    seen = set()
    for task in plan['tasks']:
        if not set(task['depends_on']) <= seen:
            raise ValueError('lab dependencies must be earlier allowlisted tasks')
        seen.add(task['id'])
    return plan


def bindings():
    paths = {*Path(__file__).parent.glob('*.json'), *Path(__file__).parent.glob('*.py')}
    source = capture_paths(load_plan())
    if source:
        from research.autolab.qualification import input_files
        paths.update(input_files(*source).values())
    for name, key in FROZEN:
        path = ROOT/name
        paths.add(path)
        paths.update(ROOT/p for p in json.loads(path.read_text())[key])
    for directory in ('research/roadmap', 'research/decision_study'):
        paths.update((ROOT/directory).glob('*.py'))
        paths.update((ROOT/directory).glob('*.json'))
    for report in REPORTS:
        paths.update(p for p in (ROOT/'reports'/report).iterdir() if p.is_file())
    # Bind source membership too: an extra root script invalidates frozen registration.
    paths.update((ROOT/'scripts').glob('*.py'))
    paths.update((ROOT/'cel').rglob('*.py'))
    paths.update((ROOT/'.github/workflows').glob('successor-*.yml'))
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths)}


def capture_paths(plan):
    evidence = plan.get('collector_evidence')
    if evidence is None:
        return None
    if not isinstance(evidence, dict) or set(evidence) != {'spool', 'metadata'}:
        raise ValueError('explicit spool and metadata paths required')
    paths = []
    for key in ('spool', 'metadata'):
        value = evidence[key]
        if not isinstance(value, str) or not value.startswith('data/raw/'):
            raise ValueError('capture must be explicitly staged under data/raw')
        path = ROOT/value
        if path.is_symlink() or not path.resolve().is_relative_to((ROOT/'data/raw').resolve()) or not path.is_dir():
            raise ValueError('original local capture directory required')
        paths.append(path)
    return tuple(paths)


def collector_readiness(plan):
    from research.autolab.qualification import qualify
    paths = capture_paths(plan)
    return qualify(spool=paths[0], metadata=paths[1]) if paths else qualify()


def frozen_integrity(plan):
    from scripts.successor_study import load_registration
    load_registration()
    count = 0
    for name, key in FROZEN:
        for path, expected in json.loads((ROOT/name).read_text())[key].items():
            if sha(ROOT/path) != expected:
                raise ValueError('frozen source hash mismatch')
            count += 1
    return {'verified_source_bindings': count, 'frozen_files_modified': False}


def released_integrity(plan):
    counts = {}
    for report in REPORTS:
        folder = ROOT/'reports'/report
        checksums = json.loads((folder/'checksums.json').read_text())
        if not checksums:
            raise ValueError('empty evidence inventory')
        for name, expected in checksums.items():
            if Path(name).name != name or sha(folder/name) != expected:
                raise ValueError('released evidence checksum mismatch')
        counts[report] = len(checksums)
    return {'verified_files_by_report': counts, 'scope': 'Local committed evidence integrity, not a new remote restore.'}


def latency_reproduction(plan):
    from research.roadmap import latency_cost as engine
    from research.roadmap.latency_publication import verify_inputs
    folder = ROOT/'reports/latency_cost_20261124'
    report, rows = verify_inputs(folder)
    for name, expected in report['protocol']['source_sha256'].items():
        if sha(ROOT/name) != expected:
            raise ValueError('released replay source binding changed')
    traces, cells = 0, 0
    def book(value):
        return engine.Book(value['local_ts_ms'], value['event_line_1based']-1,
                           value['bid'], value['ask'], value['bid_size'], value['ask_size'], value['quantity_unit'])
    for row in rows:
        if row['status'] != 'AVAILABLE':
            continue
        for trace in row['first_common_trace']:
            signal, end = book(trace['signal_quote']), book(trace['exit_quote'])
            for delay in engine.DELAYS:
                entry = book(trace['entries'][str(delay)])
                for fee in engine.FEES:
                    if engine.components(signal, entry, end, trace['side'], fee) != trace['cells'][f'{delay}/{fee}']:
                        raise ValueError('released trace arithmetic mismatch')
                    cells += 1
            traces += 1
    full = report['phases']['full']
    if not traces or not full['common_opportunities']:
        raise ValueError('no released evidence reproduced')
    return {'slots': len(rows), 'usable_slots': full['supplement_available_slots'],
            'dates': full['occupied_days'], 'overlapping_signals': full['common_opportunities'],
            'trace_examples_recomputed': traces, 'trace_cells_recomputed': cells,
            'mean_entry_notional_bps_50ms_5bps_per_fill': full['cells']['50/5']['equal_day_mean']['roundtrip_entry_notional_bps'],
            'scope': 'Reaggregates all saved sessions and recomputes selected trace examples; does not replay raw tapes or establish new alpha.'}


def execution_mechanics(plan):
    from research.roadmap.self_review import generate, check_case
    cases = generate(plan['synthetic_seed'], plan['synthetic_cases'])
    counts = Counter(check_case(case) for case in cases)
    return {'synthetic_cases': len(cases), 'seed': plan['synthetic_seed'],
            'statuses': dict(counts), 'market_observations': 0,
            'scope': 'Synthetic adversarial execution versus independent cash arithmetic; not profitability evidence.'}


def execute(store, plan, source_bindings, handlers, current_bindings=None):
    """Each attempt is immutable. Only verified successful receipts can be reused."""
    run_id = hashlib.sha256(encoded({'plan': plan, 'inputs': source_bindings})).hexdigest()
    store.mkdir(parents=True, exist_ok=True)
    lock = store/'.lock'
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.close(descriptor)
        run = store/run_id
        run.mkdir(exist_ok=True)
        state_file = run/'journal.json'
        if state_file.exists():
            state = json.loads(state_file.read_text())
            if state['run_id'] != run_id or state['inputs'] != source_bindings or state['plan'] != plan:
                raise ValueError('lab journal input binding differs')
            for task, attempts in state['attempts'].items():
                if task not in handlers:
                    raise ValueError('unknown journal task')
                for index, item in enumerate(attempts, 1):
                    name = f'{task}.{index}.json'
                    if item['file'] != name or sha(run/name) != item['sha256']:
                        raise ValueError('lab receipt missing or corrupt; do not reset state')
        else:
            state = {'schema_version': 1, 'run_id': run_id, 'inputs': source_bindings,
                     'plan': plan, 'attempts': {}, 'status': 'RUNNING'}
            save(state_file, state)
        statuses, modes = {}, {}
        for task in plan['tasks']:
            name = task['id']
            if current_bindings is not None and current_bindings() != source_bindings:
                raise ValueError('research inputs changed during execution')
            previous = state['attempts'].get(name, [])
            if previous:
                receipt = json.loads((run/previous[-1]['file']).read_text())
                if receipt['status'] == 'PASSED':
                    statuses[name] = 'PASSED'
                    modes[name] = 'VERIFIED_REUSE'
                    continue
            if any(statuses.get(dep) != 'PASSED' for dep in task['depends_on']):
                statuses[name] = 'BLOCKED_DEPENDENCY'
                modes[name] = 'NOT_RUN'
                continue
            try:
                result = handlers[name](plan)
                encoded(result)  # Reject non-finite or unserializable results before success.
                receipt = {'task': name, 'status': 'PASSED', 'result': result}
            except Exception as error:
                # Bounded diagnostics: raw exceptions can contain URLs or secret values.
                receipt = {'task': name, 'status': 'FAILED', 'error_type': type(error).__name__,
                           'action': 'Inspect this task and reproduce locally; no strategy promotion permitted.'}
            filename = f'{name}.{len(previous)+1}.json'
            if (run/filename).exists():
                raise ValueError('orphan attempt exists; inspect before resuming')
            save(run/filename, receipt)
            state['attempts'].setdefault(name, []).append({'file': filename, 'sha256': sha(run/filename)})
            statuses[name] = receipt['status']
            modes[name] = 'EXECUTED'
            save(state_file, state)
        if current_bindings is not None and current_bindings() != source_bindings:
            raise ValueError('research inputs changed during execution')
        state['task_statuses'] = statuses
        state['task_modes'] = modes
        state['status'] = 'COMPLETE' if all(s == 'PASSED' for s in statuses.values()) else 'FAILED'
        state['deployment_authorized'] = False
        state['research_status'] = 'BLOCKED_PENDING_QUALIFIED_DATA_AND_PROTOCOL'
        state['research_queue'] = plan['research_queue']
        save(state_file, state)
        summary = ['# Automated research lab', '', f"Run: `{run_id}`", '', f"Execution status: **{state['status']}**", '',
                   f"Research status: **{state['research_status']}**", '',
                   'Evidence maintenance and synthetic checks only. Original scientific decision unchanged. No trading deployment.', '',
                   '| Task | Status | Execution |', '| --- | --- | --- |']
        summary += [f'| {task} | {status} | {modes[task]} |' for task, status in statuses.items()]
        if statuses.get('latency_reproduction') == 'PASSED':
            item = state['attempts']['latency_reproduction'][-1]
            evidence = json.loads((run/item['file']).read_text())['result']
            summary += ['', '## Reproduced released finding', '',
                        f"{evidence['overlapping_signals']:,} overlapping signals across {evidence['dates']} dates; "
                        f"50 ms / 5 bps per fill: {evidence['mean_entry_notional_bps_50ms_5bps_per_fill']:.4f} bps.",
                        'Recorded quote subset only; no new observations or incremental-alpha finding. Do not deploy.']
        if statuses.get('collector_readiness') == 'PASSED':
            item = state['attempts']['collector_readiness'][-1]
            evidence = json.loads((run/item['file']).read_text())['result']
            summary += ['', '## Hypothesis evidence decision', '', evidence['question'], '',
                        f"Data status: **{evidence['status']}**; conclusion: **{evidence['conclusion']}**.",
                        'Capture review never authorizes study enrollment or deployment.',
                        'Reasons: '+', '.join(evidence['reasons'])]
        summary += ['', '## Research queue', '']
        for item in plan['research_queue']:
            summary += [f"- **{item['id']} — {item['state']}**: {item['question']}",
                        f"  Next: {item['next_action']}", '  Requires: '+ '; '.join(item['requires'])]
        (run/'README.md').write_text('\n'.join(summary)+'\n')
        return run, state
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--summary', type=Path, help='Write the current run Markdown summary here')
    args = parser.parse_args()
    plan = load_plan()
    handlers = dict(zip(TASKS, (frozen_integrity, released_integrity, latency_reproduction, execution_mechanics, collector_readiness)))
    run, state = execute(args.store, plan, bindings(), handlers, current_bindings=bindings)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text((run/'README.md').read_text())
    modes = Counter(state['task_modes'].values())
    print(f"::notice title=Automated research lab::{state['status']}; executed={modes['EXECUTED']}; "
          f"verified_reuse={modes['VERIFIED_REUSE']}; research={state['research_status']}; deployment_authorized=false")
    if 'collector_readiness' in state['attempts']:
        receipt = state['attempts']['collector_readiness'][-1]
        evidence = json.loads((run/receipt['file']).read_text()).get('result', {})
        print(f"::notice title=Hypothesis evidence decision::{evidence.get('status', 'UNAVAILABLE')}; strategy_outcomes_computed=0")
    print(f"Research lab {state['status']}: {run}")
    return 0 if state['status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
