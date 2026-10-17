"""Read-only study operations: coverage, archive health and retention, never returns."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from html import escape
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import zipfile

from cel.artifacts import file_sha256, write_json_atomic, write_text_atomic
from cel.ingest.instruments import contract_value_btc
from cel.study import DEFAULT_PLAN, health, load_plan, restore_archive, session_slot
from scripts.download_study_artifacts import download_zip, expected_names, unpack_zip, verify_run

PLANS = (DEFAULT_PLAN, DEFAULT_PLAN.with_name('study_v2_okx.json'), DEFAULT_PLAN.with_name('study_v2_bybit.json'))


def api_json(endpoint, *, paginate=False):
    # Older supported gh installations lack --slurp. Decode its ordinary
    # concatenated paginated JSON instead of changing the frozen downloader.
    args = ['gh', 'api', *(['--paginate'] if paginate else []), endpoint]
    raw = subprocess.check_output(args, text=True)
    if not paginate:
        return json.loads(raw)
    pages = []
    decoder = json.JSONDecoder()
    remaining = raw.lstrip()
    while remaining:
        page, end = decoder.raw_decode(remaining)
        pages.append(page)
        remaining = remaining[end:].lstrip()
    return pages


def instant(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('UTC-aware timestamp required')
    return result.astimezone(timezone.utc)


def slots(plan):
    day = date.fromisoformat(plan['start_date_utc'])
    while day <= date.fromisoformat(plan['end_date_utc']):
        for slot, clock in plan['slots_utc'].items():
            start = instant(f'{day}T{clock}:00+00:00')
            yield f'{day}-{slot}', slot, start + timedelta(
                minutes=plan['slot_tolerance_minutes'] + 2, seconds=plan['seconds'])
        day += timedelta(days=1)


def archive_health(archive, plan_path, session, slot, run):
    """Recompute only collection gates. Never call an outcome estimator."""
    plan, _ = load_plan(plan_path)
    with tempfile.TemporaryDirectory(prefix='study-health-') as directory:
        restored = restore_archive(archive, Path(directory))
        item = json.loads((restored / 'manifest.json').read_text())
        if (item['session_id'] != session or item['plan_sha256'] != file_sha256(plan_path)
                or item['collector_commit'] != run['head_sha'] or item['collector_dirty'] is not False
                or file_sha256(restored / 'plan.json') != file_sha256(plan_path)):
            raise ValueError('session, plan or collector provenance mismatch')
        identifier, phase = session_slot(plan, instant(item['started_at_utc']), slot)
        if identifier != session or item['phase'] != phase:
            raise ValueError('attempt does not match its frozen slot')
        status = item['status']
        if status not in ('eligible', 'blocked', 'ineligible'):
            raise ValueError('unknown collection state')
        if status != 'eligible':
            return status
        metadata = list(restored.glob('*.meta.json'))
        if len(metadata) != 1:
            raise ValueError('eligible session needs a unique recorder sidecar')
        if 'okx' in (plan['leader'], plan['follower']):
            factor = contract_value_btc(json.loads((restored / 'instrument.json').read_text()))
            if factor != item.get('verified_contract_value_btc'):
                raise ValueError('instrument conversion mismatch')
        checked = health(restored / 'tape.jsonl', plan, json.loads(metadata[0].read_text()), plan['seconds'])
        if not checked['eligible']:
            raise ValueError('claimed eligible archive fails recomputed health gates')
        return 'eligible'


def inspect(repository, *, plan_paths=PLANS, now=None, expiry_days=14):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('invalid repository')
    if not 1 <= expiry_days <= 90:
        raise ValueError('expiry warning window must be 1..90 days')
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    plans = [(path, load_plan(path)[0]) for path in plan_paths]
    unavailable = False
    try:
        pages = api_json(f'repos/{repository}/actions/artifacts?per_page=100', paginate=True)
        artifacts = [item for page in pages for item in page['artifacts']]
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError):
        artifacts, unavailable = [], True
    rows, alerts, retention = [], [], []
    runs = {}
    if unavailable:
        alerts.append('Artifact inventory unavailable; do not infer missing or successful collection.')
    for path, plan in plans:
        names = expected_names(plan)
        matching = {}
        for item in artifacts:
            if item.get('name') not in names:
                continue
            matching.setdefault(names[item['name']], []).append(item)
            expires = item.get('expires_at')
            if item.get('expired') or expires and instant(expires) <= now + timedelta(days=expiry_days):
                retention.append({'study_id': plan['study_id'], 'session': names[item['name']],
                                  'artifact_id': item['id'], 'expires_at': expires,
                                  'expired': bool(item.get('expired'))})
        for session, slot, due in slots(plan):
            row = {'study_id': plan['study_id'], 'session': session, 'due_utc': due.isoformat(),
                   'state': 'pending' if now <= due else ('unverified' if unavailable else 'missing'),
                   'run_url': None}
            attempts = matching.get(session, [])
            if len(attempts) > 1:
                row['state'] = 'ambiguous'
            elif attempts:
                item = attempts[0]
                try:
                    identifier = item['id']
                    run_id = item['workflow_run']['id']
                    if any(type(v) is not int or v <= 0 for v in (identifier, run_id)):
                        raise ValueError('invalid artifact or run ID')
                    row['run_url'] = f'https://github.com/{repository}/actions/runs/{run_id}'
                    if item.get('expired'):
                        row['state'] = 'expired'
                    else:
                        if run_id not in runs:
                            runs[run_id] = api_json(f'repos/{repository}/actions/runs/{run_id}')
                        run = runs[run_id]
                        if run.get('status') != 'completed':
                            # Check source identity even for an in-flight run;
                            # only its completion state is provisionally changed.
                            verify_run(repository, item, {**run, 'status': 'completed'},
                                       workflow=plan.get('collection_workflow', '.github/workflows/live-study.yml'))
                            row['state'] = 'running' if now <= due else 'overdue_running'
                        else:
                            verify_run(repository, item, run,
                                       workflow=plan.get('collection_workflow', '.github/workflows/live-study.yml'))
                            with tempfile.TemporaryDirectory(prefix='monitor-download-') as directory:
                                staging = Path(directory)
                                zipped = staging / 'archive.zip'
                                download_zip(repository, identifier, zipped)
                                archive = unpack_zip(zipped, staging, session)
                                row['state'] = archive_health(archive, path, session, slot, run)
                except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError,
                        tarfile.TarError, zipfile.BadZipFile):
                    # Never publish raw HTTP exceptions, tokens or remote text.
                    row['state'] = 'unverified'
            if row['state'] not in ('pending', 'running', 'eligible'):
                alerts.append(f"{plan['study_id']} {session}: {row['state']}")
            rows.append(row)
    if retention:
        alerts.append(f'{len(retention)} artifact(s) expired or expire within {expiry_days} days; preserve independent copies.')
    return {'as_of_utc': now.isoformat(), 'repository': repository,
            'inventory_available': not unavailable, 'scope': 'Collection health only; no markouts, prices or PnL.',
            'counts': dict(Counter(row['state'] for row in rows)), 'sessions': rows,
            'retention': retention, 'alerts': alerts, 'healthy': not alerts}


def render(state, out):
    out.mkdir(parents=True, exist_ok=False)
    write_json_atomic(out / 'status.json', state)
    lines = ['# Study operations', '', f"As of {state['as_of_utc']}", '', state['scope'], '',
             f"Artifact inventory available: {state['inventory_available']}", '',
             '| Study | Slot | State | Run |', '| --- | --- | --- | --- |']
    table = []
    for row in state['sessions']:
        link = f"[run]({row['run_url']})" if row['run_url'] else '—'
        lines.append(f"| {row['study_id']} | {row['session']} | {row['state']} | {link} |")
        table.append('<tr data-study="' + escape(row['study_id'], quote=True) + '"><td>' +
                     '</td><td>'.join(escape(row[k]) for k in ('study_id', 'session', 'state')) + '</td></tr>')
    lines += ['', '## Alerts', ''] + ['- ' + message for message in state['alerts']]
    write_text_atomic(out / 'summary.md', '\n'.join(lines) + '\n')
    studies = sorted({row['study_id'] for row in state['sessions']})
    options = ''.join('<option>' + escape(name) + '</option>' for name in studies)
    page = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            '<title>Study operations</title><style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:1rem}'
            'table{border-collapse:collapse;width:100%}td,th{padding:.5rem;text-align:left;border-bottom:1px solid #ddd}'
            'select{font:inherit;padding:.4rem}</style><h1>Study operations</h1><p>' + escape(state['as_of_utc']) +
            '</p><p>' + escape(state['scope']) + '</p><p>Inventory available: ' + str(state['inventory_available']) +
            '</p><p>' + escape(json.dumps(state['counts'])) + '</p><label>Study <select id="filter"><option value="">All</option>' +
            options + '</select></label><h2>Alerts</h2><ul>' + ''.join('<li>' + escape(a) + '</li>' for a in state['alerts']) +
            '</ul><table><thead><tr><th>Study</th><th>Slot</th><th>State</th></tr></thead><tbody>' + ''.join(table) +
            '</tbody></table><script>document.getElementById("filter").onchange=function(){'
            'document.querySelectorAll("tbody tr").forEach(r=>r.hidden=!!this.value&&r.dataset.study!==this.value)}'
            '</script></html>')
    write_text_atomic(out / 'dashboard.html', page)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--summary', type=Path)
    args = parser.parse_args(argv)
    state = inspect(args.repository)
    render(state, args.out)
    if args.summary:
        with args.summary.open('a') as stream:
            stream.write((args.out / 'summary.md').read_text())
    for message in state['alerts'][:10]:
        print('::error title=Study operations::' + message)
    print(json.dumps({'counts': state['counts'], 'retention_alerts': len(state['retention']),
                      'inventory_available': state['inventory_available']}))
    return 0 if state['healthy'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
