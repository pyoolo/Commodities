"""Futures settlements from Yahoo Finance (via yfinance) into the soybean Inputs sheet.

Yahoo data is delayed and unofficial: fine for a daily report, not for P&L.
Contract tickers are explicit (ZSX26.CBT...): roll them in config.yaml together
with the row labels in the workbook when the front month changes."""
from __future__ import annotations

from pathlib import Path

from ..common import log
from . import write_values


def last_close(ticker: str) -> float | None:
    import yfinance as yf
    h = yf.Ticker(ticker).history(period="7d")
    return float(h["Close"].dropna().iloc[-1]) if not h.empty else None


def update(cfg: dict, workbook: Path) -> list[str]:
    updates, warns = {}, []
    for label, spec in cfg["tickers"].items():
        try:
            px = last_close(spec["ticker"])
        except Exception as e:
            px, _ = None, warns.append(f"{spec['ticker']}: download failed ({e})")
        if px is None:
            warns.append(f"{spec['ticker']}: no price – '{label}' left unchanged")
            continue
        updates[(label, None)] = round(px * spec.get("factor", 1), 2)
    n, w = write_values(workbook, cfg["sheet"], updates, cfg.get("max_change_pct", 20), value_col=2)
    log.info("Futures: %d prices fetched, %d written", len(updates), n)
    return warns + w
