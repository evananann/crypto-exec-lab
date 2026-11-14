"""Run controlled financial faults in disposable copies, never in study sources."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CASES = [
    ('double_counted_spread', 'research/decision_study/pipeline.py',
     "net_pnl_usd=str(gross-fees))", "net_pnl_usd=str(gross-fees-eq*(decimal(entry.ask)-decimal(entry.bid))))",
     'tests.test_decision_pipeline.DecisionPipelineTests.test_same_action_identical_execution_and_exact_cash'),
    ('incorrect_fee_notional', 'research/decision_study/pipeline.py',
     'fees = eq * ep * fee_rate', 'fees = eq * fee_rate',
     'tests.test_decision_pipeline.DecisionPipelineTests.test_same_action_identical_execution_and_exact_cash'),
    ('future_quote', 'research/decision_study/pipeline.py',
     'i = bisect_right(times, time) - 1', 'i = min(bisect_right(times, time), len(times) - 1)',
     'tests.test_decision_pipeline.DecisionPipelineTests.test_future_stale_and_uncovered_quotes_not_used'),
    ('duplicate_fill', 'scripts/order_lifecycle.py',
     "execution = (order['venue'],event['execution_id'])", "execution = (order['venue'],event['message_id'])",
     'tests.test_internal_validation.LifecycleTests.test_duplicate_reports_and_retries_never_double_fill'),
]


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    for name, filename, old, new, test in CASES:
        original = (ROOT / filename).read_bytes()
        with tempfile.TemporaryDirectory(prefix='financial-mutation-') as temporary:
            root = Path(temporary)
            for folder in ('cel', 'research', 'scripts', 'tests', 'configs'):
                shutil.copytree(ROOT / folder, root / folder,
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            command = [sys.executable, '-m', 'unittest', test, '-v']
            baseline = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=60)
            source = original.decode()
            if source.count(old) != 1:
                raise ValueError('mutation anchor is not unique: ' + name)
            mutated = source.replace(old, new)
            (root / filename).write_text(mutated)
            result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=60)
            # Import/setup failures do not count as a detected financial fault.
            detected = (baseline.returncode == 0 and result.returncode != 0
                        and ('FAIL: ' + test.split('.')[-1] in result.stderr
                             or 'ERROR: ' + test.split('.')[-1] in result.stderr)
                        and 'Ran 1 test' in result.stderr
                        and 'ImportError' not in result.stderr
                        and 'ModuleNotFoundError' not in result.stderr)
            (out / (name + '.log')).write_text('BASELINE\n' + baseline.stderr + '\nMUTANT\n' + result.stderr)
            rows.append(dict(fault=name, source=filename, test=test, detected=detected,
                             baseline_exit=baseline.returncode, mutant_exit=result.returncode,
                             original_sha256=hashlib.sha256(original).hexdigest(),
                             mutant_sha256=hashlib.sha256(mutated.encode()).hexdigest()))
        if (ROOT / filename).read_bytes() != original:
            raise AssertionError('original source changed')
    report = dict(schema_version=1, evidence='controlled synthetic faults in isolated copies',
                  financial_correctness_proven=False, all_detected=all(r['detected'] for r in rows),
                  mutations=rows)
    (out / 'mutations.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.out)['all_detected'] else 1)
