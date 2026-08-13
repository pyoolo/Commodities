import pandas as pd

from clean_spark.backtest import run_backtest


def test_backtest_uses_lagged_position():
    spread = pd.Series([10.0, 11.0, 13.0])
    position = pd.Series([1.0, 1.0, 1.0])
    bt = run_backtest(spread, position, transaction_cost_per_unit=0.0)

    assert bt["held_position"].tolist() == [0.0, 1.0, 1.0]
    assert bt["gross_pnl"].tolist() == [0.0, 1.0, 2.0]


def test_transaction_costs_reduce_pnl():
    spread = pd.Series([10.0, 11.0, 12.0])
    position = pd.Series([0.0, 1.0, 0.0])
    gross = run_backtest(spread, position, transaction_cost_per_unit=0.0)
    net = run_backtest(spread, position, transaction_cost_per_unit=0.5)

    assert net["net_pnl"].sum() < gross["net_pnl"].sum()
