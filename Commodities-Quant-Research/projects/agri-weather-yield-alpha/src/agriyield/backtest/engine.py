"""Backtest bookkeeping, metrics and placebo tests.

P&L is in log-return units per unit of notional (1.0 = 100% of the
contract value). Sharpe ratios are annualised on a full calendar of business
days, with zero P&L when a sleeve is flat: off-season capital is counted as
idle, which is the honest way to report a seasonal strategy.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def calendar(first_year: int, last_year: int) -> pd.DatetimeIndex:
    return pd.bdate_range(f"{first_year}-01-01", f"{last_year}-12-31")


def to_daily(pnl: pd.DataFrame, date_col: str, cal: pd.DatetimeIndex) -> pd.Series:
    s = pnl.groupby(date_col)["pnl"].sum()
    return s.reindex(cal, fill_value=0.0)


def sharpe(daily: pd.Series) -> float:
    sd = daily.std()
    return float(daily.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0


def max_drawdown(daily: pd.Series) -> float:
    cum = daily.cumsum()
    return float((cum - cum.cummax()).min())


def summary(daily: pd.Series, trades: pd.DataFrame | None = None) -> dict:
    yearly = daily.groupby(daily.index.year).sum()
    out = {
        "sharpe": round(sharpe(daily), 2),
        "ann_return_pct": round(float(daily.mean() * 252 * 100), 2),
        "ann_vol_pct": round(float(daily.std() * np.sqrt(252) * 100), 2),
        "max_drawdown_pct": round(max_drawdown(daily) * 100, 2),
        "positive_years": f"{int((yearly > 0).sum())}/{len(yearly)}",
        "t_stat_yearly": round(float(yearly.mean() / (yearly.std() / np.sqrt(len(yearly)))), 2)
        if yearly.std() > 0 else 0.0,
    }
    if trades is not None and len(trades):
        active = trades[trades["position"] != 0]
        out["n_trades"] = int(len(active))
        out["hit_rate"] = round(float((active["pnl"] > 0).mean()), 3)
    return out


def placebo_surprise(trades: pd.DataFrame, cal: pd.DatetimeIndex, cost_bps: float,
                     n: int, rng: np.random.Generator) -> np.ndarray:
    """Sharpe distribution with random trade directions (same sizes, same dates)."""
    out = np.empty(n)
    for i in range(n):
        sign = rng.choice([-1.0, 1.0], len(trades))
        p = trades.assign(pnl=sign * trades["position"] * trades["ret"]
                          - 2 * np.abs(trades["position"]) * cost_bps / 1e4)
        out[i] = sharpe(to_daily(p, "date", cal))
    return out


def placebo_momentum(pos: pd.DataFrame, cal: pd.DatetimeIndex, cost_bps: float,
                     n: int, rng: np.random.Generator) -> np.ndarray:
    """Sharpe distribution after circularly shifting positions against returns.

    Keeps the signal's own autocorrelation and the return series intact; only
    the alignment between the two is destroyed.
    """
    out = np.empty(n)
    m = len(pos)
    for i in range(n):
        shift = int(rng.integers(20, m - 20))
        p = pos.copy()
        p["position"] = np.roll(pos["position"].to_numpy(), shift)
        turnover = p.groupby("year")["position"].diff().abs().fillna(p["position"].abs())
        p["pnl"] = p["position"] * p["ret"] - turnover * cost_bps / 1e4
        out[i] = sharpe(to_daily(p, "date", cal))
    return out


def shift_to_next_day(pos: pd.DataFrame, cal: pd.DatetimeIndex) -> pd.DataFrame:
    """Book momentum P&L on the day the return is earned (t+1)."""
    nxt = pd.Series(cal[1:], index=cal[:-1])
    p = pos.copy()
    p["pnl_date"] = p["date"].map(nxt)
    return p
