# -*- coding: utf-8 -*-
"""
Signal Engine — 仅输出状态或概率，不输出买卖建议。

所有函数仅返回状态标签（或 0~1 概率），禁止返回「买入」「卖出」「补仓」「减仓」等建议文案。
"""
from __future__ import annotations

import math
from typing import Any

# 状态枚举（仅状态，非建议）
MOMENTUM_OVERSOLD = "oversold"
MOMENTUM_NEUTRAL = "neutral"
MOMENTUM_OVERBOUGHT = "overbought"

TREND_STRONG_UP = "strong_up"
TREND_WEAK_UP = "weak_up"
TREND_DOWN = "down"
TREND_UNKNOWN = "unknown"

VALUATION_CHEAP = "cheap"
VALUATION_FAIR_LOW = "fair_low"
VALUATION_FAIR_HIGH = "fair_high"
VALUATION_EXPENSIVE = "expensive"
VALUATION_UNKNOWN = "unknown"

VOLATILITY_LOW = "low"
VOLATILITY_MEDIUM = "medium"
VOLATILITY_HIGH = "high"
VOLATILITY_UNKNOWN = "unknown"


def momentum_state(rsi: float | None) -> str:
    """动量状态：仅基于 RSI，不给出建议。"""
    if rsi is None or not math.isfinite(rsi):
        return MOMENTUM_NEUTRAL
    r = float(rsi)
    if r < 45:
        return MOMENTUM_OVERSOLD
    if r <= 70:
        return MOMENTUM_NEUTRAL
    return MOMENTUM_OVERBOUGHT


def trend_state(r2: float | None, slope: float | None) -> str:
    """趋势状态：仅基于 180d 回归 R² 与斜率，不给出建议。"""
    if slope is None or not math.isfinite(slope):
        return TREND_UNKNOWN
    if slope <= 0:
        return TREND_DOWN
    r2_val = float(r2) if r2 is not None and math.isfinite(r2) else 0.0
    if r2_val >= 0.4:
        return TREND_STRONG_UP
    if r2_val >= 0.2:
        return TREND_WEAK_UP
    return TREND_UNKNOWN


def valuation_state(premium_pctile_60: float | None) -> str:
    """估值状态：仅基于溢价 60d 分位，不给出建议。"""
    if premium_pctile_60 is None or not math.isfinite(premium_pctile_60):
        return VALUATION_UNKNOWN
    p = float(premium_pctile_60)
    if p <= 25:
        return VALUATION_CHEAP
    if p <= 50:
        return VALUATION_FAIR_LOW
    if p <= 75:
        return VALUATION_FAIR_HIGH
    return VALUATION_EXPENSIVE


def volatility_state(atr_pct: float | None) -> str:
    """波动状态：仅基于 ATR%，不给出建议。"""
    if atr_pct is None or not math.isfinite(atr_pct) or atr_pct < 0:
        return VOLATILITY_UNKNOWN
    a = float(atr_pct)
    if a <= 1.0:
        return VOLATILITY_LOW
    if a < 3.0:
        return VOLATILITY_MEDIUM
    return VOLATILITY_HIGH


def get_signal_states(
    last_row: Any,
    r2: float | None = None,
    slope: float | None = None,
    premium_pctile_60: float | None = None,
    atr_pct: float | None = None,
) -> dict[str, str]:
    """
    汇总各因子状态，仅返回状态字典，不包含任何买卖建议。
    返回 {"momentum": str, "trend": str, "valuation": str, "volatility": str}。
    """
    rsi_val = None
    if hasattr(last_row, "get"):
        rsi_val = last_row.get("RSI")
    if atr_pct is None and hasattr(last_row, "get"):
        atr = last_row.get("ATR")
        close = last_row.get("收盘")
        if atr is not None and close is not None and close != 0:
            try:
                c = float(close)
                if c > 0 and math.isfinite(c):
                    atr_pct = float(atr) / c * 100
            except (TypeError, ValueError):
                pass
    return {
        "momentum": momentum_state(rsi_val),
        "trend": trend_state(r2, slope),
        "valuation": valuation_state(premium_pctile_60),
        "volatility": volatility_state(atr_pct),
    }
