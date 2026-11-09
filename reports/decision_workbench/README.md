# Decision workbench

Open `index.html` locally or serve this directory. It is a self-contained,
read-only dashboard with embedded committed evidence and synthetic controls.
No exchange connection, remote data fetch or order submission is present.

See [the guide](../../docs/DECISION_WORKBENCH.md) for methods and limits.
The paired historical pilot is actual exploratory data, while equity charts,
scenario controls and downloadable paper CSVs are explicitly synthetic.
External paper-runner parity remains unverified without independent fill logs.

`controls.json` exports the synthetic summaries and portfolio ledgers.
Each `*-inputs.json` and `*-fills.csv` pair can reproduce the paper adapter test.
Screenshots and `browser-check.json` record desktop/mobile browser validation;
they do not establish live publication. The Pages workflow may still require
administrator configuration. The separate decision-workbench workflow builds
a downloadable artifact even when live Pages is unavailable.
