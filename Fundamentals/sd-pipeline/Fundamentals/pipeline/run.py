"""Run the whole S&D pipeline.

    cd Fundamentals
    python -m pipeline.run                 # recalc + extract + analyse + charts + report
    python -m pipeline.run --update        # first pull fresh data into the workbooks
    python -m pipeline.run --only oil      # one commodity
"""
from __future__ import annotations

import argparse
import logging
import sys

from . import analysis, charts, recalc, report
from .common import ROOT, git_previous_csv, load_config, log, out_dir
from .extractors import get as get_extractor


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="fetch new data into the workbooks first")
    ap.add_argument("--only", help="run a single commodity key")
    ap.add_argument("--no-recalc", action="store_true", help="use Excel's cached values")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cfg = load_config()
    out = out_dir(cfg)
    build = ROOT / cfg.get("build_dir", "build")
    warnings: list[str] = []

    if args.update:
        from .updaters import run_all
        warnings += run_all(cfg)

    results = []
    for key, c in cfg["commodities"].items():
        if args.only and key != args.only:
            continue
        wb = ROOT / c["workbook"]
        try:
            path = wb if args.no_recalc else recalc.recalc(wb, build)
            tables, meta = get_extractor(c["extractor"]).extract(path)
            a = analysis.ANALYSERS[c["extractor"]](tables, meta)
            ch = charts.CHARTS[c["extractor"]](tables, meta, out / "charts")
        except Exception as e:                     # one broken workbook must not kill the report
            log.exception("Processing failed for %s", key)
            warnings.append(f"{c['title']}: processing failed ({type(e).__name__}: {e}). "
                            "Check sheet names / row labels in the workbook.")
            continue

        # Save tidy tables (CSV diffs are readable in pull requests, unlike .xlsx)
        for name, df in tables.items():
            df.to_csv(out / "data" / f"{key}_{name}.csv", index=False)

        long_path = out / "data" / f"{key}_long.csv"
        prev = git_previous_csv(long_path)
        rev = analysis.revisions(tables["long"], prev, c.get("revision_threshold", 0.01))
        note = ("First run: nothing to compare yet." if prev is None
                else "No change above the threshold since the previous committed run.")

        results.append({"key": key, "title": c["title"], "as_of": meta.get("as_of", ""),
                        "revisions": rev, "revisions_note": note, "charts": ch, **a})
        log.info("%s: %d revisions, %d charts", key, len(rev), len(ch))

    paths = report.render(results, out, warnings)
    for k, p in paths.items():
        log.info("report %-7s %s", k, p.relative_to(ROOT))
    return 1 if not results else 0


if __name__ == "__main__":
    sys.exit(main())
