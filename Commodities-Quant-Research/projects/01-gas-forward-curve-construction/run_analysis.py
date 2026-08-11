#!/usr/bin/env python3
"""Reproduce every figure and table in this project's README.

Usage
-----
    python run_analysis.py [--outdir outputs]

Writes PNG figures and CSV result tables. Deterministic: the synthetic data
generator is seeded, so re-running reproduces byte-identical numbers.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cqr_core.periods import parse_product
from fwdcurve.bootstrap import build_curve, check_quote_consistency
from fwdcurve.seasonality import seasonal_shape
from fwdcurve.synthetic import synthetic_quotes

PALETTE = {
    "fit": "#1f6feb",
    "truth": "#8b949e",
    "step": "#d29922",
    "prior": "#3fb950",
    "bad": "#f85149",
}


def step_curve(quotes: dict[str, float], index: pd.DatetimeIndex) -> pd.Series:
    """Baseline: flat price inside each product, finest granularity winning.

    This is what a desk gets from a naive unpack, and it is the thing the
    smooth fit has to beat.
    """
    products = sorted(
        ((parse_product(c), p) for c, p in quotes.items()),
        key=lambda t: t[0].n_days,
    )
    out = pd.Series(np.nan, index=index)
    for period, price in products:
        mask = (index.date >= period.start) & (index.date <= period.end)
        out.loc[mask & out.isna()] = price
    return out.ffill().bfill()


def fig_main(quotes, truth, fit, step, outdir: Path) -> None:
    """Fitted curve against the truth and the naive step baseline."""
    fig, (ax, axd) = plt.subplots(
        2, 1, figsize=(13, 7), sharex=True, height_ratios=[3, 1]
    )

    ax.plot(truth.index, truth, color=PALETTE["truth"], lw=0.9, label="Truth (synthetic)")
    ax.step(
        step.index, step, where="post", color=PALETTE["step"], lw=1.1,
        alpha=0.9, label="Naive step unpack",
    )
    ax.plot(fit.curve.index, fit.curve, color=PALETTE["fit"], lw=1.7, label="Smooth fit")

    for code in quotes:
        p = parse_product(code)
        ax.axvline(pd.Timestamp(p.start), color="0.85", lw=0.5, zorder=0)

    ax.set_ylabel("EUR / MWh")
    ax.set_title(
        "Daily gas forward curve from period quotes\n"
        "monthly granularity in the front year, quarterly and Cal beyond",
        loc="left", fontsize=11,
    )
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    ax.grid(alpha=0.25)

    axd.axhline(0, color="0.6", lw=0.7)
    axd.plot(fit.curve.index, fit.curve - truth, color=PALETTE["fit"], lw=1.0)
    axd.plot(step.index, step - truth, color=PALETTE["step"], lw=0.9, alpha=0.8)
    axd.set_ylabel("error")
    axd.grid(alpha=0.25)

    fig.tight_layout()
    fig.savefig(outdir / "curve_vs_baseline.png", dpi=140)
    plt.close(fig)


def fig_prior_effect(outdir: Path) -> None:
    """What the prior buys you when the market quotes almost nothing."""
    index = pd.date_range("2027-01-01", "2027-12-31", freq="D")
    quotes = {"Cal-27": 30.0}

    flat = build_curve(quotes)
    shaped = build_curve(quotes, shape_prior=seasonal_shape(index))

    fig, ax = plt.subplots(figsize=(13, 4))
    ax.plot(index, flat.curve, color=PALETTE["truth"], lw=1.4, label="No prior")
    ax.plot(index, shaped.curve, color=PALETTE["prior"], lw=1.7, label="HDD-shaped prior")
    ax.axhline(30.0, color=PALETTE["fit"], ls="--", lw=1.0, label="Cal-27 quote")
    ax.set_ylabel("EUR / MWh")
    ax.set_title(
        "A single Cal quote leaves the within-year shape undetermined — "
        "both curves reprice it exactly",
        loc="left", fontsize=11,
    )
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(outdir / "prior_effect.png", dpi=140)
    plt.close(fig)


def fig_smoothing_sweep(quotes, truth, outdir: Path) -> pd.DataFrame:
    """Roughness/accuracy trade-off across the smoothing weight."""
    shape = seasonal_shape(truth.index)
    weights = np.logspace(-3, 4, 22)
    rows = []
    for w in weights:
        fit = build_curve(quotes, shape_prior=shape, smoothness_weight=w)
        rows.append(
            {
                "smoothness_weight": w,
                "roughness": fit.roughness,
                "rmse_vs_truth": float(np.sqrt(((fit.curve - truth) ** 2).mean())),
                "max_recon_error": fit.max_abs_error,
            }
        )
    df = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.semilogx(df.smoothness_weight, df.rmse_vs_truth, "o-", color=PALETTE["fit"], ms=3.5)
    ax.set_xlabel("smoothness weight")
    ax.set_ylabel("RMSE vs truth")
    ax.set_title(
        "Over-smoothing eventually costs accuracy — but the constraints "
        "hold throughout",
        loc="left", fontsize=11,
    )
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(outdir / "smoothing_sweep.png", dpi=140)
    plt.close(fig)
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default="outputs", type=Path)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    quotes, truth = synthetic_quotes(round_to=3)
    shape = seasonal_shape(truth.index)
    fit = build_curve(quotes, shape_prior=shape)
    step = step_curve(quotes, truth.index)

    rmse = lambda x: float(np.sqrt(((x - truth) ** 2).mean()))

    print(f"products quoted        : {len(quotes)}")
    print(f"delivery days fitted   : {len(fit.curve)}")
    print(f"max reconstitution err : {fit.max_abs_error:.3e} EUR/MWh")
    incons = check_quote_consistency(quotes, tol=0.0)
    worst = incons["difference"].abs().max() if len(incons) else 0.0
    print(f"worst input inconsistency (tick rounding): {worst:.3e} EUR/MWh")
    print(f"RMSE vs truth — smooth fit : {rmse(fit.curve):.4f}")
    print(f"RMSE vs truth — step unpack: {rmse(step):.4f}")

    fig_main(quotes, truth, fit, step, args.outdir)
    fig_prior_effect(args.outdir)
    sweep = fig_smoothing_sweep(quotes, truth, args.outdir)

    fit.summary().round(6).to_csv(args.outdir / "reconstitution.csv")
    sweep.to_csv(args.outdir / "smoothing_sweep.csv", index=False)
    fit.curve.round(6).to_csv(args.outdir / "daily_curve.csv")
    print(f"\nwrote figures and tables to {args.outdir}/")


if __name__ == "__main__":
    main()
