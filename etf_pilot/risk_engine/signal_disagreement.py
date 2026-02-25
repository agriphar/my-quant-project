# -*- coding: utf-8 -*-
"""
信号分歧风险：评估多个信号状态之间的一致性。

只能使用 Signal Engine 的输出，禁止重新计算信号。
"""
from __future__ import annotations

from signal_engine.states import (
    TREND_UP,
    TREND_DOWN,
    MOMENTUM_ACCELERATING,
    MOMENTUM_WEAKENING,
    MOMENTUM_NEUTRAL,
    VALUATION_CHEAP,
    VALUATION_FAIR,
    VALUATION_EXPENSIVE,
    VOLATILITY_LOW,
    VOLATILITY_NORMAL,
    VOLATILITY_HIGH,
)

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"


def _is_bullish(state: str, factor: str) -> bool:
    """
    判断信号状态是否偏多（Bullish）。

    参数:
    - state: Signal Engine 输出的状态值
    - factor: 信号因子名称（"trend", "momentum", "valuation", "volatility"）

    返回:
    - True: 偏多
    - False: 非偏多
    """
    if not state:
        return False

    state_upper = state.upper()

    if factor == "trend":
        return state_upper == TREND_UP
    elif factor == "momentum":
        # 根据 Signal Engine 的定义：
        # - ACCELERATING: RSI < 30（超卖，可能反弹）或 RSI > 70（超买，可能加速上涨）
        # - WEAKENING: 30 <= RSI <= 45（偏弱）或 55 <= RSI <= 70（偏强）
        # - NEUTRAL: 45 < RSI < 55（中性）
        # 由于无法从状态值区分 ACCELERATING 是超卖还是超买，保守起见：
        # - NEUTRAL 视为偏多（中性，风险较低）
        # - ACCELERATING 和 WEAKENING 不视为明确的偏多或偏空
        return state_upper == MOMENTUM_NEUTRAL
    elif factor == "valuation":
        return state_upper in (VALUATION_CHEAP, VALUATION_FAIR)
    elif factor == "volatility":
        return state_upper in (VOLATILITY_LOW, VOLATILITY_NORMAL)
    return False


def _is_bearish(state: str, factor: str) -> bool:
    """
    判断信号状态是否偏空（Bearish）。

    参数:
    - state: Signal Engine 输出的状态值
    - factor: 信号因子名称（"trend", "momentum", "valuation", "volatility"）

    返回:
    - True: 偏空
    - False: 非偏空
    """
    if not state:
        return False

    state_upper = state.upper()

    if factor == "trend":
        return state_upper == TREND_DOWN
    elif factor == "momentum":
        # 根据 Signal Engine 的定义：
        # - WEAKENING: 30 <= RSI <= 45（偏弱）或 55 <= RSI <= 70（偏强）
        # - ACCELERATING: RSI < 30（超卖）或 RSI > 70（超买）
        # 由于无法从状态值区分，保守起见：
        # - WEAKENING 视为偏空（动能减弱，风险较高）
        # - ACCELERATING 和 NEUTRAL 不视为明确的偏多或偏空
        return state_upper == MOMENTUM_WEAKENING
    elif factor == "valuation":
        return state_upper == VALUATION_EXPENSIVE
    elif factor == "volatility":
        return state_upper == VOLATILITY_HIGH
    return False


def signal_disagreement_risk(signal_states: dict[str, str] | None) -> str:
    """
    信号分歧风险：统计四因子中「偏多」与「偏空」数量；严重分歧为 HIGH。

    参数:
    - signal_states: Signal Engine 输出的完整状态字典
        {
            "trend": "UP" | "DOWN" | "SIDEWAYS" | "UNKNOWN",
            "momentum": "ACCELERATING" | "WEAKENING" | "NEUTRAL" | "UNKNOWN",
            "valuation": "CHEAP" | "FAIR" | "EXPENSIVE" | "UNKNOWN",
            "volatility": "LOW" | "NORMAL" | "HIGH" | "UNKNOWN"
        }

    返回:
    - "LOW": 信号一致（3-4 个信号一致）
    - "MEDIUM": 信号部分分歧（2-2 或 1-3 分布）
    - "HIGH": 信号严重分歧（2-2 且方向相反）

    逻辑:
    - 4-0 或 3-1 一致 → LOW（方向明确）
    - 2-2 分歧 → HIGH（严重冲突）
    - 1-3 或 0-4 一致但偏空 → MEDIUM（方向一致但不利）
    """
    if not signal_states:
        return RISK_MEDIUM

    bullish = 0
    bearish = 0

    for factor in ("trend", "momentum", "valuation", "volatility"):
        state = signal_states.get(factor)
        if not state:
            continue

        if _is_bullish(state, factor):
            bullish += 1
        elif _is_bearish(state, factor):
            bearish += 1

    total = bullish + bearish

    if total == 0:
        # 所有信号都是 UNKNOWN 或无法判断，视为中等风险
        return RISK_MEDIUM

    if bullish >= 3 or bearish >= 3:
        # 3-4 个信号一致，方向明确，风险较低
        return RISK_LOW

    if bullish == 2 and bearish == 2:
        # 2-2 分歧，严重冲突，高风险
        return RISK_HIGH

    # 1-3 或 0-4 分布，部分分歧，中等风险
    return RISK_MEDIUM
