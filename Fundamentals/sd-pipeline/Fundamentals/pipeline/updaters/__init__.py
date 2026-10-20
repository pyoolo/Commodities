"""Data updaters: write fresh source data into the INPUT cells of the workbooks.

Rules every updater follows:
  * never overwrite a formula cell
  * skip a value that moves more than `max_change_pct` vs the current cell
    (usually a wrong mapping) and report it as a warning
  * fail soft: a source that is down produces a warning, not a broken run
After writing, the workbook is flagged so Excel recalculates fully when opened;
the pipeline itself recalculates a copy with LibreOffice.
"""
from __future__ import annotations

from pathlib import Path

import openpyxl

from ..common import ROOT, find_row, header_columns, log


def write_values(workbook: Path, sheet: str, updates: dict[tuple[str, str | None], float],
                 max_change_pct: float, header_label: str | None = None, value_col: int | None = None
                 ) -> tuple[int, list[str]]:
    """updates: {(row_label, period_or_None): value}. period is matched against the header row
    found by `header_label`; if period is None the value goes in `value_col`."""
    wb = openpyxl.load_workbook(workbook)
    ws = wb[sheet]
    cols = header_columns(ws, find_row(ws, header_label)) if header_label else {}
    written, warns = 0, []
    for (label, period), new in updates.items():
        r = find_row(ws, label, required=False)
        c = cols.get(period) if period else value_col
        if r is None or c is None:
            warns.append(f"{workbook.name}/{sheet}: '{label.strip()}' {period or ''} not found – skipped")
            continue
        cell = ws.cell(r, c)
        if isinstance(cell.value, str) and cell.value.startswith("="):
            continue
        old = cell.value
        if isinstance(old, (int, float)) and old != 0 and abs(new / old - 1) * 100 > max_change_pct:
            warns.append(f"{workbook.name}/{sheet}: '{label.strip()}' {period or ''} {old} → {new:.2f} "
                         f"exceeds {max_change_pct}% – NOT written, check the mapping")
            continue
        if old != new:
            cell.value = new
            written += 1
    if written:
        wb.calculation.fullCalcOnLoad = True
        wb.save(workbook)
    log.info("%s/%s: %d cells updated", workbook.name, sheet, written)
    return written, warns


def run_all(cfg: dict) -> list[str]:
    from . import eia_steo, futures
    warnings: list[str] = []
    for name, mod in [("eia_steo", eia_steo), ("futures", futures)]:
        ucfg = cfg.get("updates", {}).get(name)
        if not ucfg or not ucfg.get("enabled"):
            continue
        try:
            warnings += mod.update(ucfg, ROOT / ucfg["workbook"])
        except Exception as e:
            log.exception("updater %s failed", name)
            warnings.append(f"Updater '{name}' failed: {e}. Workbook left unchanged.")
    return warnings
