"""Config loading. A config is a plain nested dict loaded from YAML.

Overrides are deep-merged, which keeps tests and experiments short:

    cfg = load_config("configs/default.yaml", {"world": {"counties_per_state": 8}})
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"


def deep_merge(base: dict, override: dict | None) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config(path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> dict:
    with open(path or DEFAULT_CONFIG) as fh:
        cfg = yaml.safe_load(fh)
    return deep_merge(cfg, overrides)
