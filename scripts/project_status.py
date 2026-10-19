"""One status page separating software health, collection coverage and research evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import re

from cel.study import load_plan
from scripts.study_monitor import api_json, inspect as collection_inventory, PLANS
from scripts.successor_readiness import inspect as rehearsal_readiness


def build(repository):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('invalid repository')
    now = datetime.now(timezone.utc)
    state = {'schema_version':1, 'as_of_utc':now.isoformat(), 'repository':repository,
             'software':{'state':'unverified'}, 'collection':{'state':'unverified'},
             'successor':{'state':'unverified','study_activated':False}, 'research':[], 'warnings':[]}
    try:
        runs = api_json(f'repos/{repository}/actions/workflows/test.yml/runs?branch=main&per_page=10')['workflow_runs']
        trusted = [r for r in runs if r.get('path')=='.github/workflows/test.yml' and
                   r.get('head_branch')=='main' and (r.get('head_repository') or {}).get('full_name','').lower()==repository.lower()]
        completed = next((r for r in trusted if r.get('status')=='completed'),None)
        state['software'] = {'state':completed.get('conclusion','unknown') if completed else 'unverified',
                             'last_completed_run_url':completed.get('html_url') if completed else None,
                             'last_completed_created_at_utc':completed.get('created_at') if completed else None,
                             'latest_run_status':trusted[0].get('status') if trusted else 'unknown',
                             'scope':'CI pass/fail; does not establish market data or profitable execution'}
    except Exception:
        state['warnings'].append('Software inventory unavailable; no success inferred')
    try:
        inventory = collection_inventory(repository)
        state['collection'] = {'state':'healthy' if inventory['healthy'] else 'ALERT',
                               'as_of_utc':inventory['as_of_utc'], 'inventory_available':inventory['inventory_available'],
                               'counts':inventory['counts'], 'sessions':inventory['sessions'],
                               'alerts':inventory['alerts'], 'scope':inventory['scope']}
    except Exception:
        state['warnings'].append('Collection verification unavailable; do not infer missing or eligible observations')
    try:
        readiness = rehearsal_readiness(repository)
        state['successor'] = {'state':'readiness_passed' if readiness['activation_ready'] else 'not_ready',
                              'study_activated':False, 'readiness':readiness}
    except Exception:
        state['warnings'].append('Successor readiness unavailable or interrupted; activation remains blocked')
    for path in PLANS:
        plan,_ = load_plan(path)
        released = now.date() > datetime.fromisoformat(plan['end_date_utc']).date()
        state['research'].append({'study_id':plan['study_id'], 'outcomes_released_by_date':released,
                                  'result_state':'release reached; empirical report verification pending' if released else 'outcomes time-gated',
                                  'scope':'No returns or PnL evaluated by this status page'})
    return state


def from_observation(path):
    """Dated committed evidence is displayed as a snapshot, never a fresh API inspection."""
    observation = json.loads(path.read_text())
    return {'schema_version':1, 'as_of_utc':observation['as_of_utc'],
            'repository':'evananann/crypto-exec-lab', 'software':{'state':'see live CI'},
            'collection':{'state':'ALERT', 'as_of_utc':observation['as_of_utc'], 'counts':{'missing':len(observation['reported_missing_slots'])},
                          'sessions':[{'study_id':'btc-execution-v1','session':s,'state':'missing'} for s in observation['reported_missing_slots']],
                          'scope':'Dated hosted-monitor observation; later slots are not assessed in this snapshot'},
            'successor':{'state':'not_activated', 'study_activated':False},
            'research':[{'study_id':'all frozen studies','result_state':'No empirical outcome verified in this snapshot'}],
            'warnings':['Static snapshot from '+str(path)+'; open the live status workflow for a newer inspection']}


def render(state, out):
    out.mkdir(parents=True,exist_ok=False)
    (out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
    def esc(value):
        return escape(str(value),quote=True)
    sections = []
    software = state['software']
    sections.append('<section><h2>Software health</h2><p><strong>'+esc(software['state'])+'</strong></p><p>Last completed CI: '+esc(software.get('last_completed_created_at_utc','see live workflow'))+'. Passing tests do not establish successful collection.</p><p>'+esc(software.get('scope',''))+'</p></section>')
    collection = state['collection']
    counts = ', '.join(f'{k}: {v}' for k,v in sorted(collection.get('counts',{}).items())) or 'Unavailable'
    rows = ''.join('<tr><td>'+esc(r['study_id'])+'</td><td>'+esc(r['session'])+'</td><td>'+esc(r['state'])+'</td></tr>' for r in collection.get('sessions',[]))
    sections.append('<section><h2>Collection coverage</h2><p><strong>'+esc(collection['state'])+'</strong> — '+esc(counts)+'</p><p>'+esc(collection.get('scope','Verification unavailable'))+'</p><p>Coverage inspected at '+esc(collection.get('as_of_utc',state['as_of_utc']))+' UTC.</p><table><thead><tr><th>Study</th><th>UTC slot</th><th>State</th></tr></thead><tbody>'+rows+'</tbody></table></section>')
    research = ''.join('<li>'+esc(r['study_id'])+': '+esc(r['result_state'])+'</li>' for r in state['research'])
    sections.append('<section><h2>Research results</h2><ul>'+research+'</ul><p>Missing data are not zero returns. A green workflow does not establish alpha.</p></section>')
    successor = state['successor']
    readiness = successor.get('readiness',{})
    trials = readiness.get('records', [])
    latest = max(trials,key=lambda row:row.get('run_created_at_utc') or row.get('intended_start_utc') or '') if trials else None
    detail = ''
    if latest:
        assessment = latest.get('assessment',{})
        detail = '<p>Latest preserved attempt: collection healthy='+esc(assessment.get('collection_healthy','unverified'))+', events='+esc(assessment.get('events','unverified'))+', timing qualified='+esc(assessment.get('timing',{}).get('timing_qualified',False))+', original run conclusion='+esc(latest.get('source_run_conclusion','unverified'))+'.</p>'
    sections.append('<section><h2>Successor readiness</h2><p>'+esc(successor['state'])+'; study activated: '+esc(successor['study_activated'])+'</p><p>Qualifying prospective trials: '+esc(readiness.get('qualifying_prospective_rehearsals','unverified'))+'. Transport-only rehearsals do not qualify.</p>'+detail+'</section>')
    approved = readiness.get('approved_trials')
    if approved:
        trial_rows = ''.join('<tr><td>'+esc(row['trial_id'])+'</td><td>'+esc(row['intended_start_utc'])+'</td><td>'+esc(row['state'])+'</td></tr>' for row in approved['trials'])
        sections.append('<section><h2>Approved prospective trials</h2><p>GitHub timing is unproven. Every named trial must qualify; later recordings cannot replace these dates.</p><table><thead><tr><th>Trial</th><th>Intended start (UTC)</th><th>Verified state</th></tr></thead><tbody>'+trial_rows+'</tbody></table></section>')
    warnings = ''.join('<li>'+esc(w)+'</li>' for w in state.get('warnings',[]))
    page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Crypto execution lab status</title><style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;background:#f5f7fa;color:#172335}section{background:white;padding:1rem;margin:1rem 0;border:1px solid #ccd5df;border-radius:8px}table{border-collapse:collapse;width:100%}td,th{padding:.4rem;text-align:left;border-bottom:1px solid #ddd}p{line-height:1.5}</style><h1>Crypto execution lab status</h1><p>Inspected at '+esc(state['as_of_utc'])+' (UTC). Each panel describes a separate kind of evidence.</p><ul>'+warnings+'</ul>'+''.join(sections)+'</html>'
    (out/'index.html').write_text(page)
    summary = '# Project status\n\nInspected at '+state['as_of_utc']+' UTC.\n\n'
    summary += '- Software: '+str(software['state'])+'\n- Collection: '+str(collection['state'])+'; '+counts+'\n- Successor: '+str(successor['state'])+'; activated=False\n- Research: '+ '; '.join(r['result_state'] for r in state['research'])+'\n\nDownload the project-status artifact and open index.html.\n'
    (out/'summary.md').write_text(summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--repository')
    group.add_argument('--observation',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--summary',type=Path)
    args = parser.parse_args()
    state = build(args.repository) if args.repository else from_observation(args.observation)
    summary = render(state,args.out)
    if args.summary:
        with args.summary.open('a') as stream:
            stream.write(summary)
    if state['warnings']:
        print('::warning title=Project status::Some evidence is unavailable or dated; see status.json')
    software = state['software']['state']
    if software not in ('success', 'failure', 'cancelled', 'timed_out', 'action_required', 'neutral', 'skipped', 'unverified'):
        software = 'unknown'
    collection = state['collection']['state']
    if collection not in ('healthy', 'ALERT', 'unverified'):
        collection = 'unknown'
    counts = state['collection'].get('counts', {})
    def count(key):
        value = counts.get(key, 0)
        return value if type(value) is int and value >= 0 else 0
    successor = state['successor']['state']
    if successor not in ('not_ready', 'readiness_passed', 'unverified', 'not_activated'):
        successor = 'unknown'
    print(f'::notice title=Project status::software={software} collection={collection} missing={count("missing")} eligible={count("eligible")} unverified={count("unverified")} successor={successor} study_activated=False')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
