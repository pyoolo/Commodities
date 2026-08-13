from __future__ import annotations

import math

import pandas as pd


def performance_summary(backtest: pd.DataFrame, annualization_factor: int = 252) -> dict[str, float]:
    pnl = backtest["net_pnl"].dropna()
    cumulative = pnl.cumsum()
    drawdown = cumulative - cumulative.cummax()

    std = pnl.std(ddof=0)
    sharpe = 0.0 if std == 0 else math.sqrt(annualization_factor) * pnl.mean() / std
    active = backtest.loc[backtest["held_position"] != 0, "net_pnl"]
    hit_rate = float((active > 0).mean()) if len(active) else 0.0

    return {
        "total_pnl": float(pnl.sum()),
        "annualized_sharpe": float(sharpe),
        "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
        "hit_rate": hit_rate,
        "turnover": float(backtest["turnover"].sum()),
    }
