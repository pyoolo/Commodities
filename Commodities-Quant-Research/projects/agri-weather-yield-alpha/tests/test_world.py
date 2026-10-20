import numpy as np
import pandas as pd
import pytest

from agriyield.forecast.scenarios import build_scenarios
from agriyield.synthetic.weather import WeatherArrays
from agriyield.synthetic.world import SyntheticWorld


def test_world_is_deterministic(cfg, world):
    again = SyntheticWorld.build(cfg, verbose=False, with_market=False)
    pd.testing.assert_frame_equal(world.tables["county_yields"], again.tables["county_yields"])


def test_yields_have_realistic_scale(world):
    y = world.tables["county_yields"]["yield_bu_ac"]
    assert 15 < y.median() < 70
    nt = world.tables["national_truth"]
    assert 0.01 < nt["true_dev"].std() < 0.15


def test_forecast_archive_is_reproducible_and_converges(world):
    a, b = world.forecast(2004, 100), world.forecast(2004, 100)
    np.testing.assert_array_equal(a.tmax, b.tmax)
    truth = world.season_weather(2004).tmax[:, 100:115]
    err = np.abs(a.tmax.mean(axis=0) - truth).mean(axis=0)    # by lead
    assert err[:3].mean() < err[-3:].mean()                      # skill decays with lead


def test_scenarios_refuse_unobserved_days():
    obs = WeatherArrays(*(np.full((2, 10), np.nan) for _ in range(3)))
    obs.tmax[:, :4] = obs.tmin[:, :4] = obs.prcp[:, :4] = 1.0
    fc = WeatherArrays(*(np.zeros((3, 2, 2)) for _ in range(3)))
    an = WeatherArrays(*(np.zeros((3, 2, 10)) for _ in range(3)))
    build_scenarios(obs, 4, fc, an)
    with pytest.raises(ValueError):
        build_scenarios(obs, 6, fc, an)                          # days 4-5 not observed yet


def test_null_market_expectation_is_a_martingale(world):
    """In the efficient market, daily changes of the expectation must not be predictable."""
    f = world.tables["futures_null"]
    f = f[(f["date"].dt.month >= 6) & (f["date"].dt.month <= 9) & ~f["is_report_day"]]
    d = f.groupby("year")["market_expectation_dev"].diff()
    lag = d.groupby(f["year"]).shift(1)
    rho = pd.concat([d, lag], axis=1).dropna().corr().iloc[0, 1]
    assert abs(rho) < 0.15
