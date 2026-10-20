"""Synthetic geography: states, counties, soils, acreage and spatial loadings.

Real-world counterparts
-----------------------
* County polygons / centroids   -> US Census TIGER/Line county shapefiles
* Soybean area per county       -> USDA NASS Cropland Data Layer (CDL) + NASS
                                   June Acreage report
* Available water capacity      -> USDA NRCS gSSURGO (AWS 0-150 cm)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

STATE_NAMES = ["IA", "IL", "IN", "MN", "NE", "OH", "SD", "MO"]


@dataclass
class Geography:
    county_id: np.ndarray      # (C,) int
    state_idx: np.ndarray      # (C,) int
    state_names: list[str]
    lat: np.ndarray            # (C,)
    lon: np.ndarray            # (C,)
    awc: np.ndarray            # (C,) available water capacity, mm
    base_acres: np.ndarray     # (C,) thousand acres
    loadings: np.ndarray       # (C, K) spatial loadings of weather factors

    @property
    def n_counties(self) -> int:
        return len(self.county_id)

    @property
    def n_states(self) -> int:
        return len(self.state_names)


def build_geography(cfg: dict, rng: np.random.Generator) -> Geography:
    w = cfg["world"]
    n_states, per_state = w["n_states"], w["counties_per_state"]
    lat_lo, lat_hi = w["lat_range"]
    lon_lo, lon_hi = w["lon_range"]

    # States are boxes on a 2-row grid covering the domain.
    n_cols = int(np.ceil(n_states / 2))
    dlat, dlon = (lat_hi - lat_lo) / 2, (lon_hi - lon_lo) / n_cols
    lat, lon, state = [], [], []
    for s in range(n_states):
        r, c = divmod(s, n_cols)
        lat.append(rng.uniform(lat_lo + r * dlat, lat_lo + (r + 1) * dlat, per_state))
        lon.append(rng.uniform(lon_lo + c * dlon, lon_lo + (c + 1) * dlon, per_state))
        state.append(np.full(per_state, s))
    lat, lon, state = np.concatenate(lat), np.concatenate(lon), np.concatenate(state)
    n = len(lat)

    # Weather factor loadings: Gaussian bumps + one domain-wide factor, so the
    # synthetic weather has realistic spatial coherence (droughts are regional,
    # some years are bad everywhere, e.g. 1988 / 2012).
    n_bumps = 6
    centres = np.column_stack([rng.uniform(lat_lo, lat_hi, n_bumps), rng.uniform(lon_lo, lon_hi, n_bumps)])
    d2 = (lat[:, None] - centres[None, :, 0]) ** 2 + ((lon[:, None] - centres[None, :, 1]) * 0.75) ** 2
    bumps = np.exp(-d2 / (2 * 2.5**2))
    loadings = np.column_stack([np.full(n, 0.45), bumps])
    loadings /= np.linalg.norm(loadings, axis=1, keepdims=True)

    # Soils: smooth spatial field + noise.
    soil_field = loadings @ rng.normal(0, 1, loadings.shape[1])
    awc = np.clip(165 + 30 * soil_field / soil_field.std() + rng.normal(0, 15, n), 90, 240)

    base_acres = rng.lognormal(mean=np.log(80), sigma=0.45, size=n)  # thousand acres
    return Geography(
        county_id=np.arange(n),
        state_idx=state,
        state_names=STATE_NAMES[:n_states],
        lat=lat,
        lon=lon,
        awc=awc,
        base_acres=base_acres,
        loadings=loadings,
    )
