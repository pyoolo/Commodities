"""Walk-forward + signals + backtest on the tiny world."""
import numpy as np
import pandas as pd
import pytest

from agriyield.backtest import engine
from agriyield.signals import strategies
from agriyield.validation.walkforward import run_walkforward


@pytest.fixture(scope="module")
def wf(cfg, store, wsrc):
    return run_walkforward(cfg, store, wsrc, verbose=False)


def test_walkforward_outputs(wf):
    ins = wf["inseason"]
    assert set(ins["year"]) == {2005, 2006}
    assert set(ins["model"]) == {"trend", "conditions", "panel", "gbm", "blend"}
    assert (ins["p10"] <= ins["p90"] + 1e-9).all()
    assert ins["mean"].between(10, 100).all()


def test_weather_models_beat_trend_at_end_of_season(wf, store):
    eos = wf["county_eos"].merge(store.get("county_yields", "2100-01-01"), on=["year", "county_id"])
    err = {m: np.sqrt(((eos[m] - np.log(eos["yield_bu_ac"])) ** 2).mean()) for m in ["trend", "blend"]}
    assert err["blend"] < err["trend"]


def test_surprise_positions_bounded_and_timed(cfg, store, wf):
    df = strategies.surprise_table(cfg, store, wf["inseason"], "blend")
    assert df["position"].between(-1, 1).all()
    assert (df["entry_date"] < df["date"]).all()


def test_momentum_flat_before_reports(cfg, store, wf):
    pos = strategies.momentum_positions(cfg, store, wf["inseason"], "blend")
    rep = set(pd.to_datetime(store.get("usda_reports", "2100-01-01")["date"]))
    fut = store.get("futures", "2100-01-01").set_index("date")
    nxt = pd.Series(fut.index[1:], index=fut.index[:-1])
    pre = pos[pos["date"].map(nxt).isin(rep)]
    assert (pre["position"] == 0).all()


def test_backtest_metrics_on_known_series():
    cal = engine.calendar(2020, 2020)
    perfect = pd.DataFrame({"date": cal, "pnl": np.abs(np.random.default_rng(0).normal(0, 0.01, len(cal)))})
    assert engine.sharpe(engine.to_daily(perfect, "date", cal)) > 5
    flat = pd.DataFrame({"date": cal, "pnl": 0.0})
    assert engine.sharpe(engine.to_daily(flat, "date", cal)) == 0.0
