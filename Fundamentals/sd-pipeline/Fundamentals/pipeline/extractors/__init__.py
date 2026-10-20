"""Each extractor turns one workbook into tidy tables.

An extractor module exposes:
    extract(path) -> (tables: dict[str, DataFrame], meta: dict)

Convention: the table called "long" is the tidy series used for revision
tracking, with columns  item, unit, period, value.
"""
import importlib


def get(name: str):
    return importlib.import_module(f"{__name__}.{name}")
