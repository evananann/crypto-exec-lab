"""Compile a formal disposition from original released and diagnostic evidence."""

import argparse
from html import escape
import json
from pathlib import Path
import shutil

from research.roadmap.empirical_pipeline import digest

ROOT = Path(__file__).resolve().parents[2]


def compile_decision(evidence, out):
    primary = ROOT / 'reports/released_successor_20261122'
    for name, expected in json.loads((primary / 'checksums.json').read_text()).items():
        if Path(name).name != name or digest(primary / name) != expected:
            raise ValueError('original released presentation differs')
    published = json.loads((primary / 'released-study.json').read_text())
    inputs = {'original-order-audit.json': evidence / 'first-regression-audit.json',
              'long-capture.json': evidence / 'result.json',
              'short-capture.json': evidence / 'pipeline-proof/result.json',
              'restart-diagnostic.json': evidence / 'pipeline-proof/restart-diagnostic.json',
              'activity.json': evidence / 'faulted-activity-v2/summary.json',
              'transport-probe.json': evidence / 'transport-probe.json'}
    for name in ('old-preservation.json', 'current-preservation.json'):
        path = evidence / name
        if path.exists():
            receipt = json.loads(path.read_text())
            if (receipt.get('status') != 'REMOTE_READBACK_VERIFIED'
                    or receipt.get('scientific_enrollment') is not False
                    or receipt.get('production_host_qualified') is not False
                    or receipt.get('absolute_utc_accuracy_verified') is not False):
                raise ValueError('archive receipt cannot grant scientific or host qualification')
            inputs[name] = path
    data = {k: json.loads(p.read_text()) for k, p in inputs.items()}
    order, capture, activity = (data[k] for k in ('original-order-audit.json', 'long-capture.json', 'activity.json'))
    if not order['original_bytes_unchanged'] or activity['execution_outcomes_computed'] != 0:
        raise ValueError('diagnostic scope differs from reviewed evidence')
    frozen = published['decision_status']
    if frozen != 'inconclusive_missing_coverage_or_precision':
        raise ValueError('original formal disposition changed; review required')
    result = {'schema_version': 1, 'as_of': '2026-11-23',
        'deployment_decision': 'DO_NOT_DEPLOY', 'followon_enrollment': 'BLOCKED_NOT_ENROLLED',
        'original_scientific_conclusion': frozen, 'primary_phases': published['phases'],
        'incremental_binance_value': 'UNESTABLISHED',
        'secondary_model_status': 'UNAVAILABLE_RECORDED_ORDER_VIOLATION',
        'first_problematic_original_slot': order['original']['slot_id'],
        'original_slots_diagnosed': len(order['audited_eligible']),
        'original_records_diagnosed': sum(r['counts']['records'] for r in order['audited_eligible']),
        'first_problematic_slot_order_counts': order['counts'],
        'long_capture': capture['main'], 'long_capture_target_seconds': 1800,
        'activity_counts': activity['counts'], 'execution_outcomes_computed': 0,
        'restart_original_bytes_preserved': data['restart-diagnostic.json']['all_original_bytes_retained'],
        'independent_utc_accuracy_verified': False,
        'original_report_sha256': digest(primary / 'released-report.json'),
        'source_evidence_sha256': {k: digest(p) for k, p in inputs.items()},
        'implementation_sha256': {n: digest(ROOT / n) for n in (
            'research/roadmap/formal_decision.py', 'research/roadmap/empirical_pipeline.py',
            'research/roadmap/timestamp_audit.py')},
        'interpretation': 'Do not allocate capital to the tested taker setup. The observed primary '
            'subset is unfavorable, but incomplete coverage prevents the frozen confirmatory '
            'conclusion. Incremental Binance information has not been established. No model '
            'estimate is recovered by sorting timestamps. Failed capture attempts and zero '
            'action contrasts do not qualify a new experiment or prove that no useful signal exists.',
        'next_required_evidence': ['Reliable sustained transport on a durable acquisition host',
            'Independently measured clock quality and archived original source/data readback',
            'Future source freeze covering the conservative writer-availability boundary, '
            'normalization, gap rules, fixed sensitivity and control definitions',
            'New discovery and validation dates demonstrating adequate policy contrasts',
            'Exact future enrollment calendar followed by an untouched test period'],
        'deployment_authorized': False}
    result['archive_preservation'] = {k: {field: data[k][field] for field in (
        'release_url', 'run_id', 'archive_sha256', 'archive_bytes', 'members_verified')}
        for k in ('old-preservation.json', 'current-preservation.json') if k in data}
    out.mkdir(parents=True, exist_ok=False)
    for name, path in inputs.items():
        shutil.copyfile(path, out / name)
    (out / 'decision.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    full = published['phases']['full']
    text = f'''# Formal research disposition — November 23, 2026

**Trading decision: DO NOT DEPLOY. Follow-on experiment: BLOCKED, NOT ENROLLED.**

The frozen scientific conclusion remains `{frozen}`.
It is distinct from the operational decision to reject capital deployment.

| Evidence | Measured finding | Decision consequence |
| --- | --- | --- |
| Original primary | {full['equal_day_mean_bps']:.4f} bps entry-net; {full['eligible_slots']}/{full['planned_slots']} slots; three holdout dates | Unfavorable observed subset; formal coverage requirements failed |
| Recorded order | {result['original_records_diagnosed']:,} records across {result['original_slots_diagnosed']} eligible originals through {result['first_problematic_original_slot']}; three 1 ms cross-venue reversals in that slot | Secondary model unavailable; no sorting or sample repair |
| Longer capture | Intended 1800 s; stopped at {capture['main']['elapsed_seconds']:.2f} s with a Binance transport error | Sustained collection qualification failed |
| Independent short capture | Stopped early with another Binance transport error | Preserved as a second failed attempt, not substituted for the long test |
| Independent restart | Original bytes preserved: {result['restart_original_bytes_preserved']} | Recovery mechanics only; not a durable-host certificate |
| Partial-window activity | {activity['counts']['grid_opportunities']} grid points; {activity['counts']['jointly_eligible']} joint feature points; zero active decisions or contrasts | Feasibility remains unqualified; zero execution outcomes computed |

## What the timestamp diagnosis establishes

The original recorder samples its monotonic-anchored clock before parsing and
acquiring the write lock. An adversarial test of the unchanged recorder reproduces
overtaking without a clock going backwards. All three observed reversals cross
Binance to OKX. Legacy events lack connection and parsing/write telemetry, so
individual historical causes cannot be conclusively assigned. The diagnostic
sample ends at the first affected eligible original; it is not a full-cohort audit.

The new assembler uses recorded single-writer availability, after packet receipt
and enqueue, as an explicit conservative boundary. It preserves original receive
timestamps and raw offsets. This is a new prospective convention, requiring its
own source freeze; it does not rescue the original model comparison.

## What is implemented and what remains unmeasured

The raw-to-paired pipeline validates sealed segment hashes, bracketing original
instrument responses, BTC contract conversion, per-connection sequences, quote
age, joint eligibility, both policies, both-side fees, displayed depth, cash and
inventory conservation, and unknown exits. Missing opportunities stay missing.
Fixture tests exercise closed long/short trades; actual faulted captures are
restricted to outcome-free activity. No real-data paired P&L or alpha estimate
is claimed. A complete registered-calendar assembler and confirmatory enrollment
are still required; a closed local spool is integrity evidence, not independent
authentication of venue observations.

The isolated transport probe did not reproduce the earlier errors during its
observation window and exceeded its worker-join deadline during cleanup. It does
not establish their cause or qualify transport. Clock kernel status and local
wall/monotonic telemetry do not establish independent UTC accuracy.

## Evidence needed to change the decision

1. Demonstrate sustained acquisition and recoverable gaps on a qualified durable host.
2. Preserve and independently read back the source/data archives and clock evidence.
3. Freeze the full empirical pipeline and control definitions before new enrollment.
4. Observe new discovery/validation activity and show adequate distinct decisions.
5. Complete the exact future untouched test calendar and evaluate incremental and
   absolute candidate economics under the frozen rules.

No historical slots are replaced, missing sessions imputed as zero, thresholds
tuned on these outcomes, or old studies pooled. A positive relative result alone
would still not establish a profitable strategy or authorize deployment.

The original primary is entry-to-mid markout after 50 ms and one 5 bps entry fee,
not a realized round-trip return. Its descriptive interval cannot repair missing
coverage. Original detailed summaries and source hashes accompany this memo.
'''
    archive_html = ''
    if result['archive_preservation']:
        text += '\n## Archive readback completed\n\n'
        for name, r in result['archive_preservation'].items():
            text += (f"- [{name}]({name}): {r['members_verified']} members verified; "
                     f"{r['archive_bytes']:,} archive bytes; [Release]({r['release_url']}).\n")
        text += ('\nThe repository worker and a separate cloud download both matched original '
                 'asset hashes and every member. Both failed attempts are retained. This closes '
                 'the archive-readback gap, not transport, UTC or scientific qualification. '
                 'GitHub administrators can change Release assets; WORM retention is not claimed.\n')
        archive_html = ('<h2>Archive readback completed</h2><p>Both public rehearsal archives were '
            'preserved and independently downloaded: 54 members in the earlier archive and 60 '
            'in the current one. All member hashes matched. This closes an operational gap, '
            'while transport, independent UTC evidence and new sampling remain unqualified. '
            'GitHub Release assets remain mutable by administrators.</p>')
    (out / 'README.md').write_text(text)
    table = [
        ('Original study', f"{full['equal_day_mean_bps']:.4f} bps; {full['eligible_slots']}/{full['planned_slots']} slots", 'Inconclusive under frozen coverage rules'),
        ('Secondary model', 'Three recorded cross-venue timestamp reversals', 'Unavailable; no data repair'),
        ('Sustained collection', f"Stopped at {capture['main']['elapsed_seconds']:.2f} of 1800 planned seconds", 'Qualification failed'),
        ('Paired activity', f"{activity['counts']['grid_opportunities']} grid points; zero contrasts", 'No execution outcomes or information-value estimate')]
    rows = ''.join('<tr>' + ''.join('<td>' + escape(cell) + '</td>' for cell in row) + '</tr>' for row in table)
    gates = ''.join('<li>' + escape(x) + '</li>' for x in result['next_required_evidence'])
    html = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>Formal research decision</title><style>body{font:17px/1.55 system-ui;max-width:960px;margin:40px auto;'
        'padding:20px;color:#172b4d}h1{line-height:1.2}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px '
        'solid #ccd4e0;text-align:left;padding:12px}.decision{background:#f3e9df;padding:20px;border-left:5px solid '
        '#965e28}a{color:#164fc5}@media print{body{margin:0;font-size:11pt}}</style>'
        '<p>BTC cross-venue execution research · November 23, 2026</p><h1>Reject deployment. '
        'Keep the scientific uncertainty explicit.</h1><div class="decision"><strong>DO NOT DEPLOY · '
        'FOLLOW-ON NOT ENROLLED</strong><p>' + escape(result['interpretation']) + '</p></div>'
        '<h2>Measured evidence</h2><table><tr><th>Question</th><th>Finding</th><th>Consequence</th></tr>' + rows + '</table>'
        '<h2>What the engineering work establishes</h2><p>Source-linked raw-to-paired replay, original instrument '
        'response verification, explicit availability timing, depth and cash-cost accounting, and preservation '
        'of failed attempts. Synthetic accounting checks do not establish market edge.</p>'
        '<p>The historical recorder permits callback overtaking before the write lock. Three 1 ms cross-venue '
        'reversals were found in the first affected slot. Individual causes cannot be proved from legacy events. '
        'The new writer-availability convention requires its own future source freeze.</p>'
        + archive_html + '<h2>Evidence required to change the decision</h2><ol>' + gates + '</ol>'
        '<p>The primary metric is entry-to-mid after one 5 bps entry fee, not realized round-trip profit. '
        'Missing sessions remain unknown. Relative improvement alone does not establish positive absolute economics.</p>'
        '<p><a href="https://github.com/evananann/crypto-exec-lab/blob/main/reports/formal_decision_20261123/README.md">'
        'Full memo, original summaries and source hashes</a> · '
        '<a href="https://github.com/evananann/crypto-exec-lab">Repository and tests</a></p></html>')
    (out / 'decision.html').write_text(html)
    (out / 'checksums.json').write_text(json.dumps({p.name: digest(p) for p in sorted(out.iterdir())
        if p.is_file()}, indent=2) + '\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    compile_decision(a.evidence, a.out)
