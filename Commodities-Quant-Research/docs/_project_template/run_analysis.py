#!/usr/bin/env python3
"""Reproduce every figure and table in this project's README.

Deterministic: seeded generators, so re-running reproduces identical numbers.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default="outputs", type=Path)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    # ... analysis ...

    print(f"wrote figures and tables to {args.outdir}/")


if __name__ == "__main__":
    main()
