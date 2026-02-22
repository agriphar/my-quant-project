# -*- coding: utf-8 -*-
"""回撤风险：当前距近期高点的回撤幅度 → LOW/MEDIUM/HIGH。保留 15% 极端模拟。"""
from __future__ import annotations

import pandas as pd

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"

# 距近期高点的回撤百分比阈值
DRAWDOWN_PCT_MEDIUM = 5.0   # 回撤 > 5% 视为 MEDIUM
DRAWDOWN_PCT_HIGH = 12.0    # 回撤 > 12% 视为 HIGH


def drawdown_from_high(current: float | None, high: float | None) -> float | None:
    """当前价相对近期高点的回撤百分比（正数表示已回撤）。"""
    if current is None or high is None or high <= 0:
        return None
    try:
        c, h = float(current), float(high)
        if c <= 0 or h <= 0:
            return None
        if c >= h:
            return 0.0
        return (h - c) / h * 100.0
    except (TypeError, ValueError):
        return None


def drawdown_risk_level(pct_drawdown: float | None) -> str:
    """
    回撤风险：距近期高点的回撤越大，风险越高。
    - 回撤 <= 5%: LOW
    - 5% < 回撤 <= 12%: MEDIUM
    - 回撤 > 12%: HIGH
    """
    if pct_drawdown is None:
        return RISK_MEDIUM
    try:
        p = float(pct_drawdown)
        if p <= 0:
            return RISK_LOW
        if p <= DRAWDOWN_PCT_MEDIUM:
            return RISK_LOW
        if p <= DRAWDOWN_PCT_HIGH:
            return RISK_MEDIUM
        return RISK_HIGH
    except (TypeError, ValueError):
        return RISK_MEDIUM


def drawdown_15pct_value(current_value: float) -> float:
    """极端风险模拟：若标的发生 15% 回撤，账户会变成多少。"""
    if current_value is None or pd.isna(current_value) or current_value < 0:
        return 0.0
    return round(float(current_value) * (1 - 0.15), 2)
