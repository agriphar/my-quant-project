# -*- coding: utf-8 -*-
"""
趋势不稳定性风险：基于 Signal Engine 的 trend 状态评估趋势稳定性。

只能使用 Signal Engine 的输出，禁止使用原始数据（如 R²、slope）。
"""
from __future__ import annotations

from signal_engine.states import (
    TREND_UP,
    TREND_DOWN,
    TREND_SIDEWAYS,
    TREND_UNKNOWN,
)

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"


def trend_instability_risk(trend_state: str | None) -> str:
    """
    基于 Signal Engine 的 trend 状态评估趋势不稳定性风险。

    参数:
    - trend_state: Signal Engine 输出的 trend 状态
        "UP" | "DOWN" | "SIDEWAYS" | "UNKNOWN"

    返回:
    - "LOW": 趋势稳定（trend = "UP" 或 "DOWN"，明确趋势）
    - "MEDIUM": 趋势不稳定（trend = "SIDEWAYS"，横盘震荡）
    - "HIGH": 趋势极不稳定（trend = "UNKNOWN"，无法判断趋势）

    逻辑:
    - 明确的趋势（UP/DOWN）意味着较低的风险（方向明确）
    - 横盘震荡（SIDEWAYS）意味着中等风险（方向不明确）
    - 无法判断趋势（UNKNOWN）意味着高风险（完全不确定）
    """
    if not trend_state:
        return RISK_HIGH

    trend_state = trend_state.upper()

    if trend_state == TREND_UP or trend_state == TREND_DOWN:
        # 明确的趋势，风险较低
        return RISK_LOW
    elif trend_state == TREND_SIDEWAYS:
        # 横盘震荡，中等风险
        return RISK_MEDIUM
    else:
        # UNKNOWN 或其他未知状态，高风险
        return RISK_HIGH
