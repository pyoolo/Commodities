import numpy as np
import pytest

from agriyield import agronomy as ag


def test_degree_days_closed_form_cases():
    # entirely below / entirely above / symmetric crossing
    assert ag.degree_days_above(20.0, 29.0, 30.0) == 0.0
    assert ag.degree_days_above(31.0, 35.0, 30.0) == pytest.approx(3.0)
    # tmin=25, tmax=35, threshold at the mean: area = amplitude / pi
    assert ag.degree_days_above(25.0, 35.0, 30.0) == pytest.approx(5.0 / np.pi)


def test_dense_and_sparse_degree_days_agree():
    rng = np.random.default_rng(0)
    tmin = rng.uniform(5, 28, 5000)
    tmax = tmin + rng.uniform(0, 18, 5000)
    for thr in (10.0, 30.0):
        dense = ag._dd_dense(0.5 * (tmax + tmin), 0.5 * (tmax - tmin), thr)
        np.testing.assert_allclose(dense, ag.degree_days_above(tmin, tmax, thr), atol=1e-9)


def test_gdd_is_capped():
    # above the cap, extra heat adds no beneficial degree days
    assert ag.growing_degree_days(25, 45) == pytest.approx(ag.growing_degree_days(25, 45, cap=30))
    assert ag.growing_degree_days(31, 40) == pytest.approx(20.0)


def test_water_balance_stays_in_bounds():
    rng = np.random.default_rng(1)
    prcp = rng.gamma(0.7, 12, (3, 100))
    et0 = rng.uniform(2, 7, (3, 100))
    kc = np.ones((3, 100))
    awc = np.array([100.0, 150.0, 200.0])
    sm = ag.water_balance(prcp, et0, kc, awc, awc * 0.8)
    assert (sm >= 0).all() and (sm <= awc[:, None] + 1e-9).all()


def test_stages_are_ordered_and_hot_weather_is_faster():
    d = 214
    cool = ag.stage_indices(ag.growing_degree_days(np.full(d, 12.0), np.full(d, 24.0)), np.array(30))
    hot = ag.stage_indices(ag.growing_degree_days(np.full(d, 18.0), np.full(d, 30.0)), np.array(30))
    order = ["VE", "R1", "R3", "R5", "R6", "R7"]
    assert all(cool[a] <= cool[b] for a, b in zip(order, order[1:]))
    assert hot["R6"] < cool["R6"]


def test_heat_and_drought_raise_damage_features():
    d, lat, awc = 214, np.array([41.0]), np.array([160.0])
    base = dict(lat=lat, awc=awc, sm0=np.array([120.0]), plant_idx=np.array([40]), doy0=91)
    tmin = np.full((1, d), 17.0)
    mild = ag.season_features(tmin, np.full((1, d), 28.0), np.full((1, d), 4.0), **base).features
    hot_dry = ag.season_features(tmin + 3, np.full((1, d), 34.0), np.full((1, d), 0.5), **base).features
    assert hot_dry["kdd_rep"][0] > mild["kdd_rep"][0]
    assert hot_dry["wstress_fill"][0] > mild["wstress_fill"][0]
