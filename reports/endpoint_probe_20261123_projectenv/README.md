# Current OKX public endpoint and unit probe

A separately declared twenty-second probe using the installed project Python
received **528 BBO records** on `wss://ws.okx.com/ws/v5/public` (default TLS port 443).
The [protocol](protocol.json), [report](report.json), normalized sample and public
instrument snapshots are preserved. Official global API docs list this endpoint;
the older raw rehearsal retained a notice that port 8443 would be retired.

Instrument identity and ctVal/ctMult/ctValCcy/settlement/type matched in observations
before and after capture. For this probe, `0.01 * 1 = 0.01 BTC/contract` was applied
to native OKX sizes. The raw instrument response JSON bytes were reconstructed
from the preserved parsed objects **only after an exact SHA-256 match** to the
digests recorded by the acquisition code; matching `.response.json` files are
included. No unverifiable raw response was invented. Future snapshots additionally
retain raw bytes as base64 directly.

The exact executed endpoint and normalizer source snapshots match the hashes in
the protocol. The maintained normalizer subsequently added stricter Binance
identity handling and explicit unit labels; the historical snapshots are retained.
The current driver also returns nonzero on incomplete probes. No old source or
failed probe was overwritten to make the endpoint appear successful.

This is a narrow connectivity/OKX-unit observation, not a full normalized joint
Binance/OKX dataset. It does not prove unchanged metadata between samples,
independent UTC accuracy, production uptime, fill quality or scientific enrollment.
No strategy outcome or order was used. The future deployment example now uses the
verified endpoint; frozen old collectors and their original recordings remain.
