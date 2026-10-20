"""Charts (PNG). One function per commodity; each returns [(title, path, caption)]."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

BLUE, ORANGE, AQUA, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SEQ = LinearSegmentedColormap.from_list("seq", ["#cde2fb", "#6da7ec", "#2a78d6", "#184f95", "#0d366b"])

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "xtick.color": INK2, "ytick.color": INK2, "legend.frameon": False, "lines.linewidth": 2,
})


def _save(fig, path: Path):
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _shade_forecast(ax, periods: list[str], fc: str | None):
    if fc and fc in periods:
        i = periods.index(fc)
        ax.axvspan(i - 0.5, len(periods) - 0.5, color="#f3efe2", zorder=0)
        ax.text(i - 0.4, 1.0, "forecast", transform=ax.get_xaxis_transform(), va="top",
                fontsize=8, color=INK2)


# ---------------------------------------------------------------------------
def oil_charts(t: dict, meta: dict, out: Path) -> list[tuple]:
    bal, fc = t["balance"], meta.get("forecast_from")
    q = bal[bal["period"].str.contains("Q")]
    s = lambda label: q[q["label"] == label].set_index("period")["value"]  # noqa: E731
    res = []

    # 1. Quarterly balance
    b = s("Scenario balance")
    per = list(b.index)
    fig, ax = plt.subplots(figsize=(9, 4))
    _shade_forecast(ax, per, fc)
    ax.bar(range(len(b)), b.values, width=0.65, color=[BLUE if v >= 0 else ORANGE for v in b.values])
    ax.axhline(0, color=INK2, lw=0.8)
    for i, v in enumerate(b.values):
        ax.text(i, v + (0.15 if v >= 0 else -0.15), f"{v:+.1f}", ha="center",
                va="bottom" if v >= 0 else "top", fontsize=8, color=INK2)
    ax.set_xticks(range(len(per)), per)
    ax.set_ylabel("mb/d")
    ax.set_title("Global oil balance: supply − demand (surplus blue, deficit orange)")
    p = out / "oil_balance.png"; _save(fig, p)
    res.append(("Quarterly balance", p, "Negative = stock draw. Source: EIA STEO via workbook (active scenario)."))

    # 2. Supply vs demand
    fig, ax = plt.subplots(figsize=(9, 4))
    _shade_forecast(ax, per, fc)
    for label, name, c in [("Scenario supply", "Supply", BLUE), ("Scenario demand", "Demand", ORANGE)]:
        v = s(label)
        ax.plot(range(len(v)), v.values, color=c, marker="o", ms=4, label=name)
        ax.annotate(name, (len(v) - 1, v.values[-1]), xytext=(6, 0), textcoords="offset points",
                    color=INK, fontsize=9, va="center")
    ax.set_xticks(range(len(per)), per)
    ax.set_ylabel("mb/d")
    ax.legend(loc="lower left")
    ax.set_title("World supply and demand")
    p = out / "oil_supply_demand.png"; _save(fig, p)
    res.append(("Supply and demand", p, "Total liquids, mb/d."))

    # 3. OECD stocks
    st = s("OECD commercial stocks – scenario")
    fig, ax = plt.subplots(figsize=(9, 3.6))
    _shade_forecast(ax, per, fc)
    ax.plot(range(len(st)), st.values, color=BLUE, marker="o", ms=4)
    i_min = int(np.argmin(st.values))
    ax.annotate(f"low {st.values[i_min]:,.0f} mb ({per[i_min]})", (i_min, st.values[i_min]),
                xytext=(10, 8), textcoords="offset points", ha="left", fontsize=8, color=INK)
    ax.margins(y=0.12)
    ax.set_xticks(range(len(per)), per)
    ax.set_ylabel("million barrels")
    ax.set_title("OECD commercial inventories, end of quarter")
    p = out / "oil_oecd_stocks.png"; _save(fig, p)
    res.append(("OECD inventories", p, "Scenario path = EIA base + OECD share of the scenario stock gap."))

    # 4. Prices
    fig, ax = plt.subplots(figsize=(9, 3.6))
    _shade_forecast(ax, per, fc)
    for label, name, c in [("Brent – scenario", "Brent", BLUE), ("WTI – scenario", "WTI", ORANGE)]:
        v = s(label)
        ax.plot(range(len(v)), v.values, color=c, marker="o", ms=4, label=name)
    ax.set_xticks(range(len(per)), per)
    ax.set_ylabel("$/bbl")
    ax.legend(loc="upper left")
    ax.set_title("Brent and WTI – quarterly average")
    p = out / "oil_prices.png"; _save(fig, p)
    res.append(("Prices", p, "EIA forecast adjusted by the workbook's inventory-price model."))

    # 5. Scenario dot plot
    sc = t["scenarios"]
    sc = sc[(sc["Prob."] > 0)]
    cols = [c for c in sc.columns if c.startswith("Brent ")]
    fig, ax = plt.subplots(figsize=(9, 0.55 * len(sc) + 1.2))
    y = np.arange(len(sc))[::-1]
    for c, colr in zip(cols, [BLUE, ORANGE, AQUA]):
        ax.scatter(sc[c], y, s=60, color=colr, label=c, zorder=3, edgecolor=SURFACE, linewidth=1.5)
    for yi, (_, r) in zip(y, sc.iterrows()):
        ax.plot([r[cols].min(), r[cols].max()], [yi, yi], color=GRID, lw=2, zorder=2)
    ax.set_yticks(y, [n if n.startswith("Probability") else f"{n}  ({p_*100:.0f}%)"
                      for n, p_ in zip(sc["Scenario"], sc["Prob."])])
    ax.set_xlabel("Brent $/bbl")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=len(cols))
    ax.set_title("Brent by scenario (probability in brackets)", pad=28)
    p = out / "oil_scenarios.png"; _save(fig, p)
    res.append(("Scenarios", p, "From the Scenarios sheet comparison table."))

    # 6. OPEC+ vs target
    op = t["opec_plus"].copy()
    op = op[pd.to_numeric(op["Target Sep-26"], errors="coerce").notna()] if "Target Sep-26" in op else op.iloc[0:0]
    if not op.empty:
        op = op.sort_values("Vs target")
        fig, ax = plt.subplots(figsize=(9, 0.38 * len(op) + 1.2))
        ax.barh(op["Country"].str.slice(0, 28), op["Vs target"], height=0.6,
                color=[ORANGE if v < 0 else BLUE for v in op["Vs target"]])
        ax.axvline(0, color=INK2, lw=0.8)
        ax.set_xlabel("mb/d vs target")
        ax.set_title("OPEC+ production vs target, September")
        p = out / "oil_opec_vs_target.png"; _save(fig, p)
        res.append(("OPEC+ compliance", p, "Negative = producing below target (IEA)."))
    return res


# ---------------------------------------------------------------------------
def soybean_charts(t: dict, meta: dict, out: Path) -> list[tuple]:
    res = []
    us = t["us_bs"].set_index("Item")
    usda, house = "2026/27 USDA Oct", "2026/27 HOUSE"

    # 1. Waterfall USDA -> House ending stocks
    steps = [("USDA Oct", us.loc["ENDING STOCKS", usda], "total")]
    sign = {"Production": 1, "Imports": 1, "Beginning stocks": 1,
            "Crush": -1, "Exports": -1, "Seed": -1, "Residual": -1}
    for item, sg in sign.items():
        d = us.loc[item, "House - USDA Oct"]
        if pd.notna(d) and abs(d) > 1e-9:
            steps.append((item, sg * d, "delta"))
    steps.append(("House", us.loc["ENDING STOCKS", house], "total"))
    fig, ax = plt.subplots(figsize=(9, 4))
    run = 0
    for i, (name, v, kind) in enumerate(steps):
        if kind == "total":
            ax.bar(i, v, color=BLUE, width=0.6); run = v
            ax.text(i, v + 4, f"{v:,.0f}", ha="center", fontsize=9)
        else:
            bottom = run if v >= 0 else run + v
            ax.bar(i, abs(v), bottom=bottom, color=AQUA if v >= 0 else ORANGE, width=0.6)
            ax.text(i, run + max(v, 0) + 4, f"{v:+,.0f}", ha="center", fontsize=9)
            run += v
    ax.set_xticks(range(len(steps)), [s[0] for s in steps])
    ax.set_ylabel("M bu")
    ax.set_title("US 2026/27 ending stocks: from USDA to House view")
    p = out / "soy_waterfall.png"; _save(fig, p)
    res.append(("USDA → House bridge", p, "Orange = lowers ending stocks (more use / less supply)."))

    # 2. Ending-stocks heatmap
    g = t["grid1"].set_index("yield_bpa")
    fig, ax = plt.subplots(figsize=(9, 4.4))
    im = ax.imshow(g.values, cmap=SEQ, aspect="auto")
    ax.set_xticks(range(g.shape[1]), [f"{c:,.0f}" for c in g.columns])
    ax.set_yticks(range(g.shape[0]), [f"{r:.1f}" for r in g.index])
    ax.grid(False)
    vmid = np.nanmean(g.values)
    for i in range(g.shape[0]):
        for j in range(g.shape[1]):
            v = g.values[i, j]
            ax.text(j, i, f"{v:,.0f}", ha="center", va="center", fontsize=8,
                    color="white" if v > vmid else INK)
    yu, xu = us.loc["Yield", usda], us.loc["Exports", usda]
    yh, xh = us.loc["Yield", house], us.loc["Exports", house]
    for (yy, xx, lab) in [(yu, xu, "USDA"), (yh, xh, "House")]:
        if yy in g.index and xx in g.columns:
            ax.add_patch(plt.Rectangle((list(g.columns).index(xx) - 0.5, list(g.index).index(yy) - 0.5), 1, 1,
                                       fill=False, ec=ORANGE, lw=2.5))
            ax.text(list(g.columns).index(xx) + 0.45, list(g.index).index(yy) - 0.38, lab,
                    ha="right", va="top", fontsize=7, color=ORANGE, weight="bold")
    ax.set_xlabel("Exports (M bu)")
    ax.set_ylabel("Yield (bu/acre)")
    fig.colorbar(im, ax=ax, label="Ending stocks, M bu", shrink=0.85)
    ax.set_title("US ending stocks sensitivity: yield × exports")
    p = out / "soy_stocks_grid.png"; _save(fig, p)
    res.append(("Yield × exports grid", p, "Other items at House view."))

    # 3. Price model: scatter + regression + current cases
    reg = meta["regression"]
    slope, icpt = reg["Slope ($ per unit ln S/U)"], reg["Intercept"]
    pm = t["price_model"].set_index("Case")
    fig, ax = plt.subplots(figsize=(9, 4))
    xs = np.linspace(0.03, 0.25, 200)
    ax.plot(xs * 100, icpt + slope * np.log(xs), color=INK2, lw=1.5, ls="--", label="Regression")
    hist = t.get("price_hist")
    if hist is not None:
        ax.scatter(hist["Stocks/use"] * 100, hist["SAFP ($/bu)"], color=BLUE, s=40, zorder=3, label="History")
    for case, c in [("HOUSE", ORANGE), ("USDA Oct", AQUA)]:
        r = pm.loc[case]
        ax.scatter(r["S/U"] * 100, r["Implied SAFP ($/bu)"], s=90, color=c, zorder=4,
                   edgecolor=SURFACE, linewidth=2, label=f"{case} 26/27 (implied)")
    ax.set_xlabel("US stocks / use, %")
    ax.set_ylabel("Season-avg farm price, $/bu")
    ax.legend(loc="upper right")
    ax.set_title(f"Price vs stocks/use (R² = {reg['R-squared']:.2f})")
    p = out / "soy_price_model.png"; _save(fig, p)
    res.append(("Price model", p, "SAFP = a + b·ln(S/U). Use the House–USDA difference, not the level."))

    # 4. World ending stocks by country
    w = t["world_bs"]
    blocks = w["block"].unique()
    piv = w[w["Country"] != "WORLD"].pivot(index="Country", columns="block", values="End stocks")[blocks]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    x = np.arange(len(piv)); wdt = 0.8 / len(blocks)
    for k, (b, c) in enumerate(zip(blocks, [INK2, BLUE, ORANGE])):
        ax.bar(x + (k - (len(blocks) - 1) / 2) * wdt, piv[b], width=wdt * 0.9, color=c, label=b)
    ax.set_xticks(x, piv.index)
    ax.set_ylabel("MMT")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=len(blocks), fontsize=9)
    ax.set_title("Ending stocks by country", pad=26)
    p = out / "soy_world_stocks.png"; _save(fig, p)
    res.append(("World ending stocks", p, "USDA FAS blocks vs House view."))
    return res


CHARTS = {"oil": oil_charts, "soybeans": soybean_charts}
