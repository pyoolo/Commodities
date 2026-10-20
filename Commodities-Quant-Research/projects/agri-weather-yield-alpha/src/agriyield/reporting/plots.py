"""Static figures for the README / research note (matplotlib, PNG).

Palette: validated categorical slots in fixed order (blue, orange, aqua,
yellow, magenta); text in ink tokens, never series colours; one y-axis per
panel (price and yield go in separate panels, never a dual axis).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SURFACE = "#fcfcfb"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MODEL_COLOR = {"trend": SERIES[3], "conditions": SERIES[4], "panel": SERIES[1],
               "gbm": SERIES[2], "blend": SERIES[0]}
MODEL_LABEL = {"trend": "Trend only", "conditions": "Crop conditions", "panel": "Panel regression",
               "gbm": "Gradient boosting", "blend": "Blend (panel + GBM)"}


def _style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "legend.frameon": False, "lines.linewidth": 2,
    })


def skill_by_date(skill: pd.DataFrame, usda_err: pd.DataFrame, path: Path) -> None:
    """skill: index = eval date label, columns = models, values = MAPE %."""
    _style()
    fig, ax = plt.subplots(figsize=(11, 4.8))
    x = np.arange(len(skill.index))
    for m in ["trend", "conditions", "panel", "gbm", "blend"]:
        if m in skill:
            ax.plot(x, skill[m], color=MODEL_COLOR[m], marker="o", ms=5, label=MODEL_LABEL[m])
    ax.scatter(usda_err["x"], usda_err["mape"], s=70, marker="D", color=INK2, zorder=5,
               label="USDA report (on its release date)")
    for _, r in usda_err.iterrows():
        ax.annotate(r["label"], (r["x"], r["mape"]), xytext=(9, 0), textcoords="offset points",
                    ha="left", va="center", color=INK2, fontsize=8)
    ax.set_xticks(x, skill.index)
    ax.set_xlim(-0.3, len(x) + 0.6)
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Mean absolute error vs final yield (%)")
    ax.set_title("National soybean yield forecast error by date in season")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def season_fan(year: int, ins: pd.DataFrame, truth: float, usda: pd.DataFrame,
               cons: pd.DataFrame, prices: pd.DataFrame, path: Path) -> None:
    """Two stacked panels sharing the date axis: yield distribution, then price."""
    _style()
    b = ins[(ins["year"] == year) & (ins["model"] == "blend")].sort_values("date")
    c = ins[(ins["year"] == year) & (ins["model"] == "conditions")].sort_values("date")
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(9, 6.4), sharex=True,
                                  gridspec_kw={"height_ratios": [2.2, 1]})
    ax.fill_between(b["date"], b["p10"], b["p90"], color=SERIES[0], alpha=0.18, lw=0,
                    label="Blend: 10-90% scenario range")
    ax.plot(b["date"], b["mean"], color=SERIES[0], label="Blend: expected yield")
    ax.plot(c["date"], c["mean"], color=MODEL_COLOR["conditions"], label="Crop-condition model")
    ax.axhline(truth, color=INK, lw=1.2, ls="--", label=f"Final yield ({truth:.1f})")
    u = usda[usda["year"] == year]
    k = cons[cons["year"] == year]
    ax.scatter(u["date"], u["usda_yield"], marker="D", s=55, color=SERIES[1], zorder=5, label="USDA report")
    ax.scatter(k["date"], k["consensus_yield"], marker="o", s=55, facecolor=SURFACE,
               edgecolor=SERIES[2], linewidth=2, zorder=5, label="Analyst consensus")
    ax.set_ylabel("bu/acre")
    ax.set_title(f"{year}: in-season national yield distribution vs USDA and consensus")
    ax.legend(loc="best", fontsize=8, ncol=2)
    p = prices[(prices["year"] == year) & (prices["date"] >= b["date"].min()) & (prices["date"] <= b["date"].max())]
    ax2.plot(p["date"], p["settle"], color=INK2, lw=1.5)
    ax2.set_ylabel("Nov futures ($/bu)")
    ax2.set_title("Synthetic November soybean futures", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def equity_curves(main: dict[str, pd.Series], null: dict[str, pd.Series], path: Path) -> None:
    """Cumulative P&L per sleeve: inefficient market (left) vs efficient control (right)."""
    _style()
    names = list(main.keys())
    colors = {n: SERIES[i] for i, n in enumerate(names)}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
    for ax, book, title in [(axes[0], main, "Synthetic market (gradual pricing, anchored consensus)"),
                            (axes[1], null, "Null control: efficient market, same world")]:
        ends = {}
        for n in names:
            s = book[n].cumsum() * 100
            ax.plot(s.index, s.values, color=colors[n], label=n, lw=1.8)
            ends[n] = (s.index[-1], s.iloc[-1])
        # dodge end-of-line labels so close values do not overlap
        span = max(max(abs(b[n].cumsum().max()), abs(b[n].cumsum().min())) for b in (main, null) for n in names) * 100
        gap, placed = span * 0.06, []
        for _n, (xe, ye) in sorted(ends.items(), key=lambda kv: kv[1][1]):
            yl = max(ye, placed[-1] + gap) if placed else ye
            placed.append(yl)
            ax.annotate(f"{ye:+.0f}%", (xe, ye), xytext=(xe, yl), textcoords="data",
                        va="center", color=INK2, fontsize=8)
        ax.axhline(0, color=MUTED, lw=1)
        ax.set_title(title, fontsize=10)
    axes[0].set_ylabel("Cumulative P&L (% of notional, after costs)")
    axes[0].legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def surprise_scatter(df: pd.DataFrame, path: Path) -> None:
    _style()
    fig, ax = plt.subplots(figsize=(5.6, 5.2))
    x, y = df["surprise_hat"] * 100, df["surprise_actual"] * 100
    ax.scatter(x, y, s=40, color=SERIES[0], edgecolor=SURFACE, linewidth=1, alpha=0.9)
    lim = float(np.ceil(max(abs(x).max(), abs(y).max()) + 0.5))
    ax.plot([-lim, lim], [-lim, lim], color=MUTED, lw=1, ls="--")
    ax.axhline(0, color=GRID, lw=1)
    ax.axvline(0, color=GRID, lw=1)
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    corr = np.corrcoef(x, y)[0, 1]
    hit = np.mean(np.sign(x) == np.sign(y))
    ax.set_title("Predicted vs actual USDA surprise")
    ax.text(0.03, 0.97, f"corr {corr:.2f}   direction right {hit:.0%}   n={len(df)}",
            transform=ax.transAxes, va="top", color=INK2, fontsize=9)
    ax.set_xlabel("Predicted: log(USDA-mimic / consensus), %")
    ax.set_ylabel("Actual: log(USDA / consensus), %")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
