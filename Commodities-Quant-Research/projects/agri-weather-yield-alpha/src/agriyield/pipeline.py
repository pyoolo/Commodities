"""End-to-end experiment: world -> walk-forward forecasts -> signals -> backtest -> report."""
from __future__ import annotations

import hashlib
import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import engine
from .data.sources import SyntheticWeatherSource, store_from_world
from .models.condition import national_yield_history
from .reporting import plots
from .signals import strategies
from .synthetic.world import SyntheticWorld
from .validation.walkforward import run_walkforward


def _wf_cache_path(cfg: dict, cache_dir: Path) -> Path:
    key = json.dumps({"world": SyntheticWorld.cache_key(cfg), "models": cfg["models"],
                      "first": cfg["backtest"]["first_forecast_year"]}, sort_keys=True)
    return cache_dir / f"walkforward_{hashlib.sha1(key.encode()).hexdigest()[:12]}.pkl"


def evaluate_forecasts(cfg: dict, wf: dict, store, test_years: list[int]) -> dict:
    final = national_yield_history(store, "2100-01-01")
    ins = wf["inseason"][wf["inseason"]["year"].isin(test_years)].copy()
    ins["final"] = ins["year"].map(final)
    ins["ape"] = (ins["mean"] / ins["final"] - 1).abs() * 100

    labels, rows = cfg["eval_dates"], {}
    for md in labels:
        sel = ins[ins["date"].dt.strftime("%m-%d") >= md].groupby(["year", "model"]).head(1)
        rows[pd.Timestamp(f"2000-{md}").strftime("%b %d")] = sel.groupby("model")["ape"].mean()
    skill = pd.DataFrame(rows).T

    usda = store.get("usda_reports", "2100-01-01")
    usda = usda[usda["year"].isin(test_years)].copy()
    usda["ape"] = (usda["usda_yield"] / usda["year"].map(final) - 1).abs() * 100
    eval_ts = [pd.Timestamp(f"2000-{md}") for md in labels]
    names = ["Aug", "Sep", "Oct", "Nov"]
    u_rows = []
    for r, g in usda.groupby("report"):
        md = pd.Timestamp(f"2000-{cfg['usda']['report_dates'][r]}")
        x = np.interp(md.value, [t.value for t in eval_ts], np.arange(len(eval_ts)), right=len(eval_ts) - 0.2)
        u_rows.append(dict(report=names[r], label=f"USDA {names[r]}", x=x, mape=g["ape"].mean()))
    usda_err = pd.DataFrame(u_rows)

    eos = wf["county_eos"][wf["county_eos"]["year"].isin(test_years)]
    cy = store.get("county_yields", "2100-01-01")[["year", "county_id", "yield_bu_ac"]]
    eos = eos.merge(cy, on=["year", "county_id"])
    county_rmse = {m: float(np.sqrt(((eos[m] - np.log(eos["yield_bu_ac"])) ** 2).mean()) * 100)
                   for m in ["trend", "panel", "gbm", "blend"]}
    return {"skill": skill, "usda_err": usda_err, "county_rmse_pct": county_rmse}


def run_trading(cfg: dict, wf: dict, store, test_years: list[int], cal) -> dict:
    bt = cfg["backtest"]
    cost = bt["cost_bps"]
    out = {}
    tables = {}
    for model in ("blend", "conditions"):
        df = strategies.surprise_table(cfg, store, wf["inseason"], model)
        tables[model] = df
        trades = strategies.surprise_pnl(df[df["year"].isin(test_years)], cost)
        out[f"USDA surprise ({'our model' if model == 'blend' else 'condition benchmark'})"] = (trades, "date")
    pos = strategies.momentum_positions(cfg, store, wf["inseason"], "blend")
    pos = pos[pos["year"].isin(test_years)]
    mom = engine.shift_to_next_day(strategies.momentum_pnl(pos, cost), cal)
    out["Weather momentum"] = (mom, "pnl_date")
    daily = {k: engine.to_daily(t, col, cal) for k, (t, col) in out.items()}
    daily["Combined (surprise + momentum)"] = daily["USDA surprise (our model)"] + daily["Weather momentum"]
    metrics = {k: engine.summary(daily[k], out[k][0] if k in out else None) for k in daily}
    return {"daily": daily, "metrics": metrics, "surprise_tables": tables, "momentum_positions": pos}


def run(cfg: dict, out_dir: str | Path = "reports", cache_dir: str | Path = "data/cache",
        verbose: bool = True) -> dict:
    log = print if verbose else (lambda *a, **k: None)
    out_dir, cache_dir = Path(out_dir), Path(cache_dir)
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    world = SyntheticWorld.load_or_build(cfg, cache_dir=cache_dir, verbose=verbose)
    store, store_null = store_from_world(world, "main"), store_from_world(world, "null")
    wsrc = SyntheticWeatherSource(world)

    wf_path = _wf_cache_path(cfg, cache_dir)
    if wf_path.exists():
        wf = pickle.load(open(wf_path, "rb"))
        log(f"[pipeline] walk-forward loaded from cache ({wf_path.name})")
    else:
        wf = run_walkforward(cfg, store, wsrc, verbose=verbose)
        wf_path.parent.mkdir(parents=True, exist_ok=True)
        pickle.dump(wf, open(wf_path, "wb"))

    bt = cfg["backtest"]
    test_years = list(range(bt["first_test_year"], cfg["world"]["last_year"] + 1))
    cal = engine.calendar(test_years[0], test_years[-1])

    log("[pipeline] evaluating forecasts")
    ev = evaluate_forecasts(cfg, wf, store, test_years)

    log("[pipeline] backtesting on the synthetic market and on the efficient null market")
    main = run_trading(cfg, wf, store, test_years, cal)
    null = run_trading(cfg, wf, store_null, test_years, cal)

    rng = np.random.default_rng([cfg["seed"], 99])
    sur = main["surprise_tables"]["blend"]
    trades = strategies.surprise_pnl(sur[sur["year"].isin(test_years)], bt["cost_bps"])
    plac_s = engine.placebo_surprise(trades, cal, bt["cost_bps"], bt["n_placebo"], rng)
    plac_m = engine.placebo_momentum(main["momentum_positions"], cal, bt["cost_bps"], bt["n_placebo"], rng)
    p_s = float((plac_s >= main["metrics"]["USDA surprise (our model)"]["sharpe"]).mean())
    p_m = float((plac_m >= main["metrics"]["Weather momentum"]["sharpe"]).mean())

    st = sur[sur["year"].isin(test_years)]
    surprise_stats = {
        "corr_pred_vs_actual": round(float(np.corrcoef(st["surprise_hat"], st["surprise_actual"])[0, 1]), 3),
        "direction_hit_rate": round(float((np.sign(st["surprise_hat"]) == np.sign(st["surprise_actual"])).mean()), 3),
    }
    bench = main["surprise_tables"]["conditions"]
    bench = bench[bench["year"].isin(test_years)]
    bench_corr = np.corrcoef(bench["surprise_hat"], bench["surprise_actual"])[0, 1]
    surprise_stats["benchmark_corr"] = round(float(bench_corr), 3)

    # figures ---------------------------------------------------------------
    log("[pipeline] figures")
    figs = out_dir / "figures"
    plots.skill_by_date(ev["skill"], ev["usda_err"], figs / "forecast_skill_by_date.png")
    nt = national_yield_history(store, "2100-01-01")
    devs = np.log(nt / nt.rolling(10, min_periods=5).mean().shift(1)).loc[test_years]
    fan_year = int(devs.idxmin())
    plots.season_fan(fan_year, wf["inseason"], float(nt[fan_year]),
                     store.get("usda_reports", "2100-01-01"), store.get("consensus", "2100-01-01"),
                     store.get("futures", "2100-01-01"), figs / f"season_{fan_year}.png")
    keep = ["USDA surprise (our model)", "USDA surprise (condition benchmark)", "Weather momentum",
            "Combined (surprise + momentum)"]
    plots.equity_curves({k: main["daily"][k] for k in keep}, {k: null["daily"][k] for k in keep},
                        figs / "equity_curves.png")
    plots.surprise_scatter(st, figs / "surprise_scatter.png")

    # tables + metrics ------------------------------------------------------------
    wf["inseason"].to_csv(out_dir / "inseason_forecasts.csv", index=False)
    st.to_csv(out_dir / "usda_surprise_trades.csv", index=False)
    metrics = {
        "test_years": [test_years[0], test_years[-1]],
        "county_end_of_season_rmse_pct": {k: round(v, 2) for k, v in ev["county_rmse_pct"].items()},
        "national_mape_pct_by_date": ev["skill"].round(2).to_dict(orient="index"),
        "usda_mape_pct": ev["usda_err"].set_index("report")["mape"].round(2).to_dict(),
        "surprise_forecast": surprise_stats,
        "backtest_main": main["metrics"],
        "backtest_null_market": null["metrics"],
        "placebo_p_values": {"usda_surprise": round(p_s, 3), "weather_momentum": round(p_m, 3)},
        "panel_coefficients_last_year": wf["panel_coefs"].iloc[-1].round(5).to_dict(),
        "fan_chart_year": fan_year,
        "cost_bps": bt["cost_bps"],
        "runtime_s": round(time.time() - t0, 1),
    }
    with open(out_dir / "metrics.json", "w") as fh:
        json.dump(metrics, fh, indent=2, default=str)
    (out_dir / "RESULTS.md").write_text(render_results(metrics, ev))
    log(f"[pipeline] done in {metrics['runtime_s']}s -> {out_dir}/")
    return {"metrics": metrics, "world": world, "walkforward": wf, "main": main, "null": null}


def _table(rows: list[list], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def render_results(m: dict, ev: dict) -> str:
    skill = ev["skill"].round(2)
    cols = [c for c in ["trend", "conditions", "panel", "gbm", "blend"] if c in skill]
    s_rows = [[d] + [f"{skill.loc[d, c]:.2f}" for c in cols] for d in skill.index]
    b_rows = []
    for k in m["backtest_main"]:
        a, n = m["backtest_main"][k], m["backtest_null_market"][k]
        b_rows.append([k, a["sharpe"], a["ann_return_pct"], a["max_drawdown_pct"], a["positive_years"],
                       a.get("hit_rate", "-"), n["sharpe"]])
    return f"""# Results (synthetic data)

Generated by `python -m agriyield run`. Test years {m['test_years'][0]}-{m['test_years'][1]}, walk-forward
(models retrained every year on data public at the time). All numbers come from
a synthetic world; they validate the pipeline, not a live edge.

## End-of-season county accuracy (log-yield RMSE, %)

{_table([[k, v] for k, v in m['county_end_of_season_rmse_pct'].items()], ['model', 'RMSE %'])}

## National forecast error by date (mean absolute % error vs final yield)

{_table(s_rows, ['as of'] + cols)}

USDA reports, on their own release dates: {', '.join(f'{k} {v:.2f}%' for k, v in m['usda_mape_pct'].items())}

## USDA surprise forecast

Correlation of predicted vs actual surprise (USDA minus consensus): **{m['surprise_forecast']['corr_pred_vs_actual']}**
(crop-condition benchmark: {m['surprise_forecast']['benchmark_corr']}); direction right
{m['surprise_forecast']['direction_hit_rate']:.0%} of the time.

## Backtest (after {m['cost_bps']} bps per unit turnover)

{_table(b_rows, ['sleeve', 'Sharpe', 'ann. ret %', 'max DD %', 'up years', 'hit rate', 'Sharpe, null market'])}

Placebo p-values (share of randomised strategies with a higher Sharpe):
USDA surprise {m['placebo_p_values']['usda_surprise']}, weather momentum {m['placebo_p_values']['weather_momentum']}.

## Panel regression coefficients (last training window)

{_table([[k, v] for k, v in m['panel_coefficients_last_year'].items()], ['term', 'coef (log yield per unit)'])}
"""
