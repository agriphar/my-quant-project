# -*- coding: utf-8 -*-
"""资产分级策略：Core / Tactical 信号、偏离度、补仓建议；加权评分制决策。"""
from .asset_type import get_asset_type, ASSET_TYPE_CORE, ASSET_TYPE_TACTICAL
from .signals import (
    compute_signal,
    compute_deviation,
    check_chase_high,
    compute_addon_suggestion,
    compute_grid_signal,
)
from .scoring import premium_deviation, calculate_score, get_signal_from_score

__all__ = [
    "get_asset_type",
    "ASSET_TYPE_CORE",
    "ASSET_TYPE_TACTICAL",
    "compute_signal",
    "compute_deviation",
    "check_chase_high",
    "compute_addon_suggestion",
    "compute_grid_signal",
    "premium_deviation",
    "calculate_score",
    "get_signal_from_score",
]
