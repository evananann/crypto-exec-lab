"""Causal BBO features and simple chronological model comparison.

Imported only after the release gate in empirical mode. No execution transport.
"""
from __future__ import annotations

import bisect
from collections import Counter
from datetime import datetime, timedelta, timezone
import math

import numpy as np

from cel.ingest.schema import Event
from cel.research.jumps import leader_jumps
from cel.research.mids import mids


class Tape:
    def __init__(self, events, protocol):
        self.protocol = protocol
        if any(a.local_ts > b.local_ts for a, b in zip(events, events[1:])):
            raise ValueError("receive timestamps regress; do not repair by sorting")
        self.books = {v: [e for e in events if e.kind == "bbo" and e.venue == v]
                      for v in (protocol["leader"], protocol["follower"])}
        self.times = {v: [e.local_ts for e in values] for v, values in self.books.items()}
        for values in self.books.values():
            for event in values:
                event.validate()
            if any(b.seq < a.seq and b.sequence_kind == a.sequence_kind == "sequence"
                   for a, b in zip(values, values[1:])):
                raise ValueError("hard sequence regression")

    def at(self, venue, timestamp, *, covered=False):
        values, times = self.books[venue], self.times[venue]
        index = bisect.bisect_right(times, timestamp) - 1
        if index < 0 or covered and timestamp > times[-1]:
            return None
        book = values[index]
        return book if timestamp - book.local_ts <= self.protocol["maximum_quote_age_ms"] else None


def mid(book):
    return (book.bid + book.ask) / 2


def features(tape, jump):
    p, ts = tape.protocol, jump.tick.local_ts
    direction = 1 if jump.move > 0 else -1
    follower = tape.at(p["follower"], ts)
    baseline = tape.at(p["follower"], jump.prev.local_ts)
    if follower is None or baseline is None:
        return None, "missing_or_stale_signal_book"
    if (follower.quantity_unit != "BTC" or follower.bid_sz is None or follower.ask_sz is None
            or follower.bid_sz + follower.ask_sz <= 0):
        return None, "unknown_displayed_size"
    sample = [tape.at(p["leader"], stamp)
              for stamp in range(ts - p["feature_lookback_ms"], ts + 1, p["volatility_step_ms"])]
    if any(book is None for book in sample):
        return None, "insufficient_feature_history"
    changes = [(mid(b) / mid(a) - 1) * 10000 for a, b in zip(sample, sample[1:])]
    volatility = math.sqrt(sum(x * x for x in changes) / len(changes))
    spread = (follower.ask - follower.bid) / mid(follower) * 10000
    jump_bps = abs(jump.move) / jump.prev.mid * 10000
    lo = bisect.bisect_left(tape.times[p["follower"]], ts - p["feature_lookback_ms"])
    hi = bisect.bisect_right(tape.times[p["follower"]], ts)
    history = tape.books[p["follower"]][max(0, lo - 1):hi]
    quote_changes = sum((a.bid, a.ask) != (b.bid, b.ask) for a, b in zip(history, history[1:]))
    return [jump_bps, jump_bps / max(spread, volatility, p["normalization_floor_bps"]),
            direction * (mid(follower) / mid(baseline) - 1) * 10000,
            direction * (jump.tick.mid / mid(follower) - 1) * 10000,
            spread, volatility, ts - follower.local_ts,
            direction * (follower.bid_sz - follower.ask_sz) / (follower.bid_sz + follower.ask_sz),
            quote_changes], None


def label(tape, jump, delay, horizon):
    p, ts = tape.protocol, jump.tick.local_ts
    entry = tape.at(p["follower"], ts + delay, covered=True)
    exit_book = tape.at(p["follower"], ts + horizon + p["exit_delay_ms"], covered=True)
    if entry is None or exit_book is None:
        return None, "uncovered_or_stale_entry_exit"
    buy = jump.move > 0
    sizes = (entry.ask_sz, exit_book.bid_sz) if buy else (entry.bid_sz, exit_book.ask_sz)
    if (entry.quantity_unit != "BTC" or exit_book.quantity_unit != "BTC"
            or any(x is None or x < p["quantity_btc"] for x in sizes)):
        return None, "insufficient_or_unknown_full_fill_size"
    first, last = (entry.ask, exit_book.bid) if buy else (entry.bid, exit_book.ask)
    gross = (last - first) * (1 if buy else -1)
    fees = first * p["entry_fee_bps"] / 10000 + last * p["exit_fee_bps"] / 10000
    return (gross - fees) / first * 10000, None


def extract(events, slot, protocol):
    tape = Tape(events, protocol)
    rows = []
    for index, jump in enumerate(leader_jumps(mids(events, protocol["leader"]), min_move=protocol["signal_usd"])):
        values, reason = features(tape, jump)
        targets, reasons = {}, {}
        for delay in protocol["entry_delays_ms"]:
            for horizon in protocol["horizons_ms"]:
                key = f"{delay}/{horizon}"
                targets[key], reasons[key] = label(tape, jump, delay, horizon)
        rows.append({"opportunity_id": slot["slot_id"] + f"-{index}", "slot_id": slot["slot_id"],
                     "day": slot["slot_id"][:10], "signal_ms": jump.tick.local_ts,
                     "feature_start_ms": min(jump.tick.local_ts - protocol["feature_lookback_ms"], jump.prev.local_ts) - protocol["maximum_quote_age_ms"],
                     "label_end_ms": jump.tick.local_ts + max(protocol["horizons_ms"]) + protocol["exit_delay_ms"],
                     "features": values, "feature_reason": reason,
                     "targets_bps": targets, "target_reasons": reasons})
    return rows


def fit(x, y, protocol):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if x.ndim != 2 or len(x) != len(y) or not len(y) or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("finite nonempty training matrix required")
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale < 1e-12] = 1
    design = np.column_stack([np.ones(len(x)), (x - mean) / scale])
    penalty = np.eye(design.shape[1])
    penalty[0, 0] = 0
    ridge = np.linalg.solve(design.T @ design + protocol["ridge_l2"] * penalty, design.T @ y)
    binary = (y > 0).astype(float)
    prior = (binary.sum() + .5) / (len(binary) + 1)
    logistic = np.zeros(design.shape[1])
    logistic[0] = math.log(prior / (1 - prior))
    for _ in range(protocol["logistic_iterations"]):
        probability = 1 / (1 + np.exp(-np.clip(design @ logistic, -35, 35)))
        gradient = design.T @ (probability - binary) / len(y)
        gradient += protocol["logistic_l2"] * (penalty @ logistic) / len(y)
        logistic -= protocol["logistic_learning_rate"] * gradient
    gains, losses = y[y > 0], y[y <= 0]
    return {"mean": mean.tolist(), "scale": scale.tolist(), "ridge": ridge.tolist(),
            "logistic": logistic.tolist(), "prior_profit_probability": float(prior),
            "constant_forecast_bps": float(y.mean()),
            "gain_bps": float(gains.mean()) if len(gains) else None,
            "loss_bps": float(losses.mean()) if len(losses) else None}


def predict(model, x):
    x = np.asarray(x, dtype=float)
    design = np.column_stack([np.ones(len(x)), (x - np.array(model["mean"])) / np.array(model["scale"])])
    ridge = design @ np.array(model["ridge"])
    probability = 1 / (1 + np.exp(-np.clip(design @ np.array(model["logistic"]), -35, 35)))
    ev = None if model["gain_bps"] is None or model["loss_bps"] is None else (
        probability * model["gain_bps"] + (1 - probability) * model["loss_bps"])
    return ridge, probability, ev


def purge(train, test, embargo_ms):
    if not test:
        return [], len(train)
    boundary = min(r["feature_start_ms"] for r in test)
    kept = [r for r in train if r["label_end_ms"] + embargo_ms < boundary]
    return kept, len(train) - len(kept)


def day_summary(values, protocol):
    if not values:
        return {"occupied_days": 0, "equal_day_mean_bps": None, "ci95_bps": None}
    array = np.array(list(values.values()), dtype=float)
    interval = None
    if len(array) >= 5:
        rng = np.random.default_rng(protocol["seed"])
        samples = rng.choice(array, size=(protocol["bootstrap_repetitions"], len(array)), replace=True).mean(axis=1)
        interval = [float(v) for v in np.quantile(samples, [.025, .975])]
    return {"occupied_days": len(array), "equal_day_mean_bps": float(array.mean()), "ci95_bps": interval}


def policy_metrics(rows, y, selected, planned_days, protocol):
    days = {}
    for row, value, take in zip(rows, y, selected):
        days.setdefault(row["day"], []).append(float(value) if take else 0.0)
    means = {day: sum(v) / len(v) for day, v in days.items()}
    chosen = [float(v) for v, take in zip(y, selected) if take]
    return {"state": "evaluated_hypothetical_opportunities", "eligible_opportunities": len(rows),
            "selected_opportunities": len(chosen), "selected_mean_bps": sum(chosen) / len(chosen) if chosen else None,
            "valid_abstentions": len(rows) - len(chosen),
            "unobserved_days": sorted(set(planned_days) - set(days)),
            "day_opportunity_value_bps": means,
            "day_summary": day_summary(means, protocol)}


def compare(rows, inventory, study, protocol):
    start = datetime.fromisoformat(study["start_date_utc"]).date()
    days = [str(start + timedelta(days=i)) for i in range(28)]
    expected = {s["slot_id"] for s in study["planned_slots"]}
    if len(inventory) != 56 or {s["slot_id"] for s in inventory} != expected:
        raise ValueError("all 56 original slots must remain in the inventory")
    if len({r["opportunity_id"] for r in rows}) != len(rows) or any(r["slot_id"] not in expected for r in rows):
        raise ValueError("ambiguous opportunity inventory")
    for row in rows:
        if row["day"] != row["slot_id"][:10] or row["day"] not in days:
            raise ValueError("opportunity day disagrees with planned slot")
        if row["features"] is not None and (len(row["features"]) != len(protocol["features"])
                or not all(math.isfinite(v) for v in row["features"])):
            raise ValueError("invalid feature vector")
        if any(value is not None and not math.isfinite(value) for value in row["targets_bps"].values()):
            raise ValueError("invalid economic label")
    primary = f"{protocol['primary_delay_ms']}/{protocol['primary_horizon_ms']}"
    valid = [r for r in rows if r["features"] is not None and r["targets_bps"][primary] is not None]
    folds = []
    definitions = [(f"development-{i+1}", f["train_days"], f["test_start"], f["test_end"])
                   for i, f in enumerate(protocol["development_folds"])]
    definitions.append(("untouched-holdout", 21, 21, 28))
    for name, train_end, test_start, test_end in definitions:
        training_days, testing_days = days[:train_end], days[test_start:test_end]
        train = [r for r in valid if r["day"] in training_days]
        test = [r for r in valid if r["day"] in testing_days]
        train, removed = purge(train, test, protocol["embargo_ms"])
        x = [r["features"] for r in test]
        y = np.array([r["targets_bps"][primary] for r in test])
        model = None
        policies, diagnostics = {}, {}
        if test:
            policies["jump_only"] = policy_metrics(test, y, np.ones(len(test), dtype=bool), testing_days, protocol)
            policies["normalized_jump_rule"] = policy_metrics(test, y,
                [r["features"][1] >= protocol["normalized_rule_threshold"] for r in test], testing_days, protocol)
        enough = (len(train) >= protocol["minimum_training_rows"]
                  and len({r["day"] for r in train}) >= protocol["minimum_training_days"])
        if enough and test:
            model = fit([r["features"] for r in train], [r["targets_bps"][primary] for r in train], protocol)
            forecast, probability, ev = predict(model, x)
            policies["ridge_net_value"] = policy_metrics(test, y, forecast > 0, testing_days, protocol)
            if ev is not None:
                policies["logistic_payoff_value"] = policy_metrics(test, y, ev > 0, testing_days, protocol)
            binary = (y > 0).astype(float)
            p = np.clip(probability, 1e-12, 1-1e-12)
            bins = []
            assignments = np.minimum((probability * 5).astype(int), 4)
            for index in range(5):
                mask = assignments == index
                bins.append({"lower": index / 5, "upper": (index + 1) / 5, "n": int(mask.sum()),
                    "mean_probability": float(probability[mask].mean()) if mask.any() else None,
                    "observed_profitable_fraction": float(binary[mask].mean()) if mask.any() else None})
            diagnostics = {"ridge_mse": float(np.mean((forecast-y)**2)),
                "constant_train_mean_mse": float(np.mean((model["constant_forecast_bps"]-y)**2)),
                "logistic_brier": float(np.mean((probability-binary)**2)),
                "train_prior_brier": float(np.mean((model["prior_profit_probability"]-binary)**2)),
                "log_loss": float(-np.mean(binary*np.log(p)+(1-binary)*np.log(1-p))),
                "calibration_bins": bins}
        for candidate in ("jump_only", "normalized_jump_rule", "ridge_net_value", "logistic_payoff_value"):
            policies.setdefault(candidate, {"state": "unavailable", "reason":
                "missing both payoff classes" if candidate == "logistic_payoff_value" and model else "insufficient training or test observations"})
        decay = {}
        for delay in protocol["entry_delays_ms"]:
            for horizon in protocol["horizons_ms"]:
                key = f"{delay}/{horizon}"
                available = [r for r in rows if r["day"] in testing_days and r["targets_bps"][key] is not None]
                decay[key] = policy_metrics(available, [r["targets_bps"][key] for r in available],
                    [True]*len(available), testing_days, protocol)
        folds.append({"fold": name, "training_days": training_days, "test_days": testing_days,
                      "training_opportunities": len(train), "purged_training_opportunities": removed,
                      "common_test_opportunities": len(test), "model": model,
                      "policies": policies, "prediction_diagnostics": diagnostics,
                      "jump_baseline_decay_all_available_labels": decay})
    return {"protocol_id": protocol["protocol_id"], "inventory": inventory, "opportunities": len(rows),
            "common_primary_eligible_opportunities": len(valid),
            "feature_unavailability": dict(Counter(r["feature_reason"] for r in rows if r["feature_reason"])),
            "primary_label_unavailability": dict(Counter(r["target_reasons"][primary] for r in rows if r["targets_bps"][primary] is None)),
            "opportunity_exclusions": [{"opportunity_id": r["opportunity_id"],
                "slot_id": r["slot_id"], "feature_reason": r["feature_reason"],
                "unavailable_targets": {k: v for k, v in r["target_reasons"].items() if v}}
                for r in rows if r["feature_reason"] or any(r["target_reasons"].values())],
            "folds": folds, "selected_winner": None,
            "interpretation": "Precommitted secondary comparison. Day intervals are descriptive and unadjusted across fixed comparisons. Overlapping hypothetical opportunities are not a portfolio or executable PnL; valid abstention differs from missing outcomes. No trade authorization."}


def synthetic_events(day, start_ms, *, seconds=30):
    """Periodic toy response, deliberately artificial profitable/loss regimes."""
    events = []
    amplitude, lag = (3, 90, 30, 120)[day % 4], (0, 100, 400, 200)[day % 4]
    for offset in range(0, seconds*1000+1, 20):
        for venue, delay in (("binance", 0), ("okx", lag)):
            price = 60000 + amplitude * ((max(0, offset-delay)//2000) % 2)
            events.append(Event(venue, "bbo", start_ms+offset, start_ms+offset, offset//20,
                                bid=price-.5, ask=price+.5, bid_sz=.01, ask_sz=.02))
    return events


def demo(protocol):
    from scripts.successor_study import slots

    study = {"start_date_utc": "2030-01-01", "end_date_utc": "2030-01-28",
             "development_end_date_utc": "2030-01-21", "slots_utc": {"am": "03:17", "pm": "15:17"}}
    study["planned_slots"] = slots(study)
    inventory, rows = [], []
    for slot in study["planned_slots"]:
        stamp = int(datetime.fromisoformat(slot["intended_start_utc"].replace("Z", "+00:00")).timestamp()*1000)
        day = (datetime.fromtimestamp(stamp/1000, timezone.utc).date() - datetime(2030, 1, 1).date()).days
        events = synthetic_events(day, stamp)
        rows += extract(events, slot, protocol)
        inventory.append(slot | {"eligible": True, "synthetic": True, "events": len(events), "seconds": 30})
    return compare(rows, inventory, study, protocol) | {"synthetic": True,
        "fixture": "56 toy 30-second tapes across 28 artificial dates; periodic response/lag and fixed size/spread. Not realistic distributions or market evidence."}
