"""Event-ordered financed cash/BTC portfolio, not an exchange perpetual margin model."""

from decimal import Decimal
from .pipeline import decimal


def liquidation_snapshot(cash, lots, quote, fee_bps):
    """Hypothetical full unwind at a fresh BBO; no fill is submitted or invented."""
    long_qty = sum((q for q in lots.values() if q > 0), Decimal(0))
    short_qty = -sum((q for q in lots.values() if q < 0), Decimal(0))
    if not long_qty and not short_qty:
        return {"status": "FLAT", "equity_usd": str(cash), "unwind_fee_usd": "0"}
    if quote is None:
        return {"status": "UNAVAILABLE_QUOTE", "equity_usd": None, "unwind_fee_usd": None}
    quote.validate()
    rate = decimal(fee_bps) / 10000
    if rate < 0:
        raise ValueError("nonnegative fee required")
    if long_qty > decimal(quote.bid_qty) or short_qty > decimal(quote.ask_qty):
        return {"status": "INSUFFICIENT_DEPTH", "equity_usd": None, "unwind_fee_usd": None}
    sells = long_qty * decimal(quote.bid)
    buys = short_qty * decimal(quote.ask)
    fee = (sells + buys) * rate
    return {
        "status": "HYPOTHETICAL_FULL_UNWIND",
        "equity_usd": str(cash + sells - buys - fee),
        "unwind_fee_usd": str(fee),
        "quote_time_ms": quote.time_ms,
    }


def simulate(replay, opportunities, ledger, policy, initial_cash="10000", max_gross_leverage="1.5"):
    replay.audit(opportunities, ledger)
    cash, cap = decimal(initial_cash), decimal(max_gross_leverage)
    if cash <= 0 or cap <= 0 or policy not in ("local", "cross"):
        raise ValueError("invalid portfolio configuration")
    initial = cash
    rows = [r for r in ledger if r["policy"] == policy and decimal(r["entry_qty_btc"]) > 0]
    events = []
    for r in rows:
        events.append((r["arrival_time_ms"], 1, r["opportunity_id"], "entry", r))
        if decimal(r["exit_qty_btc"]) > 0:
            events.append((r["exit_time_ms"], 0, r["opportunity_id"], "exit", r))
    events.sort(key=lambda e: e[:3])  # exits before entries at equal time
    lots, accepted, depth_used, records = {}, set(), {}, []
    fees_total = Decimal(0)
    peak_equity, max_dd = initial, Decimal(0)
    for time, _, identity, leg, row in events:
        mark_quote = replay.quote("follower", time)
        if mark_quote is None:
            return {"status": "UNAVAILABLE_MARK", "policy": policy, "events": records}
        mid = mark_quote.mid
        q = row[leg + "_quote"]
        side = row["action"] if leg == "entry" else -row["action"]
        price = decimal(q["ask" if side == 1 else "bid"])
        key = (q["time_ms"], "ask" if side == 1 else "bid")
        depth = decimal(q["ask_qty" if side == 1 else "bid_qty"])
        available = max(Decimal(0), depth - depth_used.get(key, Decimal(0)))
        requested = decimal(row[leg + "_qty_btc"])
        before_qty = sum(lots.values(), Decimal(0))
        before_equity = cash + before_qty * mid
        reason = None
        qty = min(requested, available)
        if leg == "exit":
            if identity not in accepted:
                continue
            qty = min(qty, abs(lots.get(identity, Decimal(0))))
        fee = qty * price * decimal(replay.config.fee_bps) / 10000
        if leg == "entry":
            candidate_cash = cash - side * qty * price - fee
            candidate_lots = lots | {identity: side * qty}
            candidate_equity = candidate_cash + sum(candidate_lots.values(), Decimal(0)) * mid
            gross = sum(abs(v) for v in candidate_lots.values()) * mid
            if candidate_equity <= 0 or gross > cap * candidate_equity:
                reason, qty, fee = "exposure_limit", Decimal(0), Decimal(0)
            elif qty > 0:
                accepted.add(identity)
                lots[identity] = side * qty
        if qty == 0:
            reason = reason or "depth_exhausted"
        elif leg == "exit":
            lots[identity] += side * qty
        cash -= side * qty * price + fee
        fees_total += fee
        depth_used[key] = depth_used.get(key, Decimal(0)) + qty
        net_qty = sum(lots.values(), Decimal(0))
        equity = cash + net_qty * mid
        gross = sum(abs(v) for v in lots.values()) * mid
        peak_equity = max(peak_equity, before_equity, equity)
        max_dd = max(max_dd, (peak_equity - equity) / peak_equity)
        records.append(
            {
                "time_ms": time,
                "opportunity_id": identity,
                "leg": leg,
                "quantity_btc": str(qty),
                "price_usd": str(price),
                "fee_usd": str(fee),
                "cash_usd": str(cash),
                "net_btc": str(net_qty),
                "gross_btc": str(sum(abs(v) for v in lots.values())),
                "mark_usd": str(mid),
                "equity_usd": str(equity),
                "gross_notional_usd": str(gross),
                "leverage": str(gross / equity) if equity > 0 else None,
                "rejection_reason": reason,
            }
        )
    remaining = {k: str(v) for k, v in lots.items() if v}
    # Depth already consumed by the last event is not available again for unwind.
    terminal_quote = replay.quote("follower", records[-1]["time_ms"]) if records else None
    if terminal_quote is not None:
        from dataclasses import replace

        terminal_quote = replace(
            terminal_quote,
            bid_qty=str(
                max(
                    Decimal(0),
                    decimal(terminal_quote.bid_qty)
                    - depth_used.get((terminal_quote.time_ms, "bid"), Decimal(0)),
                )
            ),
            ask_qty=str(
                max(
                    Decimal(0),
                    decimal(terminal_quote.ask_qty)
                    - depth_used.get((terminal_quote.time_ms, "ask"), Decimal(0)),
                )
            ),
        )
    return {
        "terminal_liquidation": liquidation_snapshot(
            cash, lots, terminal_quote, replay.config.fee_bps
        ),
        "status": "OPEN_INVENTORY" if remaining else "FLAT",
        "policy": policy,
        "initial_cash_usd": str(initial),
        "final_cash_usd": str(cash),
        "final_equity_usd": records[-1]["equity_usd"] if records else str(initial),
        "fees_usd": str(fees_total),
        "max_event_drawdown_fraction": str(max_dd),
        "remaining_lots_btc": remaining,
        "max_gross_leverage_at_entry": str(cap),
        "events": records,
        "limitations": "Financed cash/BTC accounting; no perpetual margin, funding, borrow rate, liquidation, or continuous intratick risk. Cap enforced on new fills only; exit precedes entry on ties. Quote-side liquidity shared until next quote update.",
    }
