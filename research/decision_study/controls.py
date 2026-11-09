"""Deterministic null/helpful/misleading controls, explicitly not market evidence."""

from .pipeline import Quote, Replay, evaluate


def control(name):
    if name not in ("no_information", "helpful", "misleading"):
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
            for offset, fm, lm in [
                (-100, 60000, 60000),
                (0, 60000, signal),
                (50, 60000, signal),
                (1050, future, signal),
            ]:
                follower.append(Quote(t + offset, str(fm - 1), str(fm + 1), "1", "1"))
                leader.append(Quote(t + offset, str(lm - 1), str(lm + 1), "1", "1"))
    replay = Replay(follower, leader)
    ledger = replay.ledgers(opportunities)
    result = evaluate(replay, opportunities, ledger)
    return replay, opportunities, ledger, result
