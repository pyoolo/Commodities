import pandas as pd
import pytest

from clean_spark.spread import clean_spark_spread, rolling_zscore, trading_position


def test_clean_spark_formula():
    power = pd.Series([100.0])
    gas = pd.Series([30.0])
    carbon = pd.Series([70.0])

    css = clean_spark_spread(power, gas, carbon, efficiency=0.5, emissions_intensity=0.36)
    expected = 100.0 - 30.0 / 0.5 - 70.0 * 0.36
    assert css.iloc[0] == pytest.approx(expected)


def test_invalid_efficiency():
    s = pd.Series([1.0])
    with pytest.raises(ValueError):
        clean_spark_spread(s, s, s, efficiency=0.0, emissions_intensity=0.36)


def test_signal_direction():
    z = pd.Series([-2.0, -0.5, 0.0, 0.5, 2.0])
    pos = trading_position(z, entry_z=1.0)
    assert pos.tolist() == [1.0, 0.0, 0.0, 0.0, -1.0]


def test_rolling_zscore_has_warmup():
    s = pd.Series(range(10), dtype=float)
    z = rolling_zscore(s, lookback=5)
    assert z.iloc[:4].isna().all()
