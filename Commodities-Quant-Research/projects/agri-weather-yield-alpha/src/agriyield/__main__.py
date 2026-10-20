"""Command line entry point.

    python -m agriyield run                       # full experiment (~10 min first run, cached after)
    python -m agriyield run --quick               # small world, ~1 min, for a demo
    python -m agriyield run --config my.yaml --out reports/my_run
"""
from __future__ import annotations

import argparse

from .config import load_config
from .pipeline import run

QUICK = {
    "world": {"counties_per_state": 12, "first_year": 1995, "last_year": 2020},
    "forecast": {"members": 8},
    "backtest": {"first_forecast_year": 2003, "first_test_year": 2009, "n_placebo": 100},
}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="agriyield", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="build the world, run walk-forward forecasts, backtest, write report")
    r.add_argument("--config", default=None, help="YAML config (default: configs/default.yaml)")
    r.add_argument("--out", default="reports", help="output directory")
    r.add_argument("--cache", default="data/cache", help="cache directory for the world and forecasts")
    r.add_argument("--quick", action="store_true", help="small world for a fast demo")
    args = ap.parse_args(argv)
    cfg = load_config(args.config, QUICK if args.quick else None)
    run(cfg, out_dir=args.out, cache_dir=args.cache)


if __name__ == "__main__":
    main()
