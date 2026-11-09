"""Deterministic null/helpful/misleading controls, explicitly not market evidence."""

from .pipeline import Quote, Replay, evaluate


def control(name):
    if name not in ("no_information", "helpful", "misleading", "less_bad", "shrinkage_only"):
        raise ValueError("unknown control")
    follower, leader, opportunities = [], [], []
    for day in range(6):
        for i in range(8):
            t = 1730419201000 + day * 86400000 + i * 10000
            opportunities.append((f"{day}-{i}", t))
            sign = 1 if i % 2 == 0 else -1
            future = 60000 + (
                200 * sign if name == "helpful" else -200 * sign if name == "misleading" else 0
            )
            signal = 60000 if name == "no_information" else 60000 + 300 * sign
            scenario = [
                (-100, 60000, 60000),
                (0, 60000, signal),
                (50, 60000, signal),
                (1050, future, signal),
            ]
            if name == "less_bad":
                signal = 60200 if i % 2 == 0 else 59800
                scenario = [
                    (-100, 60000, 60000),
                    (0, 60200, signal),
                    (50, 60210, signal),
                    (1050, 60200, signal),
                ]
            if name == "shrinkage_only":
                scenario = [
                    (-100, 60000, 60000),
                    (0, 60108, 60000),
                    (50, 60110, 60000),
                    (1050, 60100, 60000),
                ]
            for offset, fm, lm in scenario:
                follower.append(Quote(t + offset, str(fm - 1), str(fm + 1), "1", "1"))
                leader.append(Quote(t + offset, str(lm - 1), str(lm + 1), "1", "1"))
    replay = Replay(follower, leader)
    ledger = replay.ledgers(opportunities)
    result = evaluate(replay, opportunities, ledger)
    return replay, opportunities, ledger, result
