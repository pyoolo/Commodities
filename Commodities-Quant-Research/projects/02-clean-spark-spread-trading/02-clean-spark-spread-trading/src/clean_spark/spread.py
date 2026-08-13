from __future__ import annotations

import pandas as pd


def clean_spark_spread(
    power_price: pd.Series,
    gas_price: pd.Series,
    carbon_price: pd.Series,
    efficiency: float,
    emissions_intensity: float,
) -> pd.Series:
    """Return clean spark spread in EUR/MWh.

    Parameters
    ----------
    power_price:
        Power price in EUR/MWh.
    gas_price:
        Gas price in EUR/MWh_th.
    carbon_price:
        EUA price in EUR/tCO2.
    efficiency:
        Electrical efficiency as a decimal, e.g. 0.50.
    emissions_intensity:
        tCO2 per MWh_e produced.
    """
    if not 0 < efficiency <= 1:
        raise ValueError("efficiency must be in (0, 1]")
    if emissions_intensity < 0:
        raise ValueError("emissions_intensity must be non-negative")

    css = power_price - gas_price / efficiency - carbon_price * emissions_intensity
    css.name = "clean_spark_spread"
    return css


def rolling_zscore(series: pd.Series, lookback: int = 30) -> pd.Series:
    """Rolling z-score using only observations available up to time t."""
    if lookback < 2:
        raise ValueError("lookback must be at least 2")

    mean = series.rolling(lookback).mean()
    std = series.rolling(lookback).std(ddof=0)
    z = (series - mean) / std.replace(0, pd.NA)
    z.name = "zscore"
    return z.astype(float)


def trading_position(zscore: pd.Series, entry_z: float = 1.0) -> pd.Series:
    """Contrarian CSS position: long low z-scores, short high z-scores."""
    if entry_z <= 0:
        raise ValueError("entry_z must be positive")

    position = pd.Series(0.0, index=zscore.index, name="position")
    position.loc[zscore < -entry_z] = 1.0
    position.loc[zscore > entry_z] = -1.0
    return position
