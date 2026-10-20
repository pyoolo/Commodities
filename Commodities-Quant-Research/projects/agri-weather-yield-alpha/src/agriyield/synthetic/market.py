"""Synthetic CBOT November soybean futures.

The market holds an expectation E_t of the national yield deviation (log, vs
the USDA trend yield) and the price moves inversely with it:

    log P_t = log P0 - beta * E_t + noise_t

Efficient benchmark
-------------------
The *efficient* expectation is

    E*_t = D_t + s_hat_t

* D_t: what a perfect model (the true yield function) infers from observed
  weather plus the ensemble forecast (computed in world.py). Because the
  forecasts are martingales, D_t is (approximately) a martingale too.
* s_hat_t: Bayesian estimate of the part of yield weather cannot see (pests,
  disease, hail; variance s_var). Each USDA report y_r = lam_r * dev + eps_r
  gives a noisy reading of it:
      z_r = (y_r - lam_r * D_t) / lam_r,   noise var = f_var_t + eps_var_r / lam_r^2
  where f_var_t is the variance of weather still to come. Precision-weighted
  averaging of the z_r gives s_hat_t.

Inefficiencies (switched off in the null market)
------------------------------------------------
* adjustment_speed < 1: news is priced gradually (E moves part of the way to its
  target each day);
* usda_anchor > 0: the trade anchors on the USDA headline number (which shrinks
  early-season weather damage toward trend) instead of E*;
* in the last `pre_report_days` the market drifts to the analyst consensus
  (weight usda_anchor), which itself only partially anticipates the report.

With adjustment_speed = 1 and usda_anchor = 0 the price follows E* exactly and
no public-information strategy should earn money beyond noise and costs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def simulate_year(
    trading_days: pd.DatetimeIndex,
    efficient_dev: np.ndarray,
    f_var: np.ndarray,
    s_var: float,
    reports: pd.DataFrame,
    params: dict,
    noise: np.ndarray,
    report_noise: np.ndarray,
    p0: float,
) -> pd.DataFrame:
    """`reports`: date, usda_dev, consensus_dev, lam, eps_var (one row per report)."""
    eta = params["adjustment_speed"]
    anchor = params["usda_anchor"]
    beta = params["price_flexibility"]
    k_pre = params["pre_report_days"]

    reports = reports.reset_index(drop=True)
    day_pos = {d: i for i, d in enumerate(trading_days)}
    rep_idx = [day_pos[pd.Timestamp(d)] for d in reports["date"]]
    rep_at = {i: r for r, i in enumerate(rep_idx)}

    prec, num = 1.0 / s_var, 0.0           # posterior of the non-weather component
    last_usda = None
    E = efficient_dev[0]
    n = len(trading_days)
    exp_path, eff_path = np.empty(n), np.empty(n)
    is_report = np.zeros(n, bool)
    for i in range(n):
        if i in rep_at:
            r = reports.iloc[rep_at[i]]
            lam = r["lam"]
            z = (r["usda_dev"] - lam * efficient_dev[i]) / lam
            v = f_var[i] + r["eps_var"] / lam**2
            prec, num = prec + 1.0 / v, num + z / v
        eff = efficient_dev[i] + num / prec
        eff_path[i] = eff
        if i in rep_at:
            last_usda = reports.iloc[rep_at[i]]["usda_dev"]
            E = anchor * last_usda + (1 - anchor) * eff
            is_report[i] = True
        else:
            nxt = next((j for j in rep_idx if j > i), None)
            if nxt is not None and nxt - i <= k_pre:
                cons = reports.iloc[rep_at[nxt]]["consensus_dev"]
                target = anchor * cons + (1 - anchor) * eff
            elif last_usda is not None:
                target = anchor * last_usda + (1 - anchor) * eff
            else:
                target = eff
            E = E + eta * (target - E)
        exp_path[i] = E

    log_noise = np.cumsum(noise) + np.where(is_report, report_noise, 0.0).cumsum()
    log_price = np.log(p0) - beta * exp_path + log_noise
    return pd.DataFrame({
        "date": trading_days,
        "settle": np.exp(log_price),
        "market_expectation_dev": exp_path,
        "efficient_expectation_dev": eff_path,
        "weather_expectation_dev": efficient_dev,
        "is_report_day": is_report,
    })
