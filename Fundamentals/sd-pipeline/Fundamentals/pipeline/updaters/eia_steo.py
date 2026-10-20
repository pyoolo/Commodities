"""EIA Short-Term Energy Outlook via the EIA open-data API v2 (free key:
https://www.eia.gov/opendata/register.php). Writes quarterly and annual values
into the EIA_Data sheet of the oil workbook."""
from __future__ import annotations

import os
import re
from pathlib import Path

import requests

from ..common import find_row, header_columns, log
from . import write_values

API = "https://api.eia.gov/v2/steo/data/"


def _period_label(p: str) -> str:
    m = re.match(r"^(\d{4})-Q([1-4])$", p)          # 2026-Q4 -> 26Q4
    return f"{m.group(1)[2:]}Q{m.group(2)}" if m else p


def fetch(series: list[str], freq: str, start: str, end: str, key: str) -> dict[tuple[str, str], float]:
    params = {"api_key": key, "frequency": freq, "data[0]": "value", "start": start, "end": end,
              "length": 5000}
    for i, s in enumerate(series):
        params[f"facets[seriesId][{i}]"] = s
    r = requests.get(API, params=params, timeout=60)
    r.raise_for_status()
    out = {}
    for row in r.json()["response"]["data"]:
        if row.get("value") not in (None, ""):
            out[(row["seriesId"], _period_label(row["period"]))] = float(row["value"])
    return out


def update(cfg: dict, workbook: Path) -> list[str]:
    key = os.environ.get(cfg.get("api_key_env", "EIA_API_KEY"))
    if not key:
        return ["EIA update skipped: no EIA_API_KEY secret set."]

    # Which periods does the sheet hold? (e.g. 25Q1..27Q4 and 2025..2027)
    import openpyxl
    ws = openpyxl.load_workbook(workbook, read_only=False)[cfg["sheet"]]
    periods = [h for h in header_columns(ws, find_row(ws, "Series")) if re.match(r"^(\d{2}Q[1-4]|\d{4})$", h)]
    quarters = [p for p in periods if "Q" in p]
    years = [p for p in periods if "Q" not in p]

    mapping: dict[str, str] = cfg["series"]
    ids = list(set(mapping.values()))
    data = {}
    if quarters:
        data.update(fetch(ids, "quarterly", f"20{quarters[0][:2]}-Q{quarters[0][-1]}",
                          f"20{quarters[-1][:2]}-Q{quarters[-1][-1]}", key))
    if years:
        data.update(fetch(ids, "annual", years[0], years[-1], key))

    updates, missing = {}, []
    for label, sid in mapping.items():
        found = False
        for p in periods:
            if (sid, p) in data:
                updates[(label, p)] = round(data[(sid, p)], 2)
                found = True
        if not found:
            missing.append(f"EIA series {sid} ('{label.strip()}') returned no data – check the id.")
    n, warns = write_values(workbook, cfg["sheet"], updates, cfg.get("max_change_pct", 15), header_label="Series")
    log.info("EIA STEO: %d values fetched, %d written", len(updates), n)
    return missing + warns
