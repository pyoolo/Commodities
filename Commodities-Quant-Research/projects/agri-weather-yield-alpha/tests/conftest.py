import pytest

from agriyield.config import load_config
from agriyield.data.sources import SyntheticWeatherSource, store_from_world
from agriyield.synthetic.world import SyntheticWorld

TINY = {
    "world": {"n_states": 3, "counties_per_state": 4, "first_year": 1995, "last_year": 2006},
    "forecast": {"members": 4},
    "backtest": {"first_forecast_year": 2005, "first_test_year": 2005, "n_placebo": 20,
                 "usda_mimic_min_years": 1},
}


@pytest.fixture(scope="session")
def cfg():
    return load_config(overrides=TINY)


@pytest.fixture(scope="session")
def world(cfg):
    return SyntheticWorld.build(cfg, verbose=False)


@pytest.fixture(scope="session")
def store(world):
    return store_from_world(world)


@pytest.fixture(scope="session")
def wsrc(world):
    return SyntheticWeatherSource(world)
