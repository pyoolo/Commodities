"""The backtest is only as honest as its data access. These tests try to cheat."""
import numpy as np
import pandas as pd
import pytest

from agriyield.data.store import LookAheadError, PITStore
from agriyield.features.build import training_frame


def test_store_hides_future_records_and_keeps_latest_vintage():
    df = pd.DataFrame({
        "year": [2020, 2020],
        "value": [50.0, 51.5],                                   # first estimate, then revision
        "knowledge_time": ["2021-02-20", "2021-09-30"],
    })
    s = PITStore()
    s.register("x", df, key=["year"])
    assert s.get("x", "2021-01-01").empty
    assert s.get("x", "2021-03-01")["value"].item() == 50.0
    assert s.get("x", "2022-01-01")["value"].item() == 51.5
    with pytest.raises(LookAheadError):
        s.require("x", "2020-12-31")


def test_county_yields_not_known_in_season(store):
    in_season = store.get("county_yields", "2004-08-15")
    assert in_season["year"].max() == 2003                      # 2004 yields arrive Feb 2005


def test_usda_report_not_visible_before_noon(store):
    rep = store.get("usda_reports", "2100-01-01")
    first = rep.sort_values("date").iloc[0]
    before = store.get("usda_reports", pd.Timestamp(first["date"]) + pd.Timedelta(hours=11))
    after = store.get("usda_reports", pd.Timestamp(first["date"]) + pd.Timedelta(hours=12))
    assert len(after) == len(before) + 1


def test_observed_weather_is_masked_after_latency(wsrc):
    as_of = pd.Timestamp("2004-07-15")
    obs = wsrc.observed(2004, as_of)
    end = wsrc.obs_end(as_of)
    assert np.isfinite(obs.tmax[:, :end]).all()
    assert np.isnan(obs.tmax[:, end:]).all()
    assert end == as_of.dayofyear - wsrc.doy0                   # 1-day latency


def test_reanalysis_archive_refuses_current_season(wsrc):
    with pytest.raises(LookAheadError):
        wsrc.archive([2004], pd.Timestamp("2004-08-01"))
    wsrc.archive([2003], pd.Timestamp("2004-08-01"))            # last season is final by then


def test_training_frame_only_contains_past_seasons(store, wsrc):
    tr = training_frame(store, wsrc, pd.Timestamp("2004-05-31"))
    assert tr["year"].max() == 2003
    assert not tr.isna().any().any()


def test_consensus_public_before_entry(cfg, store):
    cons = store.get("consensus", "2100-01-01")
    fut = store.get("futures", "2100-01-01").set_index("date")
    for _, c in cons.iterrows():
        entry = fut.index[fut.index < c["date"]].max() + pd.Timedelta(hours=14, minutes=20)
        assert c["knowledge_time"] <= entry
