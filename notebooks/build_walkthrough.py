"""Generate a self-contained synthetic notebook; never reads market tapes."""
from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(['local_ts', 'venue', 'bid', 'ask', 'bid_sz', 'ask_sz', 'quantity_unit'])
    for t in range(0, 300001, 100):
        episode, phase = divmod(t, 10000)
        base = 60000+20*math.sin(episode)
        amplitude = (2, 6, 12, 40, 100)[episode % 5]
        direction = 1 if episode % 2 == 0 else -1
        leader = base+direction*amplitude*(phase >= 2000)
        follower = base+direction*amplitude*max(0, min(1, (phase-2100)/500))
        for venue, mid in (('binance', leader), ('okx', follower)):
            writer.writerow([t, venue, f'{mid-1:.8f}', f'{mid+1:.8f}', '.01', '.02', 'BTC'])
    data = stream.getvalue().encode()
    path = ROOT/'notebooks/data/synthetic_5min.csv'
    path.write_bytes(data)
    tool = (ROOT/'research/trading_decision.py').read_bytes()
    cells = []
    def md(value):
        cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': value.splitlines(True)})
    def code(value):
        cells.append({'cell_type': 'code', 'execution_count': None, 'metadata': {}, 'outputs': [], 'source': value.splitlines(True)})
    md('''# Cross-venue thesis walkthrough — synthetic only

This notebook loads a committed **five-minute invented BBO tape** (6,002 rows).
It is not anonymized market data. The generator deliberately inserts delayed,
directional follower responses; detecting them is not an alpha discovery.

Run all cells locally or in Colab. Data and the exact cost-bridge source are
embedded as checksummed compressed fallbacks, so a downloaded notebook does not
need a repository checkout. NumPy and Matplotlib are used; the setup cell installs
them only if missing. No exchange access, account, raw study archive or order is used.

The active study is unchanged and outcome-gated. All confidence bands below are
**toy episode-bootstrap intervals**, not evidence of market predictability.
''')
    code('''import base64
import csv
import gzip
import hashlib
import importlib.util
import io
import pathlib
import subprocess
import sys
import tempfile
from decimal import Decimal
for package in ("numpy", "matplotlib"):
    if importlib.util.find_spec(package) is None:
        subprocess.run([sys.executable, "-m", "pip", "install", package], check=True)
''')
    code('''import numpy as np
import matplotlib.pyplot as plt
get_ipython().run_line_magic("matplotlib", "inline")
print("NumPy", np.__version__, "· all inputs are synthetic")
''')
    code('''DATA_SHA256 = '''+repr(hashlib.sha256(data).hexdigest())+'''
TOOL_SHA256 = '''+repr(hashlib.sha256(tool).hexdigest())+'''
DATA_GZIP_BASE64 = '''+repr(base64.b64encode(gzip.compress(data, mtime=0)).decode())+'''
TOOL_GZIP_BASE64 = '''+repr(base64.b64encode(gzip.compress(tool, mtime=0)).decode())+'''
local_data = pathlib.Path("notebooks/data/synthetic_5min.csv")
data = local_data.read_bytes() if local_data.exists() else gzip.decompress(base64.b64decode(DATA_GZIP_BASE64))
assert hashlib.sha256(data).hexdigest() == DATA_SHA256
local_tool = pathlib.Path("research/trading_decision.py")
tool = local_tool.read_bytes() if local_tool.exists() else gzip.decompress(base64.b64decode(TOOL_GZIP_BASE64))
assert hashlib.sha256(tool).hexdigest() == TOOL_SHA256
scratch = tempfile.TemporaryDirectory()
module_path = pathlib.Path(scratch.name)/"walkthrough_bridge.py"
module_path.write_bytes(tool)
spec = importlib.util.spec_from_file_location("walkthrough_bridge", module_path)
cost = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cost)
rows = list(csv.DictReader(io.StringIO(data.decode())))
assert len(rows) == 6002
print("Rows:", len(rows), "· duration:", int(rows[-1]["local_ts"])/1000, "seconds")
print("Fixture SHA-256:", DATA_SHA256)
print("Cost tool SHA-256:", TOOL_SHA256)
''')
    md('''## Receive-time event curve

The 30 signal times and directions are fixed by the toy generator, never selected
from profitable outcomes. Use only quotes at or before each query timestamp.
Negative offsets show pre-signal behavior. A 100 ms sample grid cannot establish
submillisecond order or physical venue propagation time.
''')
    code('''follower = [r for r in rows if r["venue"] == "okx"]
times = np.array([int(r["local_ts"]) for r in follower])
mids = np.array([(float(r["bid"])+float(r["ask"]))/2 for r in follower])
offsets = np.array([-200, -100, 0, 50, 100, 250, 500, 1000])
curves = []
for episode in range(30):
    signal = episode*10000+2000
    direction = 1 if episode % 2 == 0 else -1
    query = signal+offsets
    index = np.searchsorted(times, query, side="right")-1
    assert np.all(index >= 0) and np.all(query <= times[-1])
    assert np.all(query-times[index] <= 100)
    baseline = mids[np.searchsorted(times, signal, side="right")-1]
    curves.append(direction*(mids[index]/baseline-1)*10000)
curves = np.array(curves)
rng = np.random.default_rng(0)
indices = rng.integers(0, len(curves), size=(2000, len(curves)))
bootstrap = curves[indices].mean(axis=1)
lower, upper = np.quantile(bootstrap, [.025, .975], axis=0)
mean = curves.mean(axis=0)
fig, ax = plt.subplots(figsize=(9, 4))
ax.plot(offsets, mean, marker="o", label="Mean signed toy follower mid response")
ax.fill_between(offsets, lower, upper, alpha=.2, label="95% pointwise toy episode-bootstrap band")
# Exact long break-even at an illustrative 60,000 initial mid; both $1 half-spreads and both 5bps fees.
hurdle_mid = Decimal("60001")*(1+Decimal(".0005"))/(1-Decimal(".0005"))+1
hurdle_bps = float((hurdle_mid/Decimal("60000")-1)*10000)
ax.axhline(hurdle_bps, color="firebrick", ls="--", label="Illustrative long full-cost hurdle at 60,000")
ax.set(xlabel="Time from generated signal (ms)", ylabel="Gross response (bps of event baseline)",
       title="Synthetic mechanism and cost scale — no market estimate")
ax.legend(fontsize=8)
ax.grid(alpha=.2)
plt.show()
print("Toy episodes:", len(curves), "· illustrative gross hurdle:", round(hurdle_bps, 4), "bps")
''')
    md('''These bands resample invented episodes as if independent and are pointwise,
unadjusted across horizons. One five-minute tape supplies no independent market
dates. Missing and unavailable observations cannot be turned into zero returns.
The long hurdle is a stated price/cost example, not a fitted trading rule or a
common exact hurdle for every side, episode, size or execution path.

## Exact entry-net-to-exit cash bridge

The input +2 bps below has **already paid entry spread and entry fee**. Add the
exit and its actual-notional fee; do not charge entry fees twice. This arithmetic
example is separate from the gross response curve above.
''')
    code('''bridge = cost.bridge(markout_bps="2", entry_price="60000", quantity_btc=".001",
                     entry_fee_bps="5", exit_fee_bps="5", exit_spread_bps="0")
assert bridge["net_roundtrip_usdt"] == Decimal("-.018021")
for name in ("implied_horizon_mid", "entry_fee_usdt", "exit_fee_usdt", "net_roundtrip_usdt",
             "break_even_entry_net_markout_bps"):
    print(name, bridge[name])
fig, ax = plt.subplots(figsize=(7, 3))
ax.bar(["Entry-net markout", "Closed round trip"], [2, float(bridge["net_roundtrip_bps"])],
       color=["steelblue", "firebrick"])
ax.axhline(0, color="black", lw=.8)
ax.set(ylabel="bps of executable entry notional", title="A positive primary markout can fail liquidation costs")
plt.show()
''')
    md('''## What would make this empirical?

A verified released dataset, enough independent dates, chronological holdout,
fixed conditions, valid dependence-aware inference and actual execution inputs.
Continuous OFI, impact sensitivity, multiplicity/DSR/PBO and columnar joins are
separate tools; they do not make these synthetic returns measured alpha.
The notebook sends no orders. A negative or inconclusive scientific result remains useful.
''')
    for i, cell in enumerate(cells):
        cell['id'] = f'walkthrough-{i:02}'
    notebook = {'nbformat': 4, 'nbformat_minor': 5, 'metadata': {
        'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
        'language_info': {'name': 'python'}, 'synthetic': True, 'market_tapes_read': 0}, 'cells': cells}
    (ROOT/'notebooks/01_thesis_walkthrough.ipynb').write_text(json.dumps(notebook, indent=1)+'\n')
    (ROOT/'notebooks/data/checksums.json').write_text(json.dumps({'synthetic_5min.csv': hashlib.sha256(data).hexdigest()}, indent=2)+'\n')


if __name__ == '__main__':
    build()
