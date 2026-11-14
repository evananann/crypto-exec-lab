"""GET-only OKX demo evidence export; never submits or cancels orders."""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

ORIGINS = {"eea": "https://eea.okx.com", "global": "https://www.okx.com"}
KEY_NAMES = ("OKX_DEMO_API_KEY", "OKX_DEMO_API_SECRET", "OKX_DEMO_PASSPHRASE")
ALLOWED = {
    "/api/v5/public/time",
    "/api/v5/public/instruments",
    "/api/v5/account/config",
    "/api/v5/trade/fills-history",
    "/api/v5/trade/orders-history-archive",
}
REPO = Path(__file__).resolve().parents[2]


class DemoError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def signature(secret, message):
    return base64.b64encode(
        hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()
    ).decode()


def headers(credentials, timestamp, path):
    return {
        "OK-ACCESS-KEY": credentials[0],
        "OK-ACCESS-SIGN": signature(credentials[1], timestamp + "GET" + path),
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": credentials[2],
        "x-simulated-trading": "1",
        "Accept": "application/json",
        "User-Agent": "crypto-exec-lab-readonly/1.0",
    }


class Client:
    allowed_paths = ALLOWED

    def __init__(self, region="eea"):
        if region not in ORIGINS:
            raise DemoError("Unsupported OKX region")
        self.origin = ORIGINS[region]
        missing = [n for n in KEY_NAMES if not os.environ.get(n)]
        if missing:
            raise DemoError("Missing secure runtime variables: " + ", ".join(missing))
        self.credentials = tuple(os.environ[n] for n in KEY_NAMES)
        self.opener = build_opener(NoRedirect())

    def get(self, path, params=None, *, private=True):
        if path not in self.allowed_paths:
            raise DemoError("Endpoint not allowed by read-only client")
        query = path + ("?" + urlencode(params) if params else "")
        if private:
            stamp = int(self.get("/api/v5/public/time", private=False)[0]["ts"])
            timestamp = (
                datetime.fromtimestamp(stamp / 1000, timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
            request_headers = headers(self.credentials, timestamp, query)
        else:
            request_headers = {
                "Accept": "application/json",
                "x-simulated-trading": "1",
                "User-Agent": "crypto-exec-lab-readonly/1.0",
            }
        request = Request(self.origin + query, headers=request_headers, method="GET")
        try:
            with self.opener.open(request, timeout=20) as response:
                payload = json.load(response)
        except HTTPError as exc:
            try:
                error_payload = json.loads(exc.read(8192))
                api_code = str(error_payload.get("code", ""))
            except (ValueError, AttributeError):
                api_code = ""
            safe_code = api_code if re.fullmatch(r"[0-9]{1,6}", api_code) else "unknown"
            raise DemoError(
                "OKX HTTP "
                + str(exc.code)
                + "; API code "
                + safe_code
                + "; response body suppressed"
            ) from None
        except (URLError, TimeoutError):
            raise DemoError(
                "OKX transport unavailable; credentials and response suppressed"
            ) from None
        if payload.get("code") != "0":
            code = str(payload.get("code", ""))
            raise DemoError(
                "OKX API code "
                + (code if re.fullmatch(r"[0-9]{1,6}", code) else "unknown")
                + "; message suppressed"
            )
        if not isinstance(payload.get("data"), list):
            raise DemoError("Unexpected OKX response schema")
        return payload["data"]

    def check(self):
        data = self.get("/api/v5/account/config")
        if len(data) != 1 or {v.strip() for v in data[0].get("perm", "").split(",")} != {
            "read_only"
        }:
            raise DemoError("A demo key with Read permission only is required")
        return {
            "authenticated": True,
            "read_only_permission_verified": True,
            "simulated_trading_header": True,
        }

    def pages(self, path, key, *, end, max_pages=20):
        rows, seen, cursors = [], set(), set()
        params = {"instType": "SWAP", "instId": "BTC-USDT-SWAP", "end": str(end), "limit": "100"}
        for _ in range(max_pages):
            data = self.get(path, params)
            for row in data:
                identity = row.get(key)
                if not isinstance(identity, str) or not identity or identity in seen:
                    raise DemoError("Missing/duplicate pagination identity; export incomplete")
                seen.add(identity)
                rows.append(row)
            if len(data) < 100:
                return {
                    "records": rows,
                    "pagination_exhausted": True,
                    "scope": "Only records retained by this demo endpoint; not guaranteed lifetime history",
                }
            cursor = data[-1][key]
            if cursor in cursors:
                raise DemoError("Pagination did not advance")
            cursors.add(cursor)
            params["after"] = cursor
            time.sleep(0.3)
        return {
            "records": rows,
            "pagination_exhausted": False,
            "scope": "Safety page limit reached; not a complete export",
        }


def private_json(path, value):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def export(client, output):
    resolved = output.resolve()
    if resolved.is_relative_to(REPO) or resolved == REPO:
        raise DemoError("Private account exports must stay outside the public repository")
    client.check()
    metadata = client.get(
        "/api/v5/public/instruments", {"instType": "SWAP", "instId": "BTC-USDT-SWAP"}, private=False
    )
    if (
        len(metadata) != 1
        or metadata[0].get("ctType") != "linear"
        or metadata[0].get("ctValCcy") != "BTC"
        or metadata[0].get("settleCcy") != "USDT"
    ):
        raise DemoError("Instrument contract metadata must be verified before export")
    end = int(client.get("/api/v5/public/time", private=False)[0]["ts"])
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    private_json(output / "instrument.json", metadata)
    counts = {}
    complete = True
    for name, path, key in [
        ("fills", "/api/v5/trade/fills-history", "billId"),
        ("orders", "/api/v5/trade/orders-history-archive", "ordId"),
    ]:
        result = client.pages(path, key, end=end)
        private_json(output / (name + ".json"), result)
        counts[name] = len(result["records"])
        complete = complete and result["pagination_exhausted"]
    private_json(
        output / "manifest.json",
        {
            "schema_version": 1,
            "api_origin": client.origin,
            "mode": "demo_readonly",
            "end_ms": end,
            "instrument": "BTC-USDT-SWAP",
            "files_sha256": {
                name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                for name in ("instrument.json", "fills.json", "orders.json")
            },
            "counts": counts,
            "pagination_exhausted": complete,
            "quantity_units": "Native contracts; do not treat fillSz as BTC without instrument conversion",
            "limits": "No original local order-submission/ACK timestamps, strategy config or market stream are reconstructed from history. Not an atomic account snapshot or proof of live fill quality.",
        },
    )
    audit = audit_export(output)
    private_json(output / "audit.json", audit)
    return {
        "private_export_written": True,
        "pagination_exhausted": complete,
        "counts": counts,
        "audit": audit,
    }


def audit_export(directory):
    """Check retained venue history, not replay parity or complete order lifecycles.

    Raw OKX fees are signed changes in feeCcy. No USD conversion is inferred.
    Orders can predate retained fills; summed retained fills need only be <= accFillSz.
    """
    from collections import Counter
    from decimal import Decimal, InvalidOperation

    directory = Path(directory)
    problems = Counter()

    def number(value, *, positive=False):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Numeric venue fields must be nonempty decimal strings")
        try:
            result = Decimal(value)
        except InvalidOperation:
            raise ValueError("Invalid decimal") from None
        if not result.is_finite() or (positive and result <= 0):
            raise ValueError("Invalid finite quantity")
        return result

    try:
        manifest = json.loads((directory / "manifest.json").read_text())
        if manifest.get("schema_version") != 1 or manifest.get("mode") != "demo_readonly":
            raise ValueError("Unsupported export schema")
        for name in ("instrument.json", "fills.json", "orders.json"):
            digest = hashlib.sha256((directory / name).read_bytes()).hexdigest()
            if manifest["files_sha256"].get(name) != digest:
                raise ValueError("Export hash mismatch")
        instrument = json.loads((directory / "instrument.json").read_text())
        fills_doc = json.loads((directory / "fills.json").read_text())
        orders_doc = json.loads((directory / "orders.json").read_text())
        fills, orders = fills_doc["records"], orders_doc["records"]
        if not isinstance(fills, list) or not isinstance(orders, list):
            raise ValueError("Expected lists")
        if (
            len(instrument) != 1
            or instrument[0].get("instId") != "BTC-USDT-SWAP"
            or instrument[0].get("ctType") != "linear"
            or instrument[0].get("ctValCcy") != "BTC"
            or instrument[0].get("settleCcy") != "USDT"
        ):
            raise ValueError("Unsupported instrument metadata")
        contract_btc = number(instrument[0]["ctVal"], positive=True)
        if manifest.get("counts") != {"fills": len(fills), "orders": len(orders)}:
            raise ValueError("Manifest count mismatch")
        cutoff = manifest["end_ms"]
        if type(cutoff) is not int or cutoff < 0:
            raise ValueError("Invalid export cutoff")
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError):
        raise DemoError("Invalid or tampered private export; details suppressed") from None

    index = {}
    for order in orders:
        try:
            oid = order["ordId"]
            if not isinstance(oid, str) or not oid or oid in index:
                raise ValueError("Duplicate/missing order identity")
            if (
                order["instId"] != "BTC-USDT-SWAP"
                or order["side"] not in ("buy", "sell")
                or order["state"]
                not in ("filled", "canceled", "live", "partially_filled", "mmp_canceled")
            ):
                raise ValueError("Order schema")
            size = number(order["sz"], positive=True)
            filled = number(order["accFillSz"])
            if filled < 0 or filled > size:
                raise ValueError("Order fill size")
            index[oid] = order
        except (ValueError, KeyError, TypeError):
            problems["invalid_or_duplicate_order"] += 1

    seen_bills, seen_trades = set(), set()
    totals, fees = {}, {}
    filled_btc = Decimal(0)
    for fill in fills:
        try:
            bill, trade = fill["billId"], fill["tradeId"]
            if not isinstance(bill, str) or not bill or not isinstance(trade, str) or not trade:
                raise ValueError("Missing execution identity")
            identity = (fill["instId"], fill["ordId"], trade)
            if bill in seen_bills or identity in seen_trades:
                raise ValueError("Duplicate execution")
            seen_bills.add(bill)
            seen_trades.add(identity)
            if fill["instId"] != "BTC-USDT-SWAP" or fill["side"] not in ("buy", "sell"):
                raise ValueError("Fill instrument or side")
            qty = number(fill["fillSz"], positive=True)
            number(fill["fillPx"], positive=True)
            fee = number(fill["fee"])
            currency = fill["feeCcy"]
            if not isinstance(currency, str) or not currency.strip():
                raise ValueError("Missing fee currency")
            ts = fill["ts"]
            if not isinstance(ts, str) or not ts.isdecimal() or not 0 <= int(ts) <= cutoff:
                raise ValueError("Invalid fill timestamp")
            order = index.get(fill["ordId"])
            if order is None:
                problems["fill_without_retained_order"] += 1
            elif order["side"] != fill["side"] or (
                fill.get("clOrdId") and order.get("clOrdId") != fill["clOrdId"]
            ):
                problems["order_fill_identity_mismatch"] += 1
            totals[fill["ordId"]] = totals.get(fill["ordId"], Decimal(0)) + qty
            fees[currency] = fees.get(currency, Decimal(0)) + fee
            filled_btc += qty * contract_btc
        except (ValueError, KeyError, TypeError):
            problems["invalid_or_duplicate_fill"] += 1
    for oid, total in totals.items():
        if oid in index and total > number(index[oid]["accFillSz"]):
            problems["fills_exceed_order_accumulated_size"] += 1
    complete = (
        manifest.get("pagination_exhausted") is True
        and fills_doc.get("pagination_exhausted") is True
        and orders_doc.get("pagination_exhausted") is True
    )
    if not complete:
        problems["incomplete_pagination"] += 1
    status = (
        "DISCREPANCIES"
        if problems
        else ("NO_EXECUTION_EVIDENCE" if not fills else "HISTORY_CHECKED")
    )
    return {
        "status": status,
        "fill_count": len(fills),
        "order_count": len(orders),
        "issues": dict(sorted(problems.items())),
        "retained_fill_volume_btc": str(filled_btc),
        "signed_fee_changes_by_currency": {k: str(v) for k, v in sorted(fees.items())},
        "replay_parity_verified": False,
        "latency_calibrated": False,
        "scope": "Retained demo history consistency only; missing local send/ACK clocks, strategy mapping and replay tape. No USD fee conversion or live fill-quality claim.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=sorted(ORIGINS), default="eea")
    parser.add_argument("--export-private", type=Path)
    parser.add_argument("--audit-private", type=Path)
    args = parser.parse_args()
    try:
        if args.audit_private:
            if args.export_private:
                raise DemoError("Choose export or offline audit, not both")
            result = audit_export(args.audit_private)
        else:
            client = Client(args.region)
            result = export(client, args.export_private) if args.export_private else client.check()
        print(json.dumps(result, allow_nan=False))
        if (
            result.get("status") == "DISCREPANCIES"
            or result.get("audit", {}).get("status") == "DISCREPANCIES"
        ):
            raise SystemExit(1)
    except DemoError as exc:
        print(str(exc))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
