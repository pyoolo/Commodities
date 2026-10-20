"""Assemble a complete, internally consistent synthetic world.

Each table mirrors a real dataset (see docs/DATA_SOURCES.md) and carries a
`knowledge_time`: the moment the information would have been public. The
point-in-time store (data/store.py) uses it to prevent look-ahead.

| synthetic table   | real counterpart                                         |
|-------------------|----------------------------------------------------------|
| county_yields     | USDA NASS Quick Stats, county soybean yield (Feb, y+1)   |
| county_acres      | USDA NASS June Acreage + CDL crop mask                   |
| planting          | USDA NASS Crop Progress (% planted) / remote sensing     |
| conditions        | USDA NASS Crop Progress & Condition, weekly, Mon 4pm ET  |
| usda_reports      | USDA NASS Crop Production / WASDE, Aug-Nov, noon ET      |
| consensus         | Reuters / Bloomberg pre-report analyst survey            |
| futures           | CME soybean futures, November contract (ZSX), settle     |
| weather           | ERA5-Land / gridMET obs + GEFS / ECMWF ENS forecasts     |
"""
from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .. import agronomy
from ..forecast.scenarios import build_scenarios, choose_analogs
from . import truth
from .geography import Geography, build_geography
from .market import simulate_year
from .weather import WeatherArrays, generate_forecast, generate_season, make_error_field


def business_day_on_or_after(ts: pd.Timestamp) -> pd.Timestamp:
    while ts.weekday() >= 5:
        ts += pd.Timedelta(days=1)
    return ts


@dataclass
class SyntheticWorld:
    cfg: dict
    geo: Geography
    years: np.ndarray
    doy: np.ndarray
    weather: WeatherArrays                 # (Y, C, D) truth = final reanalysis
    sm0: np.ndarray                        # (Y, C) soil water at season start, mm
    plant_idx: np.ndarray                  # (Y, C) planting day index
    acres: np.ndarray                      # (Y, C) thousand acres
    county_effect: np.ndarray              # (C,) hidden
    weather_offset: float                  # hidden centring constant
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)

    # ------------------------------------------------------------------ utils
    @property
    def doy0(self) -> int:
        return int(self.doy[0])

    @property
    def n_days(self) -> int:
        return len(self.doy)

    def yidx(self, year: int) -> int:
        return int(year - self.years[0])

    def as_of_index(self, ts) -> int:
        """Season day index of a timestamp (may be <0 or >= n_days)."""
        ts = pd.Timestamp(ts)
        return int(ts.dayofyear - self.doy0)

    def obs_end(self, as_of_idx: int) -> int:
        """First season day NOT yet observed when standing at `as_of_idx`."""
        return int(np.clip(as_of_idx - self.cfg["forecast"]["obs_latency_days"] + 1, 0, self.n_days))

    def season_weather(self, year: int) -> WeatherArrays:
        y = self.yidx(year)
        return WeatherArrays(self.weather.tmax[y], self.weather.tmin[y], self.weather.prcp[y])

    def forecast(self, year: int, obs_end: int) -> WeatherArrays:
        """Deterministic ensemble forecast 'archive' for a given issue."""
        fc = self.cfg["forecast"]
        if not hasattr(self, "_err_fields"):
            self._err_fields = {}
        if year not in self._err_fields:
            self._err_fields.clear()          # ~10 MB per season: keep only the current one
            self._err_fields[year] = make_error_field(
                self.geo, self.n_days, fc["horizon_days"], np.random.default_rng([self.cfg["seed"], 8, int(year)]))
        rng = np.random.default_rng([self.cfg["seed"], 2, int(year), int(obs_end)])
        return generate_forecast(self.season_weather(year), self.geo, obs_end, fc["horizon_days"],
                                 fc["members"], rng, self._err_fields[year])

    def evaluation_key(self, year: int, as_of_idx: int) -> int:
        """Map a trading day to the day whose information set is evaluated.

        Daily through the critical window (1 Jun - 30 Sep), weekly in October,
        once after the season. Before 1 June the 1 June value is used: those
        days are never traded, so this only shapes the (untraded) spring path.
        """
        jun1 = self.as_of_index(pd.Timestamp(f"{year}-06-01"))
        sep30 = self.as_of_index(pd.Timestamp(f"{year}-09-30"))
        if as_of_idx < jun1:
            return jun1
        if as_of_idx <= sep30:
            return as_of_idx
        if as_of_idx < self.n_days:
            return sep30 + 7 * ((as_of_idx - sep30) // 7)
        return self.n_days

    def analog_candidates(self, year: int) -> list[int]:
        prior = [int(y) for y in self.years if y < year]
        return prior if len(prior) >= 5 else [int(y) for y in self.years if y != year]

    # ------------------------------------------------------- efficient market
    def _true_expected_dev(self, year: int, as_of_idx: int, usda_trend: float) -> float:
        y = self.yidx(year)
        M = self.cfg["forecast"]["members"]
        end = self.obs_end(as_of_idx)
        fc = self.forecast(year, end)
        # analog year per member is fixed for the whole season: daily changes in the
        # expectation then reflect news (observations, forecasts), not resampling noise
        rng = np.random.default_rng([self.cfg["seed"], 3, int(year)])
        an = choose_analogs(self.analog_candidates(year), M, rng)
        ai = np.array([self.yidx(a) for a in an])
        analog = WeatherArrays(self.weather.tmax[ai], self.weather.tmin[ai], self.weather.prcp[ai])
        scen = build_scenarios(self.season_weather(year), end, fc, analog)
        plant = np.minimum(self.plant_idx[y], max(as_of_idx, 0))
        f = agronomy.season_features(
            scen.tmin, scen.tmax, scen.prcp, lat=self.geo.lat, awc=self.geo.awc,
            sm0=self.sm0[y], plant_idx=plant, doy0=self.doy0,
        ).features
        w = truth.weather_log_effect(f) - self.weather_offset
        log_y = (self.county_effect + truth.TREND_PER_YEAR * (year - 1995) + w
                 + 0.5 * (truth.STATE_SHOCK_SD**2 + truth.COUNTY_SHOCK_SD**2))
        nat = (np.exp(log_y) * self.acres[y]).sum(axis=1) / self.acres[y].sum()
        return float(np.log(nat.mean() / usda_trend))

    # ---------------------------------------------------------------- caching
    @staticmethod
    def cache_key(cfg: dict) -> str:
        relevant = {k: cfg[k] for k in ("seed", "world", "forecast", "usda", "market", "null_market")}
        return hashlib.sha1(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:12]

    @classmethod
    def load_or_build(cls, cfg: dict, cache_dir: str | Path | None = None, verbose: bool = True) -> "SyntheticWorld":
        if cache_dir is None:
            return cls.build(cfg, verbose=verbose)
        path = Path(cache_dir) / f"world_{cls.cache_key(cfg)}.pkl"
        if path.exists():
            with open(path, "rb") as fh:
                return pickle.load(fh)
        world = cls.build(cfg, verbose=verbose)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(world, fh)
        return world

    # ------------------------------------------------------------------ build
    @classmethod
    def build(cls, cfg: dict, verbose: bool = True, with_market: bool = True) -> "SyntheticWorld":
        log = print if verbose else (lambda *a, **k: None)
        seed = cfg["seed"]
        wc = cfg["world"]
        rng = np.random.default_rng([seed, 0])
        geo = build_geography(cfg, rng)
        years = np.arange(wc["first_year"], wc["last_year"] + 1)
        doy = np.arange(wc["season_start_doy"], wc["season_end_doy"] + 1)
        Y, C, D = len(years), geo.n_counties, len(doy)

        # 1. weather -------------------------------------------------------
        log(f"[world] weather: {Y} seasons x {C} counties x {D} days")
        seasons = [generate_season(geo, doy, np.random.default_rng([seed, 1, int(y)])) for y in years]
        weather = WeatherArrays(
            tmax=np.stack([s.tmax for s in seasons]),
            tmin=np.stack([s.tmin for s in seasons]),
            prcp=np.stack([s.prcp for s in seasons]),
        )

        # 2. soil moisture at start, planting dates -----------------------
        rng_s = np.random.default_rng([seed, 4])
        sm_field = np.stack([geo.loadings @ rng_s.normal(0, 1, geo.loadings.shape[1]) for _ in years])
        sm0 = geo.awc[None, :] * np.clip(0.75 + 0.15 * sm_field + rng_s.normal(0, 0.05, (Y, C)), 0.3, 1.0)
        w0, w1 = 100 - doy[0], 135 - doy[0]
        spring_wet = weather.prcp[:, :, w0:w1].mean(axis=-1)
        z = (spring_wet - spring_wet.mean()) / spring_wet.std()
        plant_doy = np.clip(124 + 0.9 * (geo.lat[None, :] - 37) + 5 * z + rng_s.normal(0, 2.5, (Y, C)), 108, 165)
        plant_idx = np.round(plant_doy).astype(int) - doy[0]

        # 3. true yields ----------------------------------------------------
        log("[world] agronomy + true yields")
        season = agronomy.season_features(
            weather.tmin, weather.tmax, weather.prcp, lat=geo.lat, awc=geo.awc,
            sm0=sm0, plant_idx=plant_idx, doy0=int(doy[0]), keep_daily=True,
        )
        w_raw = truth.weather_log_effect(season.features)
        offset = float(w_raw.mean())
        rng_y = np.random.default_rng([seed, 5])
        county_effect = (np.log(truth.BASE_YIELD_1995) + 0.0010 * (geo.awc - 160)
                         + rng_y.normal(0, 0.05, C))
        trend = truth.TREND_PER_YEAR * (years - 1995)
        state_shock = rng_y.normal(0, truth.STATE_SHOCK_SD, (Y, geo.n_states))[:, geo.state_idx]
        county_shock = rng_y.normal(0, truth.COUNTY_SHOCK_SD, (Y, C))
        log_yield = county_effect[None] + trend[:, None] + (w_raw - offset) + state_shock + county_shock
        yield_true = np.exp(log_yield)
        acres = geo.base_acres[None] * np.exp(0.01 * (years - 1995)[:, None] + rng_y.normal(0, 0.03, (Y, C)))
        national_true = (yield_true * acres).sum(1) / acres.sum(1)

        world = cls(cfg=cfg, geo=geo, years=years, doy=doy, weather=weather, sm0=sm0,
                    plant_idx=plant_idx, acres=acres, county_effect=county_effect,
                    weather_offset=offset)

        # 4. USDA trend (what USDA would use, from prior years only) --------
        usda_trend = np.empty(Y)
        nat_base = np.log((np.exp(county_effect)[None] * acres).sum(1) / acres.sum(1))
        for i, y in enumerate(years):
            past = np.arange(max(0, i - 20), i)
            if len(past) >= 5:
                b = np.polyfit(years[past], np.log(national_true[past]), 1)
                usda_trend[i] = np.exp(np.polyval(b, y))
            else:
                usda_trend[i] = np.exp(nat_base[i] + truth.TREND_PER_YEAR * (y - 1995))
        true_dev = np.log(national_true / usda_trend)

        # 5. tables ---------------------------------------------------------
        rng_t = np.random.default_rng([seed, 6])
        tables: dict[str, pd.DataFrame] = {}
        yy, cc = np.meshgrid(years, geo.county_id, indexing="ij")
        nass = yield_true * np.exp(rng_t.normal(0, 0.01, (Y, C)))       # survey error
        tables["county_yields"] = pd.DataFrame({
            "year": yy.ravel(), "county_id": cc.ravel(),
            "state": np.array(geo.state_names)[geo.state_idx][cc.ravel()],
            "yield_bu_ac": nass.ravel(),
            "knowledge_time": pd.to_datetime([f"{y + 1}-02-20 12:00" for y in yy.ravel()]),
        })
        tables["county_acres"] = pd.DataFrame({
            "year": yy.ravel(), "county_id": cc.ravel(), "planted_kac": acres.ravel(),
            "knowledge_time": pd.to_datetime([f"{y}-06-30 12:00" for y in yy.ravel()]),
        })
        tables["planting"] = pd.DataFrame({
            "year": yy.ravel(), "county_id": cc.ravel(),
            "plant_doy": (plant_idx + doy[0]).ravel(),
            "knowledge_time": pd.to_datetime([f"{y}-01-01" for y in yy.ravel()])
            + pd.to_timedelta((plant_idx + doy[0]).ravel() + 2, unit="D"),
        })
        tables["soil_moisture_start"] = pd.DataFrame({          # SMAP L4 / ERA5-Land swvl
            "year": yy.ravel(), "county_id": cc.ravel(), "sm0_mm": sm0.ravel(),
            "knowledge_time": pd.to_datetime([f"{y}-04-02" for y in yy.ravel()]),
        })
        tables["county_static"] = pd.DataFrame({
            "county_id": geo.county_id, "state": np.array(geo.state_names)[geo.state_idx],
            "lat": geo.lat, "lon": geo.lon, "awc_mm": geo.awc,
        })
        tables["wasde_trend"] = pd.DataFrame({                  # May WASDE trend yield
            "year": years, "trend_yield": usda_trend,
            "knowledge_time": pd.to_datetime([f"{y}-05-10 12:00" for y in years]),
        })
        tables["national_truth"] = pd.DataFrame({
            "year": years, "yield_true": national_true, "usda_trend": usda_trend, "true_dev": true_dev,
        })

        # crop condition ratings (state, weekly) ---------------------------
        log("[world] crop condition ratings")
        cidx = truth.condition_index(season.daily, plant_idx, plant_doy)       # (Y, C, D)
        rows = []
        bias = rng_t.normal(0, 4.0, (Y, geo.n_states))
        mondays_all = {}
        for i, y in enumerate(years):
            mondays = pd.date_range(f"{y}-06-01", f"{y}-09-30", freq="W-MON")
            mondays_all[y] = mondays
            for m in mondays:
                d = min(int(m.dayofyear - doy[0]) - 1, D - 1)
                for s in range(geo.n_states):
                    sel = geo.state_idx == s
                    rows.append((y, m, s, np.average(cidx[i, sel, d], weights=acres[i, sel])))
        cond = pd.DataFrame(rows, columns=["year", "week_date", "state_idx", "cidx"])
        cond["week"] = cond["week_date"].dt.isocalendar().week.astype(int)
        ref = cond.groupby(["week", "state_idx"])["cidx"].transform("median")
        noise = rng_t.normal(0, 2.0, len(cond))
        cond["good_excellent_pct"] = np.clip(
            68 + 70 * (cond["cidx"] - ref) + bias[cond["year"] - years[0], cond["state_idx"]] + noise, 15, 92)
        cond["state"] = np.array(geo.state_names)[cond["state_idx"]]
        cond["knowledge_time"] = cond["week_date"] + pd.Timedelta(hours=16)
        tables["conditions"] = cond[["year", "week_date", "state", "good_excellent_pct", "knowledge_time"]]

        # USDA reports + consensus -----------------------------------------
        uc, mc = cfg["usda"], cfg["market"]
        lam, nse = np.array(uc["weather_loading"]), np.array(uc["noise_pct"]) / 100
        rep_rows = []
        for i, y in enumerate(years):
            prev = 0.0
            for r, mmdd in enumerate(uc["report_dates"]):
                date = business_day_on_or_after(pd.Timestamp(f"{y}-{mmdd}"))
                eps = rng_t.normal(0, nse[r])
                cons_eps = rng_t.normal(0, mc["consensus_noise_pct"] / 100)
                usda_dev = lam[r] * true_dev[i] + eps
                rep_rows.append(dict(year=y, report=r, date=date, usda_dev=usda_dev, prev_dev=prev,
                                     cons_eps=cons_eps, usda_trend=usda_trend[i]))
                prev = usda_dev
        rep = pd.DataFrame(rep_rows)
        tables["_reports_raw"] = rep

        world.tables = tables
        world._usda_trend = usda_trend
        if not with_market:
            return world

        # 6. efficient expectation + futures ---------------------------------
        log("[world] efficient expectation path (true model on forecast scenarios) ...")
        eff = {}
        for i, y in enumerate(years):
            days = pd.bdate_range(f"{y}-04-01", f"{y}-11-30")
            idx = np.array([world.as_of_index(d) for d in days])
            cache: dict[int, float] = {}
            vals = []
            for a in idx:
                key = world.evaluation_key(int(y), int(a))
                if key not in cache:
                    cache[key] = world._true_expected_dev(int(y), key, usda_trend[i])
                vals.append(cache[key])
            eff[y] = (days, np.array(vals))
            if verbose and (i % 5 == 0 or i == Y - 1):
                log(f"    {y}: efficient expectation end-of-season {vals[-1]:+.3f}, truth {true_dev[i]:+.3f}")
        world._weather_path = eff
        world._efficient = world._drift_corrected(eff)
        world.tables.update(world._simulate_markets(cfg["market"], suffix=""))
        world.tables.update(world._simulate_markets({**cfg["market"], **cfg["null_market"]}, suffix="_null"))
        del world.tables["_reports_raw"]
        return world

    @staticmethod
    def _drift_features(days: pd.DatetimeIndex, v: np.ndarray, year: int) -> pd.DataFrame:
        s = pd.Series(v, index=days)
        rem = np.clip((pd.Timestamp(f"{year}-09-30") - days).days / 120, 0, 1)
        f = {}
        for k in (1, 3, 5, 10, 20):
            dk = (s - s.shift(k)).fillna(0.0).to_numpy()
            f[f"d{k}"], f[f"d{k}r"] = dk, dk * rem
        return pd.DataFrame(f, index=days)

    def _drift_corrected(self, paths: dict) -> dict:
        """Efficient weather expectation = best prediction of the end-of-season value.

        The scenario engine uses climatology beyond the 15-day forecast window,
        while weather regimes persist; evidence of a regime therefore arrives a
        little more each day and the raw path D_t drifts predictably (daily
        changes are positively autocorrelated). An efficient market anticipates
        that. We fit, across all simulated seasons (the market knows the world's
        statistics), E[D_final - D_t | recent changes of D] and add it to D_t.
        The resulting path has ~zero autocorrelation in its daily changes.
        """
        X, yv = [], []
        for y, (days, v) in paths.items():
            f = self._drift_features(days, v, int(y))
            m = (days.month >= 6) & (days.month <= 10)
            X.append(f[m])
            yv.append(v[-1] - v[m])
        X = pd.concat(X)
        beta = np.linalg.lstsq(np.column_stack([np.ones(len(X)), X.to_numpy()]), np.concatenate(yv), rcond=None)[0]
        self._drift_beta = beta
        out = {}
        for y, (days, v) in paths.items():
            f = self._drift_features(days, v, int(y)).to_numpy()
            corr = beta[0] + f @ beta[1:]
            corr[days.month < 6] = 0.0                     # nothing to correct before the weather market
            corr[days >= pd.Timestamp(f"{y}-11-01")] = 0.0  # season over: D is final
            out[y] = (days, v + corr)
        return out

    def _uncertainty_profile(self) -> tuple[float, dict[int, float]]:
        """Variances the efficient market needs (it knows the world's statistics).

        s_var : variance of the yield component weather cannot explain
        f_var : by season day, variance of the weather still to come
                (final weather expectation minus expectation on that day)
        """
        nt = self.tables["national_truth"].set_index("year")["true_dev"]
        finals = {y: v[-1] for y, (d, v) in self._efficient.items()}
        s_var = float(np.var([nt[y] - finals[y] for y in self.years]))
        diffs: dict[int, list[float]] = {}
        for y, (days, v) in self._efficient.items():
            for d, x in zip(days, v):
                diffs.setdefault(self.as_of_index(d), []).append(finals[y] - x)
        return max(s_var, 1e-5), {k: float(np.var(vals)) for k, vals in diffs.items()}

    def _simulate_markets(self, mparams: dict, suffix: str) -> dict[str, pd.DataFrame]:
        rep = self.tables["_reports_raw"].copy()
        kappa = mparams["consensus_kappa"]
        lam = np.array(self.cfg["usda"]["weather_loading"])
        # Analysts can anticipate the systematic part of the report (USDA's
        # weather loading applied to what public information implies on the
        # survey date) but not USDA's own sampling noise. kappa < 1: they only
        # move part of the way from the previous USDA number (anchoring).
        anticip = []
        for _, r in rep.iterrows():
            days, effv = self._efficient[r["year"]]
            survey = pd.Timestamp(r["date"]) - pd.offsets.BDay(3)
            anticip.append(lam[r["report"]] * effv[days.get_indexer([survey], method="pad")[0]])
        rep["anticipated_dev"] = anticip
        rep["consensus_dev"] = rep["prev_dev"] + kappa * (rep["anticipated_dev"] - rep["prev_dev"]) + rep["cons_eps"]
        rep["usda_yield"] = rep["usda_trend"] * np.exp(rep["usda_dev"])
        rep["consensus_yield"] = rep["usda_trend"] * np.exp(rep["consensus_dev"])
        rep["knowledge_time"] = rep["date"] + pd.Timedelta(hours=12)                 # noon ET release
        # survey published 3 business days before release, after the close
        rep["consensus_knowledge_time"] = rep["date"] - pd.offsets.BDay(3) + pd.Timedelta(hours=17)
        rep["lam"] = lam[rep["report"].to_numpy()]
        rep["eps_var"] = (np.array(self.cfg["usda"]["noise_pct"]) / 100)[rep["report"].to_numpy()] ** 2
        s_var, f_var_by_idx = self._uncertainty_profile()
        fut = []
        for y in self.years:
            days, effv = self._efficient[y]
            fv = np.array([f_var_by_idx.get(self.as_of_index(d), 0.0) for d in days])
            r = rep[rep["year"] == y]
            rng_n = np.random.default_rng([self.cfg["seed"], 7, int(y)])           # same noise in both markets
            noise = rng_n.normal(0, mparams["daily_vol_pct"] / 100, len(days))
            rnoise = rng_n.normal(0, 0.006, len(days))
            p0 = 10.0 * np.exp(rng_n.normal(0, 0.2))
            df = simulate_year(days, effv, fv, s_var, r, mparams, noise, rnoise, p0)
            df["year"] = y
            fut.append(df)
        fut = pd.concat(fut, ignore_index=True)
        fut["knowledge_time"] = fut["date"] + pd.Timedelta(hours=14, minutes=20)     # CBOT settle
        usda = rep[["year", "report", "date", "usda_trend", "usda_yield", "usda_dev", "knowledge_time"]]
        cons = rep[["year", "report", "date", "consensus_yield", "consensus_dev", "consensus_knowledge_time"]] \
            .rename(columns={"consensus_knowledge_time": "knowledge_time"})
        return {f"usda_reports{suffix}": usda, f"consensus{suffix}": cons, f"futures{suffix}": fut}
