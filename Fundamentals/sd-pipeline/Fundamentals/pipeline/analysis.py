"""Analysis: headline numbers, rule-based commentary and revisions vs the previous run.

Every number in the commentary is computed from the extracted tables, so the
text stays correct when the workbook changes.
"""
from __future__ import annotations

import pandas as pd

from .common import fmt


# ---------------------------------------------------------------------------
# Revisions: current tidy series vs the version committed at the previous run
# ---------------------------------------------------------------------------
def revisions(current: pd.DataFrame, previous: pd.DataFrame | None, threshold: float,
              top: int = 15) -> pd.DataFrame:
    cols = ["item", "unit", "period", "previous", "current", "change"]
    if previous is None or previous.empty:
        return pd.DataFrame(columns=cols)
    m = current.merge(previous, on=["item", "period"], how="outer", suffixes=("", "_prev"))
    m["unit"] = m["unit"].fillna(m["unit_prev"])
    m = m.rename(columns={"value": "current", "value_prev": "previous"})
    m["change"] = m["current"] - m["previous"]
    changed = m[(m["change"].abs() > threshold) | m["current"].isna() | m["previous"].isna()]
    changed = changed.reindex(changed["change"].abs().sort_values(ascending=False).index)
    return changed[cols].head(top).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Oil
# ---------------------------------------------------------------------------
def _series(bal: pd.DataFrame, label: str) -> pd.Series:
    s = bal[bal["label"] == label]
    return s.set_index("period")["value"]


def analyse_oil(t: dict, meta: dict) -> dict:
    bal = t["balance"]
    q = lambda s: s[s.index.str.contains("Q")]            # noqa: E731
    yr = lambda s: s[~s.index.str.contains("Q")]          # noqa: E731

    balance = _series(bal, "Scenario balance")
    stocks = _series(bal, "OECD commercial stocks – scenario")
    brent = _series(bal, "Brent – scenario")
    wti = _series(bal, "WTI – scenario")
    fc = meta.get("forecast_from")

    bq, sq, brq = q(balance), q(stocks), q(brent)
    trough_p = sq.idxmin()
    peak_p = brq.idxmax()
    first_surplus_fc = next((p for p, v in bq.items() if fc and p >= fc and v > 0), None)
    ann = yr(balance)

    sc = t["scenarios"].set_index("Scenario")
    pw = sc.loc["Probability-weighted average"]
    base = sc.loc["EIA Base"]
    named = sc.drop(index=["Probability-weighted average", "Custom"], errors="ignore")
    named = named[named["Prob."] > 0]

    kpis = [
        {"label": f"Balance {ann.index[-2]}", "value": fmt(ann.iloc[-2], sign=True), "unit": "mb/d",
         "tone": "neg" if ann.iloc[-2] < 0 else "pos"},
        {"label": f"Balance {ann.index[-1]}", "value": fmt(ann.iloc[-1], sign=True), "unit": "mb/d",
         "tone": "neg" if ann.iloc[-1] < 0 else "pos"},
        {"label": f"OECD stocks trough ({trough_p})", "value": fmt(sq.min(), 0), "unit": "mb"},
        {"label": f"Brent {fc or ''} (EIA)", "value": fmt(brq.get(fc, float('nan')), 1), "unit": "$/bbl"},
        {"label": f"Brent {fc} prob.-weighted", "value": fmt(pw[f"Brent {fc}"], 1) if f"Brent {fc}" in pw else "–",
         "unit": "$/bbl"},
    ]

    bullets = [
        f"Active scenario in the workbook: <b>{meta['active_scenario']}</b>. Forecast quarters start at {fc}.",
        f"The market is in deficit in {ann.index[-2]} ({fmt(ann.iloc[-2], sign=True)} mb/d) and swings to a "
        f"{'surplus' if ann.iloc[-1] > 0 else 'deficit'} of {fmt(ann.iloc[-1], sign=True)} mb/d in {ann.index[-1]}; "
        f"the first forecast surplus quarter is <b>{first_surplus_fc}</b>.",
        f"OECD commercial stocks bottom at {fmt(sq.min(), 0)} mb in {trough_p}, then rebuild to "
        f"{fmt(sq.iloc[-1], 0)} mb by {sq.index[-1]} ({fmt(sq.iloc[-1] - sq.min(), 0, sign=True)} mb).",
        f"Brent peaks at ${fmt(brq.max(), 1)} in {peak_p} and falls to ${fmt(brq.iloc[-1], 1)} by {brq.index[-1]} "
        f"as inventories rebuild. WTI–Brent spread in {fc}: ${fmt(brent.get(fc) - wti.get(fc), 1)}.",
    ]
    col = f"Brent {fc}"
    if col in named:
        lo, hi = named[col].idxmin(), named[col].idxmax()
        bullets.append(
            f"Scenarios put {fc} Brent between ${fmt(named[col].min(), 1)} ({lo}) and ${fmt(named[col].max(), 1)} "
            f"({hi}); the probability-weighted value is ${fmt(pw[col], 1)}, "
            f"{fmt(pw[col] - base[col], 1, sign=True)} $/bbl vs the EIA base.")

    ag = t["agency_check"].dropna(subset=["Difference"])
    if not ag.empty:
        r = ag.loc[ag["Difference"].abs().idxmax()]
        bullets.append(f"Largest EIA–IEA gap: {r['Metric']} ({fmt(r['Difference'], 2, sign=True)} mb/d).")

    op = t["opec_plus"]
    sep_col = [c for c in op.columns if c.startswith("Sep")][0] if any(c.startswith("Sep") for c in op.columns) else None
    if sep_col and "Chg m/m" in op:
        top = op.loc[op["Chg m/m"].abs().idxmax()]
        bullets.append(f"OPEC+: biggest m/m move is {top['Country']} ({fmt(top['Chg m/m'], 2, sign=True)} mb/d, "
                       f"{fmt(top[sep_col], 2)} mb/d in {sep_col}).")

    wk = t["us_weekly"].dropna(subset=["EIA actual"])
    if not wk.empty:
        last = wk.iloc[-1]
        bullets.append(f"Last US weekly crude report ({last['Week ending']}): {fmt(last['EIA actual'], 2, sign=True)} mb "
                       f"vs {fmt(last['Expected'], 2, sign=True)} expected – {last['Read']}.")

    return {"kpis": kpis, "bullets": bullets,
            "tables": {"Scenario comparison": t["scenarios"],
                       "Agency check": t["agency_check"],
                       "Catalysts": t["catalysts"]}}


# ---------------------------------------------------------------------------
# Soybeans
# ---------------------------------------------------------------------------
def analyse_soybeans(t: dict, meta: dict) -> dict:
    us = t["us_bs"].set_index("Item")
    usda, house = "2026/27 USDA Oct", "2026/27 HOUSE"
    es_u, es_h = us.loc["ENDING STOCKS", usda], us.loc["ENDING STOCKS", house]
    su_u, su_h = us.loc["Stocks / use", usda], us.loc["Stocks / use", house]
    pm = t["price_model"].set_index("Case")
    p_h, p_u = pm.loc["HOUSE", "Implied SAFP ($/bu)"], pm.loc["USDA Oct", "Implied SAFP ($/bu)"]
    km = t["key_metrics"].set_index("Metric")
    w = km.loc["World ending stocks (MMT)"]
    wu, wh = "2026/27 USDA", "2026/27 HOUSE"
    crush = meta["crush"]["BOARD CRUSH MARGIN ($/bu)"]
    sp = t["spreads"].set_index("Spread")

    g1 = t["grid1"].set_index("yield_bpa")
    ys = sorted(g1.index)
    per_bpa = (g1.loc[ys[-1]].iloc[0] - g1.loc[ys[0]].iloc[0]) / (ys[-1] - ys[0])

    deltas = us["House - USDA Oct"].dropna()
    drivers = deltas[(deltas.abs() > 0) & ~deltas.index.str.startswith(("Memo", "TOTAL", "ENDING", "Stocks", "Check"))]

    kpis = [
        {"label": "US ending stocks – House", "value": fmt(es_h, 0), "unit": "M bu", "tone": "neg"},
        {"label": "US ending stocks – USDA Oct", "value": fmt(es_u, 0), "unit": "M bu"},
        {"label": "US stocks/use House vs USDA", "value": f"{su_h*100:.1f}% / {su_u*100:.1f}%", "unit": ""},
        {"label": "Implied SAFP House – USDA", "value": fmt(p_h - p_u, 2, sign=True), "unit": "$/bu",
         "tone": "pos" if p_h > p_u else "neg"},
        {"label": "Board crush margin", "value": fmt(crush, 2), "unit": "$/bu"},
    ]
    drv = ", ".join(f"{k.lower()} {fmt(v, 1, sign=True)}" for k, v in drivers.items())
    bullets = [
        f"House US 2026/27 carryout is <b>{fmt(es_h, 0)} M bu</b> vs USDA's {fmt(es_u, 0)} "
        f"({fmt(es_h - es_u, 0, sign=True)}), stocks/use {su_h*100:.1f}% vs {su_u*100:.1f}%.",
        f"Differences vs USDA come from: {drv}.",
        f"The S/U regression implies a farm price of ${fmt(p_h, 2)}/bu (House) vs ${fmt(p_u, 2)} (USDA balance), "
        f"{fmt(p_h - p_u, 2, sign=True)} $/bu. R² is {meta['regression'].get('R-squared', float('nan')):.2f}: use the change, not the level.",
        f"World ending stocks {fmt(w[wh], 1)} MMT (House) vs {fmt(w[wu], 1)} (USDA), "
        f"{fmt(w[wh] - w[wu], 2, sign=True)} MMT; exporter stocks/use "
        f"{km.loc['Exporter stocks / exporter use (US+BR+AR)', wh]*100:.1f}%.",
        f"Board crush margin ${fmt(crush, 2)}/bu ({'above' if crush > 2 else 'below'} the $2 'run at capacity' level); "
        f"oil is {meta['crush']['Oil share of product value']*100:.0f}% of product value.",
    ]
    for name, r in sp.iterrows():
        bullets.append(f"{name}: {fmt(r['Spread back-front (c)'], 1)}c carry = {r['% of full carry']*100:.0f}% of full carry "
                       f"({'tight' if r['% of full carry'] < 0.6 else 'comfortable' if r['% of full carry'] > 0.9 else 'neutral'}).")
    bullets.append(f"Sensitivity: 1 bu/acre of yield ≈ {fmt(abs(per_bpa), 0)} M bu of ending stocks.")

    us_tbl = t["us_bs"].drop(columns=["Source"], errors="ignore")
    us_tbl = us_tbl[~us_tbl["Item"].str.startswith(("Memo", "Check"))]
    return {"kpis": kpis, "bullets": bullets,
            "house_view": meta["house_view"],
            "tables": {"US balance sheet (M bu)": us_tbl,
                       "World key metrics": t["key_metrics"],
                       "Calendar spreads": t["spreads"]}}


ANALYSERS = {"oil": analyse_oil, "soybeans": analyse_soybeans}
