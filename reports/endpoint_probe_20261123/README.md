# Retained first endpoint probe — failed before connection

This planned twenty-second probe used the system Python, which did not have the
project's `websocket-client` dependency. The collector exited after approximately
0.25 seconds, before any BBO record. [report.json](report.json) is explicitly
`PROBE_INCOMPLETE`; matching public instrument snapshots do not make it a successful
capture. This failure is retained rather than relabeled or erased.

The separate [project-environment probe](../endpoint_probe_20261123_projectenv/README.md)
uses the installed frozen project environment. Neither attempt is enrolled in a
scientific cohort, and neither computes strategy outcomes or submits an order.
The maintained CLI now returns nonzero for incomplete probes. The executed source
snapshots preserve the earlier exact versions against protocol hashes.
