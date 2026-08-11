"""Shared infrastructure for the Commodities-Quant-Research projects.

Anything in here is used by more than one project. Project-specific research
code lives under ``projects/``, never in this package.
"""

from cqr_core.periods import (
    DeliveryPeriod,
    daily_index,
    parse_product,
    period_weight_matrix,
)

__all__ = [
    "DeliveryPeriod",
    "daily_index",
    "parse_product",
    "period_weight_matrix",
]

__version__ = "0.1.0"
