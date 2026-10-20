"""County-level yield models.

All models predict log yield for (county, year) rows and share one interface:

    model.fit(train_df)              # rows from features.build.training_frame
    model.predict(df) -> np.ndarray  # log yield

TrendFE      county fixed effects + state linear trends, no weather. The
             "what USDA assumes in May" baseline.
PanelWeather TrendFE + linear/quadratic weather terms: the classic
             Schlenker-Roberts style econometric model.
GBMWeather   TrendFE baseline + gradient boosting on the residual, so the
             trees only learn the weather response (incl. interactions such
             as heat x drought) while the trend extrapolates linearly.
Blend        weighted average of the above.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

from ..features.build import MODEL_FEATURES

TREND_ORIGIN = 2000


class TrendFE:
    name = "trend_fe"

    def __init__(self, alpha: float = 1e-3):
        self.alpha = alpha

    def _design(self, df: pd.DataFrame) -> np.ndarray:
        county = (df["county_id"].to_numpy()[:, None] == self.counties_[None, :]).astype(float)
        state = (df["state"].to_numpy()[:, None] == self.states_[None, :]).astype(float)
        t = (df["year"].to_numpy() - TREND_ORIGIN)[:, None] / 10.0
        return np.hstack([county, state * t])

    def fit(self, df: pd.DataFrame) -> "TrendFE":
        self.counties_ = np.sort(df["county_id"].unique())
        self.states_ = np.sort(df["state"].unique())
        X = self._design(df)
        self.model_ = Ridge(alpha=self.alpha, fit_intercept=False).fit(X, df["log_yield"])
        self.resid_var_ = float(np.var(df["log_yield"] - self.model_.predict(X)))
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.model_.predict(self._design(df))


def panel_terms(df: pd.DataFrame) -> pd.DataFrame:
    """Textbook specification: degree days, precipitation (quadratic), timing."""
    return pd.DataFrame({
        "rep_days": df["rep_days"],
        "kdd_veg": df["kdd_veg"],
        "kdd_rep": df["kdd_rep"],
        "prcp_veg": df["prcp_veg"] / 100,
        "prcp_veg2": (df["prcp_veg"] / 100) ** 2,
        "prcp_rep": df["prcp_rep"] / 100,
        "prcp_rep2": (df["prcp_rep"] / 100) ** 2,
        "late_plant": np.maximum(0, df["plant_doy"] - 135),
        "sm_start": df["sm_start"],
    })


class PanelWeather(TrendFE):
    name = "panel"

    def _design(self, df):
        base = super()._design(df)
        w = (panel_terms(df).to_numpy() - self.mu_) / self.sd_
        return np.hstack([base, w])

    def fit(self, df):
        P = panel_terms(df)
        self.mu_, self.sd_ = P.mean().to_numpy(), P.std().to_numpy() + 1e-9
        self.terms_ = list(P.columns)
        return super().fit(df)

    def coefficients(self) -> pd.Series:
        """Weather coefficients in original units (per unit of each term)."""
        k = len(self.terms_)
        return pd.Series(self.model_.coef_[-k:] / self.sd_, index=self.terms_)


class GBMWeather:
    name = "gbm"

    def __init__(self, **params):
        self.params = params
        self.base = TrendFE()

    def fit(self, df: pd.DataFrame) -> "GBMWeather":
        self.base.fit(df)
        resid = df["log_yield"] - self.base.predict(df)
        self.gbm_ = HistGradientBoostingRegressor(random_state=0, **self.params)
        self.gbm_.fit(df[MODEL_FEATURES], resid)
        self.resid_var_ = float(np.var(resid - self.gbm_.predict(df[MODEL_FEATURES])))
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.base.predict(df) + self.gbm_.predict(df[MODEL_FEATURES])


class Blend:
    name = "blend"

    def __init__(self, models: dict, weights: dict[str, float]):
        self.models, self.weights = models, weights

    def fit(self, df):
        for m in self.models.values():
            m.fit(df)
        self.resid_var_ = float(sum(self.weights[k] * self.models[k].resid_var_ for k in self.weights))
        return self

    def predict(self, df):
        return sum(w * self.models[k].predict(df) for k, w in self.weights.items())


def build_models(cfg: dict) -> dict:
    mc = cfg["models"]
    panel = PanelWeather(alpha=mc["panel_ridge_alpha"] * 1e-3)
    gbm = GBMWeather(**mc["gbm"])
    return {
        "trend": TrendFE(),
        "panel": panel,
        "gbm": gbm,
        "blend": Blend({"panel": panel, "gbm": gbm}, mc["blend_weights"]),
    }


def fit_models(models: dict, train: pd.DataFrame) -> dict:
    """Fit in dependency order (Blend reuses already-fitted members)."""
    for name in ("trend", "panel", "gbm"):
        models[name].fit(train)
    b = models["blend"]
    b.resid_var_ = float(sum(b.weights[k] * b.models[k].resid_var_ for k in b.weights))
    return models
