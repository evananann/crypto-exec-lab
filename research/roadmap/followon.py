"""Synthetic matched-scale delay/horizon and activity-preserving placebo study.

No empirical loader, model fitting, winner selection, or live execution.
"""

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
import random

from research.decision_study.pipeline import (
    Config,
    Quote,
    Replay,
    decimal,
    evaluate,
    integer,
    digest,
)

DELAYS = (0, 25, 50, 100, 250, 500)
HORIZONS = (250, 1000, 5000)


@dataclass(frozen=True)
class FollowOnConfig(Config):
    def validate(self):
        # The independent experiment permits zero delay and holding horizons
        # shorter than entry latency; exit is signal+delay+holding horizon.
        integer(self.delay_ms)
        Config.validate(replace(self, delay_ms=1))


class MatchedReplay(Replay):
    def __init__(self, *args, overrides=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.overrides = overrides

    def action(self, policy, time):
        scores = []
        for venue in ("follower", "leader"):
            before = self.quote(venue, time - self.config.lookback_ms)
            now = self.quote(venue, time)
            if before is None or now is None:
                return None
            scores.append((now.mid / before.mid - 1) * 10000)
        if policy not in ("local", "cross"):
            raise ValueError("unknown policy")
        if policy == "cross" and self.overrides is not None:
            action = self.overrides[time]
            if type(action) is not int or action not in (-1, 0, 1):
                raise ValueError("invalid control action")
            return action
        score = scores[0] / 2 + (scores[1] / 2 if policy == "cross" else 0)
        threshold = decimal(self.config.threshold_bps)
        return 1 if score >= threshold else -1 if score <= -threshold else 0

    def audit(self, opportunities, rows):
        return super().audit(opportunities, rows) | {
            "policy_definition": "L/2 versus L/2+B/2; joint feature eligibility",
            "override_sha256": digest(sorted(self.overrides.items()))
            if self.overrides is not None
            else None,
        }


def fixtures(regime="informative"):
    if regime not in ("informative", "constant_leader"):
        raise ValueError("unknown constructed regime")
    leader, follower, opportunities = [], [], []
    for day in range(6):
        for i in range(8):
            time = 1730419201000 + day * 86400000 + i * 10000
            opportunities.append((f"{day}-{i}", time))
            sign = 1 if i % 2 == 0 else -1
            amplitude = Decimal(180 + day * 12 + i * 2)
            for offset in range(-100, 5501, 25):
                if regime == "constant_leader":
                    fm = Decimal(60000 if offset < 0 else 60108 if offset == 0 else 60100)
                    lm = Decimal(60000)
                else:
                    progress = max(Decimal(0), min(Decimal(1), Decimal(offset - 100) / 400))
                    decay = max(Decimal(0), Decimal(offset - 1500) / 4000)
                    fm = Decimal(60000) + sign * amplitude * progress * (1 - Decimal(".8") * decay)
                    lm = Decimal(60000 if offset < 0 else 60000 + sign * 300)
                follower.append(Quote(time + offset, str(fm - 1), str(fm + 1), "1", "1"))
                leader.append(Quote(time + offset, str(lm - 1), str(lm + 1), "1", "1"))
    return follower, leader, opportunities


def placebo_actions(opportunities, actions, kind, seed=7):
    groups = defaultdict(list)
    for identity, time in opportunities:
        groups[datetime.fromtimestamp(time / 1000, timezone.utc).date()].append(time)
    rng = random.Random(seed)
    result = {}
    for times in groups.values():
        values = [actions[t] for t in times]
        if any(v is None for v in values):
            raise ValueError("control requires complete source action eligibility")
        if kind == "cyclic_shift":
            transformed = values[-1:] + values[:-1]
        elif kind == "sign_inversion":
            transformed = [-v for v in values]
        elif kind == "within_day_shuffle":
            transformed = values[:]
            rng.shuffle(transformed)
        elif kind == "random_trigger":
            active = [v for v in values if v]
            rng.shuffle(active)
            positions = rng.sample(range(len(times)), len(active))
            transformed = [0] * len(times)
            for index, value in zip(positions, active):
                transformed[index] = value
        else:
            raise ValueError("unknown placebo")
        result.update(zip(times, transformed))
    return result


def summarize(replay, opportunities, *, repetitions=2000):
    ledger = replay.ledgers(opportunities)
    result = evaluate(replay, opportunities, ledger, repetitions=repetitions)
    result["synthetic"] = True
    result["action_contrasts"] = sum(
        ledger[i]["action"] != ledger[i + 1]["action"] for i in range(0, len(ledger), 2)
    )
    if not result["action_contrasts"]:
        result.update(
            inference_valid=False,
            ci95_usd=None,
            interpretation="No policy contrast; zero observed difference is not an information-value estimate.",
        )
    result["identification"] = (
        "Matched local coefficient; illustrative rules, not causal proof or a trained-model ablation"
    )
    return result


def experiment():
    surfaces = {}
    for regime in ("informative", "constant_leader"):
        follower, leader, opportunities = fixtures(regime)
        cells = []
        for delay in DELAYS:
            for horizon in HORIZONS:
                config = FollowOnConfig(delay_ms=delay, horizon_ms=horizon)
                result = summarize(MatchedReplay(follower, leader, config), opportunities)
                cells.append({"delay_ms": delay, "holding_horizon_ms": horizon, "result": result})
        surfaces[regime] = cells
    follower, leader, opportunities = fixtures()
    original = MatchedReplay(follower, leader, FollowOnConfig())
    actions = {time: original.action("cross", time) for _, time in opportunities}
    controls = []
    for kind in ("cyclic_shift", "sign_inversion", "within_day_shuffle", "random_trigger"):
        overrides = placebo_actions(opportunities, actions, kind)
        replay = MatchedReplay(follower, leader, FollowOnConfig(), overrides=overrides)
        controls.append(
            {
                "name": kind,
                "source_active": sum(v != 0 for v in actions.values()),
                "control_active": sum(v != 0 for v in overrides.values()),
                "scope": "Synthetic retrospective placebo; shuffling/rotation may use future actions. Not an executable policy.",
                "result": summarize(replay, opportunities),
            }
        )
    return {
        "schema_version": 1,
        "evidence_status": "SYNTHETIC",
        "market_tapes_read": 0,
        "search_size_cells": len(DELAYS) * len(HORIZONS) * 2,
        "fixed_control_count": 4,
        "winner_selected": False,
        "surfaces": surfaces,
        "negative_controls": controls,
        "clock": "receive-time backward asof; 500ms maximum age; 100ms feature lookback",
        "execution": "0.001BTC requested, recorded ask/bid,5bps each fill, depth-limited; independent opportunities",
        "inference": "Synthetic date-bootstrap intervals are plumbing checks, not empirical coverage or adjusted hypothesis tests. Controls are dependent; no p-values or best cell reported.",
        "decision": "No empirical edge or deployment conclusion. New empirical enrollment requires its own source freeze and future untouched evaluation.",
    }
