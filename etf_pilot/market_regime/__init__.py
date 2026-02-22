# -*- coding: utf-8 -*-
"""市场状态与资产性格：Core/Tactical 分类、趋势 vs 震荡、宏观状态识别。"""
from .classification import classify_etfs, get_cached_classification
from .trend import compute_trend_classification, ASSET_TREND, ASSET_OSCILLATING
from .regime_detection import (
    detect_regime,
    detect_regime_from_fetch,
    fetch_macro_series,
    classify_risk_regime,
    classify_liquidity,
    classify_usd_trend,
)

__all__ = [
    "classify_etfs",
    "get_cached_classification",
    "compute_trend_classification",
    "ASSET_TREND",
    "ASSET_OSCILLATING",
    "detect_regime",
    "detect_regime_from_fetch",
    "fetch_macro_series",
    "classify_risk_regime",
    "classify_liquidity",
    "classify_usd_trend",
]
