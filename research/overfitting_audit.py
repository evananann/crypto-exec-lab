"""Future-input selection diagnostics; demo is invented and never reads study outcomes."""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np


def adjust_pvalues(pvalues, alpha=.05):
    if not 0 < alpha < 1 or not pvalues:
        raise ValueError('nonempty fixed family and alpha in (0,1) required')
    for value in pvalues:
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1):
            raise ValueError('valid marginal p-values or explicit unavailable required')
    # Unavailable hypotheses stay in family size and cannot be rejected.
    raw = np.array([1. if v is None else v for v in pvalues])
    order = np.argsort(raw, kind='stable')
    n = len(raw)
    ranks = np.arange(1, n+1)
    bh = np.minimum.accumulate((raw[order]*n/ranks)[::-1])[::-1]
    by = bh*sum(1/i for i in range(1, n+1))
    holm = np.maximum.accumulate(raw[order]*(n-ranks+1))
    results = {}
    for name, adjusted in (('BH', bh), ('BY', by), ('Holm', holm)):
        restored = np.empty(n)
        restored[order] = np.clip(adjusted, 0, 1)
        values = [None if pvalues[i] is None else float(v) for i, v in enumerate(restored)]
        results[name] = {'adjusted': values, 'reject': [v is not None and v <= alpha for v in values]}
    return {'family_size': n, 'unavailable': sum(v is None for v in pvalues), 'alpha': alpha,
            'methods': results,
            'assumptions': 'Holm FWER needs valid marginal p-values; BH FDR needs independence/PRDS; BY handles arbitrary dependence with valid marginal p-values. No method repairs invalid tick-level inference.'}


def deflated_sharpe(*, observed_sr, observations, skewness, pearson_kurtosis,
                    trials, trial_sr_std):
    values = (observed_sr, skewness, pearson_kurtosis, trial_sr_std)
    if (not all(math.isfinite(v) for v in values) or type(observations) is not int or observations < 3
            or type(trials) is not int or trials < 1 or trial_sr_std < 0 or pearson_kurtosis < 1):
        raise ValueError('finite per-period moments, counts and trial dispersion required')
    normal = NormalDist()
    gamma = .5772156649015329
    benchmark = 0. if trials == 1 else trial_sr_std*((1-gamma)*normal.inv_cdf(1-1/trials)
                   + gamma*normal.inv_cdf(1-1/(trials*math.e)))
    variance_factor = 1-skewness*observed_sr+(pearson_kurtosis-1)/4*observed_sr**2
    if variance_factor <= 0:
        raise ValueError('inconsistent moments produce nonpositive Sharpe variance')
    score = (observed_sr-benchmark)*math.sqrt(observations-1)/math.sqrt(variance_factor)
    return {'deflated_sharpe_probability': normal.cdf(score), 'inflated_null_sr': benchmark,
            'z': score, 'observations': observations, 'assumed_effective_trials': trials,
            'scope': 'Nonannualized per-period Sharpe; Pearson kurtosis (normal=3). Approximate probabilistic Sharpe with expected-max null. Effective trials/dispersion are assumptions; iid/stationarity and moment estimation matter. Not probability of profitability.'}


def sharpe_moments(returns):
    values = np.asarray(returns, dtype=float)
    if values.ndim != 1 or len(values) < 8 or not np.isfinite(values).all():
        raise ValueError('at least eight finite portfolio period returns required; no missing-to-zero conversion')
    centered = values-values.mean()
    variance = np.mean(centered**2)
    if variance <= 0:
        raise ValueError('zero return variance')
    return {'observed_sr': float(values.mean()/values.std(ddof=1)), 'observations': len(values),
            'skewness': float(np.mean(centered**3)/variance**1.5),
            'pearson_kurtosis': float(np.mean(centered**4)/variance**2)}


def pbo_cscv(returns, blocks=6):
    values = np.asarray(returns, dtype=float)
    if (values.ndim != 2 or values.shape[1] < 2 or not np.isfinite(values).all()
            or type(blocks) is not int or blocks < 4 or blocks > 12 or blocks % 2
            or len(values) % blocks or len(values)//blocks < 2):
        raise ValueError('finite complete return matrix, 2+ trials and even 4..12 equal contiguous blocks required')
    pieces = np.split(np.arange(len(values)), blocks)
    rows, logits = [], []
    for selected in itertools.combinations(range(blocks), blocks//2):
        train_index = np.concatenate([pieces[i] for i in selected])
        test_index = np.concatenate([pieces[i] for i in range(blocks) if i not in selected])
        train, test = values[train_index], values[test_index]
        train_sd, test_sd = train.std(axis=0, ddof=1), test.std(axis=0, ddof=1)
        if np.any(train_sd <= 0) or np.any(test_sd <= 0):
            rows.append({'training_blocks': list(selected), 'unavailable': 'zero variance in fixed candidate family'})
            continue
        train_sr, test_sr = train.mean(axis=0)/train_sd, test.mean(axis=0)/test_sd
        winners = np.flatnonzero(train_sr == train_sr.max())
        if len(winners) == values.shape[1]:
            rows.append({'training_blocks': list(selected), 'unavailable': 'no distinguishable training candidate'})
            continue
        winner = int(winners[0])  # fixed index tie rule, reported explicitly
        rank = float(np.sum(test_sr < test_sr[winner])+(np.sum(test_sr == test_sr[winner])+1)/2)
        relative_rank = rank/(values.shape[1]+1)
        logit = math.log(relative_rank/(1-relative_rank))
        logits.append(logit)
        rows.append({'training_blocks': list(selected), 'winner_index': winner,
                     'training_top_ties': len(winners), 'oos_midrank': rank, 'logit_rank': logit})
    complete = len(logits) == len(rows)
    return {'pbo': sum(v <= 0 for v in logits)/len(logits) if logits and complete else None,
            'planned_splits': len(rows), 'available_splits': len(logits), 'splits': rows,
            'scope': 'CSCV retrospective selection audit, not chronological forecast validation or a replacement holdout. Equal time blocks, complete fixed family, first-index train tie rule and OOS midranks; logit <=0 counts at/below median. Partial availability cannot yield a complete PBO.'}


def demo():
    rng = np.random.default_rng(0)
    returns = rng.normal(0, .01, (120, 8))
    trial_sr = returns.mean(axis=0)/returns.std(axis=0, ddof=1)
    chosen = int(np.argmax(trial_sr))
    return {'synthetic': True, 'market_tapes_read': 0, 'portfolio_evidence': False,
        'multiplicity': adjust_pvalues([.001, .012, .035, .08, .11, .24, .51, .91, None]),
        'dsr': deflated_sharpe(**sharpe_moments(returns[:, chosen]), trials=8,
                               trial_sr_std=float(trial_sr.std(ddof=1))),
        'pbo': pbo_cscv(returns),
        'scope': 'Invented p-values and iid toy portfolio returns; not study grid p-values, live returns or empirical performance.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(demo(), indent=2, allow_nan=False)+'\n')
