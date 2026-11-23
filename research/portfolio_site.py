"""Allowlisted research portfolio site and explicit GitHub Pages setup gate."""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import shutil
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'evananann/crypto-exec-lab'


def build(output):
    source = ROOT/'reports/opportunity'
    manifest = json.loads((source/'checksums.json').read_text())
    if set(manifest) != {'opportunity.json', 'hero.png', 'hero.svg', 'leadlag.png', 'README.md'}:
        raise ValueError('unexpected synthetic presentation inventory')
    for name, expected in manifest.items():
        if (Path(name).name != name or (source/name).is_symlink()
                or hashlib.sha256((source/name).read_bytes()).hexdigest() != expected):
            raise ValueError('synthetic presentation checksum mismatch')
    report = json.loads((source/'opportunity.json').read_text())
    if report.get('synthetic') is not True or report.get('market_tapes_read') != 0:
        raise ValueError('portfolio site accepts synthetic opportunity fixture only')
    output.mkdir(parents=True, exist_ok=False)  # never mix stale output with a new publication
    for name in ('hero.png', 'leadlag.png'):
        shutil.copyfile(source/name, output/name)
    lab = ROOT/'reports/trading_decision/decision.html'
    expected = json.loads((lab.parent/'checksums.json').read_text())[lab.name]
    if hashlib.sha256(lab.read_bytes()).hexdigest() != expected:
        raise ValueError('cost lab checksum mismatch')
    shutil.copyfile(lab, output/'cost-lab.html')
    style = '''<meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font:17px/1.65 system-ui,sans-serif;color:#142238;background:#f6f8fb;margin:0}main{max-width:1120px;margin:auto;padding:36px 22px}h1{font-size:2.4rem;line-height:1.15}h2{margin-top:2em}a{color:#174f9e}img{max-width:100%;height:auto;background:white}nav{display:flex;gap:22px;flex-wrap:wrap}p{max-width:85ch}.badge{color:#795000;font-weight:700}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:9px;border-bottom:1px solid #cad3df}.scroll{overflow:auto}.button{display:inline-block;padding:10px 18px;background:#174f9e;color:white;border-radius:6px;text-decoration:none}footer{border-top:1px solid #cad3df;margin-top:3em;padding-top:1em}</style>'''
    def page(title, content):
        return '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>'+escape(title)+'</title>'+style+'</head><body><main><nav><a href="index.html">Research overview</a><a href="cost-lab.html">Interactive cost lab</a><a href="experiment.html">Maker &amp; lead–lag examples</a><a href="followon.html">Matched-scale sensitivity lab</a><a href="https://github.com/evananann/crypto-exec-lab/actions/workflows/self-review.yml">Continuous review</a></nav>'+content+'<footer><a href="https://github.com/'+REPOSITORY+'">Source, tests and evidence</a> · Research only; isolated demo transactions, no live-money execution.</footer></main></body></html>\n'
    (output/'index.html').write_text(page('BTC cross-venue research', '''<p class="badge">Released primary evidence · incomplete coverage</p><h1>Can cross-venue price discovery survive execution costs?</h1><p>A BTC perpetual research case study with causal replay, frozen hypotheses, explicit costs, queue counterfactuals and uncertainty. Current decision: no live deployment; the registered study is inconclusive.</p><p><b>Released November 22:</b> −4.6954bps observed entry-net markout; 23/56 eligible slots, three holdout dates. Formal conclusion: inconclusive. <a href="released-study.html">Read the authenticated result and limits</a>.</p><img src="hero.png" alt="Synthetic Binance jump and OKX response, beside a waterfall charging both spreads and actual-notional fees. No empirical result."><p><a class="button" href="cost-lab.html">Explore the interactive exit-cost lab</a></p><p>A positive entry-to-mid markout needs an executable exit. The lab starts with an already-entry-net markout; the figure above starts from gross mid movement. Neither is a calibrated market estimate.</p><h2>A constructive alternative to taker arbitrage</h2><p>Test whether a received leader jump can help cancel a vulnerable maker quote before it fills. Avoided adverse fills, cancellation races and missed profitable fills must all count. The mechanism is a future research hypothesis, not an established edge.</p><p><a href="experiment.html">Inspect every fixed maker case and the synthetic lead–lag diagnostic</a>.</p><p><a href="workbench.html">Open the decision workbench: historical pilot, collection evidence and synthetic execution controls</a>.</p><p><a href="execution-validation.html">Actual demo execution: predicted versus observed fills, fees and timing</a> (independent spot batch; not a perpetual trading result).</p><p><a href="research-memo.pdf">Two-page research memo (PDF)</a> · <a href="research-memo.html">HTML version</a> · <a href="execution-sensitivity.json">Cost scenarios</a>.</p><h2>What is established?</h2><p>An authenticated unfavorable observed primary result with incomplete coverage, reconciled independent demo accounting and synthetic controls. Predictive power, maker savings, fill probabilities, physical propagation latency and profitable execution remain unverified. The primary result is released; separate replications are reported independently and never pooled.</p>'''))
    rows = []
    for row in report['maker_scenarios']:
        values = [row['side'], row['future_mid'], row['cancel_delay_ms'], row['trade_before_cancel'],
                  f"{row['comparison']['cancellation_value_usdt']:.6f}"]
        rows.append('<tr>'+''.join('<td>'+escape(str(value))+'</td>' for value in values)+'</tr>')
    content = '''<p class="badge">Future draft · synthetic only</p><h1>Maker quote management and lead–lag</h1><p>Each maker order joins behind assumed displayed depth. Only explicit executed trade volume can fill it. Cancellation takes time, fills before acknowledgement remain inventory, and unknown cancellation location is a sensitivity assumption.</p><h2>Receive-clock correlation</h2><img src="leadlag.png" alt="Correlation versus lag for three sampling scales on a synthetic 30ms delayed-copy tape."><p>Positive lag denotes leader-first association. The toy generator deliberately delays the follower by 30ms. This checks the estimator; transport, asynchronous sampling and shared news prevent interpreting an empirical peak as physical transmission proof.</p><h2>All maker counterfactuals</h2><p>Cancel-minus-keep values mark hypothetical inventory to a future mid. They include missed profitable fills and are not realized round-trip profits. Prices, queue depth, trade flow and future mids are invented.</p><div class="scroll"><table><thead><tr><th>Side</th><th>Future mid</th><th>Cancel delay, ms</th><th>Trade wins tie?</th><th>Value difference, USDT</th></tr></thead><tbody>'''+''.join(rows)+'''</tbody></table></div><p>No best side, lag, condition or cancellation assumption was selected.</p>'''
    (output/'experiment.html').write_text(page('Synthetic maker and lead–lag examples', content))
    from research.decision_study.workbench import build as build_workbench
    build_workbench(output/'workbench.html')
    roadmap = ROOT/'reports/roadmap_20261114'
    manifest = json.loads((roadmap/'checksums.json').read_text())
    for name in ('followon.html','matched-study.json'):
        if hashlib.sha256((roadmap/name).read_bytes()).hexdigest() != manifest[name]:
            raise ValueError('follow-on evidence checksum mismatch')
    followon = json.loads((roadmap/'matched-study.json').read_text())
    if followon.get('evidence_status') != 'SYNTHETIC' or followon.get('market_tapes_read') != 0:
        raise ValueError('follow-on site accepts only the synthetic independent study')
    shutil.copyfile(roadmap/'followon.html',output/'followon.html')
    demo = ROOT/'reports/spot_validation_20261115'
    demo_checksums = json.loads((demo/'checksums.json').read_text())
    for source_name, target_name in (('index.html','execution-validation.html'),
                                     ('validation.json','validation.json'),
                                     ('protocol.json','protocol.json')):
        if hashlib.sha256((demo/source_name).read_bytes()).hexdigest() != demo_checksums[source_name]:
            raise ValueError('demo validation evidence checksum mismatch')
        shutil.copyfile(demo/source_name, output/target_name)
    memo = ROOT/'reports/execution_sensitivity_20261116'
    memo_checksums = json.loads((memo/'checksums.json').read_text())
    for source_name,target_name in (('memo.html','historical-research-memo.html'),
                                    ('RESEARCH_MEMO.pdf','historical-research-memo.pdf'),
                                    ('sensitivity.json','execution-sensitivity.json')):
        if hashlib.sha256((memo/source_name).read_bytes()).hexdigest() != memo_checksums[source_name]:
            raise ValueError('execution memo checksum mismatch')
        shutil.copyfile(memo/source_name,output/target_name)
    released = ROOT/'reports/released_successor_20261122'
    released_checksums = json.loads((released/'checksums.json').read_text())
    for name in ('released-study.html','released-study.json','released-report.json','released-note.md'):
        if hashlib.sha256((released/name).read_bytes()).hexdigest() != released_checksums[name]:
            raise ValueError('released evidence checksum mismatch')
        shutil.copyfile(released/name,output/name)
    shutil.copyfile(released/'released-study.html',output/'research-memo.html')
    if hashlib.sha256((released/'RESEARCH_MEMO.pdf').read_bytes()).hexdigest() != released_checksums['RESEARCH_MEMO.pdf']:
        raise ValueError('released memo checksum mismatch')
    shutil.copyfile(released/'RESEARCH_MEMO.pdf',output/'research-memo.pdf')
    formal = ROOT/'reports/formal_decision_20261123'
    formal_checksums = json.loads((formal/'checksums.json').read_text())
    for original, published in (('decision.html', 'formal-decision.html'),
                                ('decision.json', 'formal-decision.json')):
        if hashlib.sha256((formal/original).read_bytes()).hexdigest() != formal_checksums[original]:
            raise ValueError('formal decision evidence checksum mismatch')
        shutil.copyfile(formal/original, output/published)
    home = output/'index.html'
    home.write_text(home.read_text().replace('<h2>What is established?</h2>',
        '<h2>Current formal decision — November 23</h2><p><a href="formal-decision.html">'
        'Read the current decision and timestamp/capture diagnosis</a> · '
        '<a href="formal-decision.json">Structured findings</a>. '
        'Do not deploy. The paired follow-on is not enrolled; transport qualification '
        'failed and incremental Binance value remains unestablished.</p><h2>What is established?</h2>'))
    files = sorted(p.name for p in output.iterdir())
    (output/'site-checksums.json').write_text(json.dumps({name: hashlib.sha256((output/name).read_bytes()).hexdigest() for name in files}, indent=2)+'\n')


def pages_request(method, repository, token, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    request = Request('https://api.github.com/repos/'+repository+'/pages', data=body, method=method,
                      headers={'Authorization': 'Bearer '+token, 'Accept': 'application/vnd.github+json',
                               'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b'{}')
    except HTTPError as error:
        if error.code in (403, 404, 409, 422):
            return error.code, {}
        raise


def pages_gate(repository, token, request=pages_request):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', repository):
        raise ValueError('invalid repository')
    status, site = request('GET', repository, token)
    if status == 404:
        status, site = request('POST', repository, token, {'build_type': 'workflow'})
    elif status == 200 and site.get('build_type') != 'workflow':
        status, site = request('PUT', repository, token, {'build_type': 'workflow'})
    ready = status in (200, 201, 204)
    return {'ready': ready, 'status': status,
            'reason': 'Pages configured for Actions' if ready else 'Repository administrator must enable Settings > Pages > Source: GitHub Actions; built preview remains available as an artifact.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['build', 'pages-gate'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.mode == 'build':
        if args.output is None:
            parser.error('--output is required')
        build(args.output)
        return
    result = pages_gate(os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'])
    print(json.dumps(result))
    with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
        stream.write('ready='+str(result['ready']).lower()+'\n')
    if not result['ready']:
        print('::notice title=Pages setup pending::'+result['reason']+' HTTP '+str(result['status']))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write(result['reason']+' HTTP '+str(result['status'])+'\n')


if __name__ == '__main__':
    main()
