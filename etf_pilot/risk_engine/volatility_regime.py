# -*- coding: utf-8 -*-
"""
波动率制度风险：基于 Signal Engine 的 volatility 状态评估风险。

只能使用 Signal Engine 的输出，禁止使用原始数据（如 ATR%）。
"""
from __future__ import annotations

from signal_engine.states import (
    VOLATILITY_LOW,
    VOLATILITY_NORMAL,
    VOLATILITY_HIGH,
    VOLATILITY_UNKNOWN,
)

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"


def volatility_regime_risk(volatility_state: str | None) -> str:
    """
    基于 Signal Engine 的 volatility 状态评估波动率风险。

    参数:
    - volatility_state: Signal Engine 输出的 volatility 状态
        "LOW" | "NORMAL" | "HIGH" | "UNKNOWN"

    返回:
    - "LOW": 低波动风险（volatility = "LOW"）
    - "MEDIUM": 中等波动风险（volatility = "NORMAL" 或 "UNKNOWN"）
    - "HIGH": 高波动风险（volatility = "HIGH"）

    逻辑:
    - Signal Engine 的 volatility 状态直接映射到风险等级
    - 高波动环境意味着更高的交易风险
    """
    if not volatility_state:
        return RISK_MEDIUM

    volatility_state = volatility_state.upper()

    if volatility_state == VOLATILITY_HIGH:
        return RISK_HIGH
    elif volatility_state == VOLATILITY_LOW:
        return RISK_LOW
    else:
        # NORMAL 或 UNKNOWN 视为中等风险
        return RISK_MEDIUM
