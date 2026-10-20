"""Render the HTML report (self-contained, for GitHub Pages / email) and a Markdown
summary (REPORT.md, readable directly in the GitHub repo)."""
from __future__ import annotations

import base64
import html
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from .common import ROOT

PCT_HINT = re.compile(r"(%|share|stocks ?/ ?use|s/u|prob)", re.I)


def _cell(v, row_label: str, col: str, unit: str | None) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        is_pct = unit == "%" or (unit is None and (PCT_HINT.search(str(col)) or PCT_HINT.search(str(row_label))))
        if is_pct and abs(v) <= 1.5:
            return f"{v*100:.1f}%"
        if float(v).is_integer() and abs(v) >= 100:
            return f"{v:,.0f}"
        return f"{v:,.2f}"
    return html.escape(str(v))


def df_html(df: pd.DataFrame, max_rows: int = 40) -> str:
    df = df.head(max_rows)
    cols = list(df.columns)
    unit_col = next((c for c in cols if str(c).lower() == "unit"), None)
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols)
    body = []
    for _, r in df.iterrows():
        label = str(r[cols[0]])
        unit = r[unit_col] if unit_col else None
        body.append("<tr>" + "".join(f"<td>{_cell(r[c], label, c, unit)}</td>" for c in cols) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def revisions_html(rev: pd.DataFrame) -> str:
    rows = []
    for _, r in rev.iterrows():
        ch = r["change"]
        cls = "" if pd.isna(ch) else ("up" if ch > 0 else "down")
        f = lambda x: "new" if pd.isna(x) else f"{x:,.2f}"  # noqa: E731
        rows.append(f"<tr><td>{html.escape(str(r['item']))}</td><td>{r['period']}</td><td>{html.escape(str(r['unit']))}</td>"
                    f"<td>{f(r['previous'])}</td><td>{f(r['current'])}</td>"
                    f"<td class='{cls}'>{'' if pd.isna(ch) else f'{ch:+,.2f}'}</td></tr>")
    return ("<table><thead><tr><th>Item</th><th>Period</th><th>Unit</th><th>Previous</th><th>Current</th>"
            f"<th>Change</th></tr></thead><tbody>{''.join(rows)}</tbody></table>")


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "local"


def render(results: list[dict], out: Path, warnings: list[str]) -> dict[str, Path]:
    now = datetime.now(timezone.utc)
    env = Environment(loader=FileSystemLoader(ROOT / "pipeline" / "templates"), autoescape=True)
    tpl = env.get_template("report.html.j2")

    def ctx(embed: bool):
        comms = []
        for r in results:
            charts = []
            for title, path, caption in r["charts"]:
                src = ("data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()) if embed \
                    else Path(path).relative_to(out).as_posix()
                charts.append({"title": title, "src": src, "caption": caption})
            rev = r["revisions"]
            comms.append({
                "key": r["key"], "title": r["title"], "as_of": r["as_of"], "kpis": r["kpis"],
                "bullets": r["bullets"], "house_view": r.get("house_view"), "charts": charts,
                "revisions_html": revisions_html(rev) if not rev.empty else "",
                "revisions_note": r["revisions_note"],
                "tables": [(n, df_html(d)) for n, d in r["tables"].items()],
            })
        return {"commodities": comms, "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
                "date": now.strftime("%Y-%m-%d"), "commit": _commit(), "warnings": warnings}

    paths = {}
    # Self-contained file (charts embedded): send by email, open offline, archive
    paths["html"] = out / "report.html"
    paths["html"].write_text(tpl.render(**ctx(embed=True)), encoding="utf-8")
    # GitHub Pages entry point
    paths["index"] = out / "index.html"
    paths["index"].write_text(tpl.render(**ctx(embed=False)), encoding="utf-8")
    # Dated archive copy
    arch = out / "archive"; arch.mkdir(exist_ok=True)
    paths["archive"] = arch / f"report_{now:%Y-%m-%d}.html"
    paths["archive"].write_text(paths["html"].read_text(encoding="utf-8"), encoding="utf-8")
    # Markdown summary
    paths["md"] = out / "REPORT.md"
    paths["md"].write_text(markdown(results, now, warnings), encoding="utf-8")
    return paths


def _strip(s: str) -> str:
    return re.sub(r"</?b>", "**", s)


def markdown(results: list[dict], now: datetime, warnings: list[str]) -> str:
    md = [f"# S&D report – {now:%Y-%m-%d}", "",
          f"_Generated automatically {now:%Y-%m-%d %H:%M} UTC. Full report: `report.html`._", ""]
    for w in warnings:
        md.append(f"> ⚠️ {w}")
    for r in results:
        md += ["", f"## {r['title']}", f"_{r['as_of']}_", "",
               "| " + " | ".join(k["label"] for k in r["kpis"]) + " |",
               "|" + "---|" * len(r["kpis"]),
               "| " + " | ".join(f"{k['value']} {k['unit']}" for k in r["kpis"]) + " |", ""]
        md += [f"- {_strip(b)}" for b in r["bullets"]]
        rev = r["revisions"]
        md += ["", "**Changes since previous run**", ""]
        if rev.empty:
            md.append(f"_{r['revisions_note']}_")
        else:
            md += ["| Item | Period | Previous | Current | Change |", "|---|---|---:|---:|---:|"]
            for _, x in rev.iterrows():
                f = lambda v: "new" if pd.isna(v) else f"{v:,.2f}"  # noqa: E731
                ch = "" if pd.isna(x["change"]) else f"{x['change']:+,.2f}"
                md.append(f"| {str(x['item']).replace('|', '›')} | {x['period']} | {f(x['previous'])} | {f(x['current'])} | {ch} |")
        md.append("")
        for title, path, _ in r["charts"]:
            md.append(f"![{title}](charts/{Path(path).name})")
    return "\n".join(md) + "\n"
