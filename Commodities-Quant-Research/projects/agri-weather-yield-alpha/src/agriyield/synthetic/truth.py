"""The HIDDEN data-generating process for soybean yield.

Nothing in models/ or signals/ imports this module. It exists only to generate
the synthetic world. The functional form deliberately contains things a
textbook linear panel model misses:

* heat damage is amplified by drought (KDD x soil-water-stress interaction),
* water stress matters only in the seed-fill window,
* late planting and late maturity (frost risk) are penalised,
* threshold effects in VPD and waterlogging.

Coefficients are chosen to produce realistic magnitudes: county yield
deviations of ~8-12%, national deviations of ~4-6% (2012-like years ~ -15%).
"""
from __future__ import annotations

import numpy as np

TREND_PER_YEAR = 0.0135          # ~1.35%/yr genetic + agronomic gain
BASE_YIELD_1995 = 36.0           # bu/ac
STATE_SHOCK_SD = 0.020           # unobservable (pests, disease, hail) state-year
COUNTY_SHOCK_SD = 0.045          # unobservable county-year


def weather_log_effect(f: dict[str, np.ndarray]) -> np.ndarray:
    """Log-yield effect of the season's weather (before centring)."""
    return (
        0.0025 * (f["rep_days"] - 45.0)
        - 0.0045 * f["kdd_rep"] * (1.0 + 1.5 * f["dry_rep"])
        - 0.0010 * f["kdd_veg"]
        - 0.22 * f["wstress_fill"] ** 1.5
        - 0.0035 * np.maximum(0.0, f["plant_doy"] - 135.0)
        - 0.05 * np.maximum(0.0, f["vpd_rep"] - 2.0)
        - 0.0040 * np.maximum(0.0, f["r6_doy"] - 260.0)
        - 0.0003 * np.maximum(0.0, f["prcp_veg"] - 350.0)
    )


def condition_index(daily: dict[str, np.ndarray], plant_idx: np.ndarray, plant_doy: np.ndarray) -> np.ndarray:
    """Crop-condition 'health' index through each day (what field observers see).

    It reflects stress accumulated *so far* only; observers cannot see future
    weather, which is why early-season ratings carry little information.
    """
    D = daily["kdd"].shape[-1]
    d = np.arange(D)
    cum_kdd = np.cumsum(daily["kdd"] * daily["rep_mask"], axis=-1)
    started = d >= plant_idx[..., None]
    cum_ws = np.cumsum(daily["ws"] * started, axis=-1)
    n = np.maximum(np.cumsum(started, axis=-1), 1)
    ws_mean = cum_ws / n
    late = 0.0035 * np.maximum(0.0, plant_doy - 135.0)[..., None]
    return -(0.004 * cum_kdd * (1 + 1.5 * ws_mean) + 0.6 * ws_mean + late)
