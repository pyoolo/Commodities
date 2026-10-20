"""Data-source interfaces, the synthetic implementation, and real-data adapters.

The pipeline only talks to the two interfaces below. Swapping the synthetic
world for real data means implementing the adapters at the bottom of this
file; nothing in features/, models/, signals/ or backtest/ changes.

    WeatherSource  observed weather, ensemble forecasts, reanalysis archive
    TableSource    any tabular dataset with a knowledge_time column
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..synthetic.weather import WeatherArrays
from .store import LookAheadError, PITStore


# =============================================================================
# Interfaces
# =============================================================================
class WeatherSource(ABC):
    """Gridded weather already aggregated to counties with crop-mask weights."""

    members: int
    doy0: int
    n_days: int

    @abstractmethod
    def obs_end(self, as_of: pd.Timestamp) -> int:
        """First season-day index that is NOT yet observed at `as_of`."""

    @abstractmethod
    def observed(self, year: int, as_of: pd.Timestamp) -> WeatherArrays:
        """(C, D) arrays; days >= obs_end(as_of) are NaN."""

    @abstractmethod
    def forecast(self, year: int, as_of: pd.Timestamp) -> WeatherArrays:
        """(M, C, h) ensemble issued at `as_of`, starting at obs_end(as_of)."""

    @abstractmethod
    def archive(self, years: list[int], as_of: pd.Timestamp) -> WeatherArrays:
        """(Y, C, D) final reanalysis for completed seasons."""


class TableSource(ABC):
    name: str
    key: list[str]

    @abstractmethod
    def fetch(self) -> pd.DataFrame:
        """Full history with a `knowledge_time` column (one row per vintage)."""


# =============================================================================
# Synthetic implementation
# =============================================================================
REANALYSIS_LAG = pd.Timedelta(days=92)   # ERA5 final ~ 2-3 months after real time


@dataclass
class SyntheticWeatherSource(WeatherSource):
    world: "object"   # SyntheticWorld; typed loosely to avoid a circular import

    def __post_init__(self):
        self.members = self.world.cfg["forecast"]["members"]
        self.doy0 = self.world.doy0
        self.n_days = self.world.n_days

    def _idx(self, as_of) -> int:
        return self.world.as_of_index(pd.Timestamp(as_of))

    def obs_end(self, as_of) -> int:
        return self.world.obs_end(self._idx(as_of))

    def observed(self, year: int, as_of) -> WeatherArrays:
        as_of = pd.Timestamp(as_of)
        if as_of.year < year:
            end = 0
        elif as_of.year > year:
            end = self.n_days
        else:
            end = self.obs_end(as_of)
        w = self.world.season_weather(year)
        out = {}
        for var in ("tmax", "tmin", "prcp"):
            a = getattr(w, var).astype(float).copy()
            a[:, end:] = np.nan
            out[var] = a
        return WeatherArrays(**out)

    def forecast(self, year: int, as_of) -> WeatherArrays:
        as_of = pd.Timestamp(as_of)
        if as_of.year != year:
            raise ValueError("forecasts are only issued in-season")
        return self.world.forecast(year, self.obs_end(as_of))

    def archive(self, years, as_of) -> WeatherArrays:
        as_of = pd.Timestamp(as_of)
        for y in years:
            season_end = pd.Timestamp(f"{y}-01-01") + pd.Timedelta(days=self.doy0 + self.n_days - 1)
            if season_end + REANALYSIS_LAG > as_of:
                raise LookAheadError(f"reanalysis for {y} not final as of {as_of.date()}")
        idx = [self.world.yidx(y) for y in years]
        w = self.world.weather
        return WeatherArrays(w.tmax[idx], w.tmin[idx], w.prcp[idx])


def store_from_world(world, market: str = "main") -> PITStore:
    """Register every synthetic table in a PIT store.

    market: "main" (inefficient market) or "null" (efficient market control).
    """
    sfx = "" if market == "main" else "_null"
    t = world.tables
    store = PITStore()
    store.register("county_yields", t["county_yields"], key=["year", "county_id"])
    store.register("county_acres", t["county_acres"], key=["year", "county_id"])
    store.register("planting", t["planting"], key=["year", "county_id"])
    store.register("soil_moisture_start", t["soil_moisture_start"], key=["year", "county_id"])
    store.register("conditions", t["conditions"], key=["week_date", "state"])
    store.register("wasde_trend", t["wasde_trend"], key=["year"])
    store.register("usda_reports", t[f"usda_reports{sfx}"], key=["year", "report"])
    store.register("consensus", t[f"consensus{sfx}"], key=["year", "report"])
    store.register("futures", t[f"futures{sfx}"], key=["date"])
    static = t["county_static"].assign(knowledge_time=pd.Timestamp("1900-01-01"))
    store.register("county_static", static, key=["county_id"])
    return store


# =============================================================================
# Real-data adapters (to implement against production data)
# =============================================================================
class _NotWired(TableSource):
    """Base for adapters that document the real endpoint but are not wired."""

    url: str = ""
    notes: str = ""

    def fetch(self) -> pd.DataFrame:  # pragma: no cover - documentation stubs
        raise NotImplementedError(f"{type(self).__name__}: implement against {self.url}\n{self.notes}")


class NassCountyYields(_NotWired):
    name, key = "county_yields", ["year", "county_id"]
    url = "https://quickstats.nass.usda.gov/api/api_GET/ (free API key)"
    notes = ("commodity_desc=SOYBEANS, statisticcat_desc=YIELD, agg_level_desc=COUNTY. "
             "knowledge_time = publication date of the County Estimates release (Feb, y+1). "
             "Keep every vintage: NASS revises.")


class NassAcreage(_NotWired):
    name, key = "county_acres", ["year", "county_id"]
    url = "NASS June Acreage report + Cropland Data Layer (nassgeodata.gmu.edu/CropScape)"
    notes = ("State planted acres from the June Acreage report (end of June), disaggregated "
             "to counties with CDL soybean pixel shares from the previous year.")


class NassCropProgress(_NotWired):
    name, key = "conditions", ["week_date", "state"]
    url = "Quick Stats: statisticcat_desc=CONDITION / PROGRESS, weekly"
    notes = "Released Mondays 4pm ET. Good+Excellent % by state; % planted for planting dates."


class UsdaCropProduction(_NotWired):
    name, key = "usda_reports", ["year", "report"]
    url = "https://usda.library.cornell.edu (ESMIS archive: Crop Production, WASDE)"
    notes = "Release at 12:00 ET on report day. National yield forecast Aug-Nov, final in Jan."


class AnalystConsensus(_NotWired):
    name, key = "consensus", ["year", "report"]
    url = "Reuters / Bloomberg pre-report surveys (licensed)"
    notes = "Average analyst yield estimate, published 2-4 days before each USDA report."


class CmeSoybeanFutures(_NotWired):
    name, key = "futures", ["date"]
    url = "CME DataMine / Bloomberg / Databento: ZS November contract (ZSX)"
    notes = "Daily settlement 2:20pm ET (CT 1:20pm). Use the new-crop November contract."


class Era5LandWeather(WeatherSource):  # pragma: no cover - documentation stub
    """ERA5-Land hourly (0.1 deg) via the Copernicus CDS API (`cdsapi`, dataset
    'reanalysis-era5-land'). Aggregate to daily tmax/tmin/precip, then to
    counties with CDL soybean-pixel weights. ERA5T (preliminary) ~5 days latency;
    final ~2-3 months. For the US, gridMET or PRISM give ~1 day latency.

    Forecasts: NOAA GEFS (s3://noaa-gefs-pds, 31 members, 00/06/12/18Z, GRIB2;
    `herbie` or `xarray`+`cfgrib`) and ECMWF ENS (`ecmwf-opendata` package).
    Archive every run as it arrives: re-downloading later gives a different
    (reprocessed) dataset and silently breaks point-in-time integrity.
    """

    def obs_end(self, as_of):
        raise NotImplementedError

    def observed(self, year, as_of):
        raise NotImplementedError

    def forecast(self, year, as_of):
        raise NotImplementedError

    def archive(self, years, as_of):
        raise NotImplementedError


REAL_SOURCES = [NassCountyYields, NassAcreage, NassCropProgress, UsdaCropProduction,
                AnalystConsensus, CmeSoybeanFutures, Era5LandWeather]
