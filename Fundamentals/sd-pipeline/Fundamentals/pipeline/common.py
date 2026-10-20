"""Shared helpers: paths, config, label-based cell lookup, git access."""
from __future__ import annotations

import io
import logging
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]          # .../Fundamentals
log = logging.getLogger("sd")


def load_config() -> dict:
    with open(ROOT / "pipeline" / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def out_dir(cfg: dict) -> Path:
    p = ROOT / cfg.get("output_dir", "output")
    (p / "data").mkdir(parents=True, exist_ok=True)
    (p / "charts").mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Label-based lookup. Scripts never use fixed row numbers, so inserting a row
# in Excel does not break the pipeline. Labels must stay unique per sheet/area.
# ---------------------------------------------------------------------------
def _norm(v) -> str:
    return str(v).strip().lower() if v is not None else ""


def find_row(ws, label: str, col: int = 1, start: int = 1, required: bool = True) -> int | None:
    target = _norm(label)
    for r in range(start, ws.max_row + 1):
        if _norm(ws.cell(r, col).value) == target:
            return r
    if required:
        raise KeyError(f"Label '{label}' not found in sheet '{ws.title}' (column {col})")
    return None


def header_columns(ws, header_row: int, first_col: int = 1) -> dict[str, int]:
    """Map header text -> column index for a header row."""
    out = {}
    for c in range(first_col, ws.max_column + 1):
        v = ws.cell(header_row, c).value
        if v is not None:
            out[str(v).strip()] = c
    return out


def read_table(ws, header_label: str, label_col: int = 1, stop_blank: bool = True,
               start: int = 1, max_rows: int = 200) -> pd.DataFrame:
    """Read a rectangular table whose header row starts with `header_label`.
    Reads down until the first fully blank row."""
    hr = find_row(ws, header_label, col=label_col, start=start)
    cols = header_columns(ws, hr, label_col)
    rows = []
    for r in range(hr + 1, min(ws.max_row, hr + max_rows) + 1):
        vals = {h: ws.cell(r, c).value for h, c in cols.items()}
        if all(v is None for v in vals.values()):
            if stop_blank:
                break
            continue
        rows.append(vals)
    return pd.DataFrame(rows, columns=list(cols))


# ---------------------------------------------------------------------------
# Git: previous committed version of a file (for revision tracking)
# ---------------------------------------------------------------------------
def git_previous_csv(path: Path, rev: str = "HEAD") -> pd.DataFrame | None:
    """Return the CSV as it was at `rev`, or None (no git / file not committed yet)."""
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
        rel = path.resolve().relative_to(Path(top).resolve()).as_posix()
        blob = subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=top,
                              capture_output=True, check=True).stdout
        return pd.read_csv(io.BytesIO(blob))
    except Exception:
        return None


def fmt(x, nd: int = 2, pct: bool = False, sign: bool = False) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "–"
    if pct:
        return f"{x*100:+.{nd}f}%" if sign else f"{x*100:.{nd}f}%"
    return f"{x:+,.{nd}f}" if sign else f"{x:,.{nd}f}"
