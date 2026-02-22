# -*- coding: utf-8 -*-
"""策略层兼容：re-export 自 market_regime、signal_engine、decision_engine。"""
from .asset_type import get_asset_type, ASSET_TYPE_CORE, ASSET_TYPE_TACTICAL
from signal_engine.signals import (
    compute_signal,
    compute_deviation,
    check_chase_high,
    compute_addon_suggestion,
    compute_grid_signal,
)
from decision_engine.scoring import premium_deviation, calculate_score, get_signal_from_score

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
