"""Clean spark spread research toolkit."""

from .spread import clean_spark_spread, rolling_zscore, trading_position
from .backtest import run_backtest
from .analytics import performance_summary

__all__ = [
    "clean_spark_spread",
    "rolling_zscore",
    "trading_position",
    "run_backtest",
    "performance_summary",
]
