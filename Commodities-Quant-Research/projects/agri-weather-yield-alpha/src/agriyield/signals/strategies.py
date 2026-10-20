"""Trading signals built on the in-season yield distribution.

1. USDA surprise (event-driven)
   Prices react to the USDA number *relative to consensus*, not to true yield.
   So we forecast the USDA print itself:
       usda_dev = b1 * our_dev + b2 * prev_usda_dev   ("USDA-mimic" layer, ridge, past years)
       (deviations are logs vs the May WASDE trend yield)
       surprise = log(predicted USDA / analyst consensus)
   Position (held from the close before the report to the report-day close):
       pos = -clip(surprise / scale, -1, 1)   (higher yield than consensus = bearish)

2. Weather momentum (daily, weather-market window)
   Our expected national yield moves every time a new forecast run lands.
   If the market prices weather news gradually, recent changes in our
   expectation predict the next day's price move:
       z_t   = log E_t[yield] - log E_{t-k}[yield]
       pos_t = -clip(z_t / scale, -1, 1), held close t -> close t+1
   Flat the day before a USDA report (that risk belongs to sleeve 1).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.store import PITStore


def forecast_series(inseason: pd.DataFrame, model: str) -> pd.Series:
    s = inseason[inseason["model"] == model].set_index("date")["mean"]
    return s.sort_index()


def surprise_table(cfg: dict, store: PITStore, inseason: pd.DataFrame, model: str) -> pd.DataFrame:
    """One row per (year, report): our forecast, mimic prediction, consensus, outcome."""
    bt = cfg["backtest"]
    far = pd.Timestamp("2100-01-01")
    usda = store.get("usda_reports", far)
    cons = store.get("consensus", far)
    trend = store.get("wasde_trend", far).set_index("year")["trend_yield"]
    fut = store.get("futures", far).set_index("date")["settle"]
    fc = forecast_series(inseason, model)
    years = sorted(inseason["year"].unique())

    rows = []
    for y in years:
        u = usda[usda["year"] == y].sort_values("report")
        for _, r in u.iterrows():
            date = pd.Timestamp(r["date"])
            pre = fut.index[fut.index < date].max()            # last close before release
            c = cons[(cons["year"] == y) & (cons["report"] == r["report"])].iloc[0]
            assert c["knowledge_time"] <= pre + pd.Timedelta(hours=14, minutes=20), "consensus not public yet"
            prev = trend[y] if r["report"] == 0 else u[u["report"] == r["report"] - 1]["usda_yield"].iloc[0]
            rows.append(dict(year=y, report=int(r["report"]), date=date, entry_date=pre,
                             ours=fc.asof(pre), prev=prev, consensus=c["consensus_yield"],
                             usda=r["usda_yield"], p_entry=fut.loc[pre], p_exit=fut.loc[date]))
    df = pd.DataFrame(rows)
    df["trend"] = df["year"].map(trend)
    df["our_dev"] = np.log(df["ours"] / df["trend"])
    df["prev_dev"] = np.log(df["prev"] / df["trend"])
    df["usda_dev"] = np.log(df["usda"] / df["trend"])

    # USDA-mimic layer, per report month, past years only:
    #   usda_dev ~ b1 * our_dev + b2 * prev_dev      (ridge toward b = [1, 0])
    # The prior says "USDA will print our number"; history pulls b1 toward the
    # agency's real behaviour (early reports lean on trend, revisions are partial).
    k, b0 = bt["usda_mimic_ridge"], np.array([1.0, 0.0])
    pred = []
    for _, r in df.iterrows():
        past = df[(df["year"] < r["year"]) & (df["report"] == r["report"])]
        b = b0
        if len(past) >= bt["usda_mimic_min_years"]:
            X = past[["our_dev", "prev_dev"]].to_numpy()
            b = np.linalg.solve(X.T @ X + k * np.eye(2), X.T @ past["usda_dev"].to_numpy() + k * b0)
        pred.append(b[0] * r["our_dev"] + b[1] * r["prev_dev"])
    df["d_usda_hat"] = np.array(pred) - df["prev_dev"]
    df["d_usda"] = df["usda_dev"] - df["prev_dev"]
    df["usda_hat"] = df["prev"] * np.exp(df["d_usda_hat"])
    df["surprise_hat"] = np.log(df["usda_hat"] / df["consensus"])
    df["surprise_actual"] = np.log(df["usda"] / df["consensus"])
    df["ret"] = np.log(df["p_exit"] / df["p_entry"])
    df["position"] = -np.clip(df["surprise_hat"] / (bt["surprise_scale_pct"] / 100), -1, 1)
    return df


def surprise_pnl(df: pd.DataFrame, cost_bps: float) -> pd.DataFrame:
    out = df[["year", "report", "date", "position", "ret"]].copy()
    out["pnl"] = out["position"] * out["ret"] - 2 * np.abs(out["position"]) * cost_bps / 1e4
    return out


def momentum_positions(cfg: dict, store: PITStore, inseason: pd.DataFrame, model: str) -> pd.DataFrame:
    """Daily positions and next-day returns for the weather-momentum sleeve."""
    bt = cfg["backtest"]
    far = pd.Timestamp("2100-01-01")
    fut = store.get("futures", far).set_index("date")
    usda_dates = set(pd.to_datetime(store.get("usda_reports", far)["date"]))
    fc = np.log(forecast_series(inseason, model))
    k, scale = bt["momentum_lookback_days"], bt["momentum_scale_pct"] / 100
    start_md, end_md = bt["momentum_window"]
    rows = []
    for y, s in fc.groupby(fc.index.year):
        z = s - s.shift(k)
        px = fut.loc[fut.index.year == y, "settle"]
        nxt_ret = np.log(px.shift(-1) / px)
        nxt_day = pd.Series(px.index, index=px.index).shift(-1)
        lo, hi = pd.Timestamp(f"{y}-{start_md}"), pd.Timestamp(f"{y}-{end_md}")
        for d in s.index:
            if not (lo <= d <= hi) or pd.isna(z.loc[d]) or pd.isna(nxt_ret.get(d, np.nan)):
                continue
            pos = -np.clip(z.loc[d] / scale, -1, 1)
            if nxt_day.loc[d] in usda_dates:
                pos = 0.0
            rows.append((y, d, z.loc[d], pos, nxt_ret.loc[d]))
    return pd.DataFrame(rows, columns=["year", "date", "z", "position", "ret"])


def momentum_pnl(pos: pd.DataFrame, cost_bps: float) -> pd.DataFrame:
    out = pos.copy()
    turnover = out.groupby("year")["position"].diff().abs().fillna(out["position"].abs())
    out["pnl"] = out["position"] * out["ret"] - turnover * cost_bps / 1e4
    return out
