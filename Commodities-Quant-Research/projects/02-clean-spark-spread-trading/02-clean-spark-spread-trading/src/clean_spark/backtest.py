from __future__ import annotations

import pandas as pd


def run_backtest(
    spread: pd.Series,
    position: pd.Series,
    transaction_cost_per_unit: float = 0.0,
) -> pd.DataFrame:
    """Backtest a one-period-lagged position on changes in the CSS.

    The signal observed at t is traded for the change from t to t+1.
    This lag avoids using the same-period price change to create P&L.
    """
    if transaction_cost_per_unit < 0:
        raise ValueError("transaction_cost_per_unit must be non-negative")

    frame = pd.concat([spread.rename("spread"), position.rename("position")], axis=1).dropna()
    frame["spread_change"] = frame["spread"].diff()
    frame["held_position"] = frame["position"].shift(1).fillna(0.0)
    frame["turnover"] = frame["position"].diff().abs().fillna(frame["position"].abs())
    frame["gross_pnl"] = frame["held_position"] * frame["spread_change"].fillna(0.0)
    frame["cost"] = frame["turnover"] * transaction_cost_per_unit
    frame["net_pnl"] = frame["gross_pnl"] - frame["cost"]
    frame["cumulative_pnl"] = frame["net_pnl"].cumsum()
    return frame
