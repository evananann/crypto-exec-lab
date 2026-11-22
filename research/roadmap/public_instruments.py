"""Fixed-host public instrument snapshots; never retroactively qualifies old tapes."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ENDPOINTS = {
    "binance": "https://fapi.binance.com/fapi/v1/exchangeInfo",
    "okx": "https://www.okx.com/api/v5/public/instruments?instType=SWAP&instId=BTC-USDT-SWAP",
}


def parse(venue, body):
    data = json.loads(body)
    if venue == "binance":
        selected = [r for r in data["symbols"] if r.get("symbol") == "BTCUSDT"]
        if len(selected) != 1:
            raise ValueError("Missing/duplicate Binance instrument")
        r = selected[0]
        if any(
            r.get(k) != v
            for k, v in {
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "marginAsset": "USDT",
                "contractType": "PERPETUAL",
                "status": "TRADING",
            }.items()
        ):
            raise ValueError("Unsupported Binance contract identity")
        metadata = {
            k: r[k]
            for k in ("symbol", "baseAsset", "quoteAsset", "marginAsset", "contractType", "status")
        }
        metadata["native_quantity_unit"] = "BTC"
        metadata["unit_basis"] = (
            "USDT-M BTCUSDT bookTicker quantity convention, bound to the base-asset identity; no price-derived multiplier"
        )
    elif venue == "okx":
        if data.get("code") != "0" or len(data.get("data", [])) != 1:
            raise ValueError("Missing/duplicate OKX instrument")
        r = data["data"][0]
        if any(
            r.get(k) != v
            for k, v in {
                "instId": "BTC-USDT-SWAP",
                "ctType": "linear",
                "ctValCcy": "BTC",
                "settleCcy": "USDT",
                "state": "live",
            }.items()
        ):
            raise ValueError("Unsupported OKX contract identity")
        metadata = {"instrument": r}
    else:
        raise ValueError("Unsupported venue")
    return metadata | {
        "source_url": ENDPOINTS[venue],
        "source_sha256": hashlib.sha256(body).hexdigest(),
        "raw_body_base64": base64.b64encode(body).decode(),
        "contemporaneous_verified": False,
        "scope": "Public metadata observation only; pair matching snapshots around a new same-host recording before setting a contemporaneous binding. A current snapshot cannot qualify historical native quantities.",
    }


def fetch(venue):
    if venue not in ENDPOINTS:
        raise ValueError("Unsupported venue")
    start = time.monotonic_ns()
    try:
        with urlopen(
            Request(ENDPOINTS[venue], headers={"User-Agent": "crypto-exec-lab-readonly/1.0"}),
            timeout=20,
        ) as response:
            body = response.read(8_000_001)
    except (HTTPError, URLError, TimeoutError):
        raise RuntimeError(
            "Public instrument host unavailable; no alternate host, proxy or credential fallback attempted"
        ) from None
    if len(body) > 8_000_000:
        raise ValueError("Instrument response exceeds bound")
    return parse(venue, body) | {
        "request_start_monotonic_ns": start,
        "receive_monotonic_ns": time.monotonic_ns(),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--venue", choices=tuple(ENDPOINTS), required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result = fetch(a.venue)
    with a.out.open("x") as f:
        json.dump(result, f, indent=2)
