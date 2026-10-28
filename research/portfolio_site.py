"""Allowlisted synthetic portfolio site and explicit GitHub Pages setup gate."""
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
        return '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>'+escape(title)+'</title>'+style+'</head><body><main><nav><a href="index.html">Research overview</a><a href="cost-lab.html">Interactive cost lab</a><a href="experiment.html">Maker &amp; lead–lag examples</a></nav>'+content+'<footer><a href="https://github.com/'+REPOSITORY+'">Source, tests and evidence</a> · Public-data research; no orders.</footer></main></body></html>\n'
    (output/'index.html').write_text(page('BTC cross-venue research', '''<p class="badge">Synthetic demonstrations · empirical outcomes pending</p><h1>Can cross-venue price discovery survive execution costs?</h1><p>A BTC perpetual research case study with causal replay, frozen hypotheses, explicit costs, queue counterfactuals and uncertainty. Current decision: remain in research.</p><img src="hero.png" alt="Synthetic Binance jump and OKX response, beside a waterfall charging both spreads and actual-notional fees. No empirical result."><p><a class="button" href="cost-lab.html">Explore the interactive exit-cost lab</a></p><p>A positive entry-to-mid markout needs an executable exit. The lab starts with an already-entry-net markout; the figure above starts from gross mid movement. Neither is a calibrated market estimate.</p><h2>A constructive alternative to taker arbitrage</h2><p>Test whether a received leader jump can help cancel a vulnerable maker quote before it fills. Avoided adverse fills, cancellation races and missed profitable fills must all count. The mechanism is a future research hypothesis, not an established edge.</p><p><a href="experiment.html">Inspect every fixed maker case and the synthetic lead–lag diagnostic</a>.</p><h2>What is established?</h2><p>Auditable software mechanics and synthetic examples. Predictive power, maker savings, fill probabilities, physical propagation latency and profitable execution remain unverified. Registered scientific outcomes are time-gated.</p>'''))
    rows = []
    for row in report['maker_scenarios']:
        values = [row['side'], row['future_mid'], row['cancel_delay_ms'], row['trade_before_cancel'],
                  f"{row['comparison']['cancellation_value_usdt']:.6f}"]
        rows.append('<tr>'+''.join('<td>'+escape(str(value))+'</td>' for value in values)+'</tr>')
    content = '''<p class="badge">Future draft · synthetic only</p><h1>Maker quote management and lead–lag</h1><p>Each maker order joins behind assumed displayed depth. Only explicit executed trade volume can fill it. Cancellation takes time, fills before acknowledgement remain inventory, and unknown cancellation location is a sensitivity assumption.</p><h2>Receive-clock correlation</h2><img src="leadlag.png" alt="Correlation versus lag for three sampling scales on a synthetic 30ms delayed-copy tape."><p>Positive lag denotes leader-first association. The toy generator deliberately delays the follower by 30ms. This checks the estimator; transport, asynchronous sampling and shared news prevent interpreting an empirical peak as physical transmission proof.</p><h2>All maker counterfactuals</h2><p>Cancel-minus-keep values mark hypothetical inventory to a future mid. They include missed profitable fills and are not realized round-trip profits. Prices, queue depth, trade flow and future mids are invented.</p><div class="scroll"><table><thead><tr><th>Side</th><th>Future mid</th><th>Cancel delay, ms</th><th>Trade wins tie?</th><th>Value difference, USDT</th></tr></thead><tbody>'''+''.join(rows)+'''</tbody></table></div><p>No best side, lag, condition or cancellation assumption was selected.</p>'''
    (output/'experiment.html').write_text(page('Synthetic maker and lead–lag examples', content))
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
