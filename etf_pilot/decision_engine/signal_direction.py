# -*- coding: utf-8 -*-
"""
Layer 1: Signal Direction（信号方向）

基于 Signal Engine 和 Risk Engine 的输出确定基础信号方向。

只能使用 Signal Engine 和 Risk Engine 的输出，禁止重新计算信号。
"""
from __future__ import annotations

from typing import Any

from signal_engine.states import (
    TREND_UP,
    TREND_DOWN,
    TREND_SIDEWAYS,
    TREND_UNKNOWN,
)

# 信号方向常量
DIRECTION_BULLISH = "BULLISH"
DIRECTION_BEARISH = "BEARISH"
DIRECTION_NEUTRAL = "NEUTRAL"
DIRECTION_UNKNOWN = "UNKNOWN"

# 初步动作映射
ACTION_INCREASE = "INCREASE"
ACTION_HOLD = "HOLD"
ACTION_REDUCE = "REDUCE"
ACTION_WAIT = "WAIT"

# Risk Engine 的风险等级常量
RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"


def determine_signal_direction(
    signal_states: dict[str, str] | None,
    risk_result: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """
    确定信号方向和初步动作。

    修复：现在使用 Risk Engine 的 signal_disagreement 输出，而不是重新判断信号方向。

    参数:
    - signal_states: Signal Engine 输出的状态字典
    - risk_result: Risk Engine 输出的风险结果（可选，用于获取 signal_disagreement）

    返回:
    - (direction, preliminary_action)
      - direction: "BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN"
      - preliminary_action: "INCREASE" | "HOLD" | "REDUCE" | "WAIT"

    逻辑:
    1. 优先使用 Risk Engine 的 signal_disagreement 输出判断信号方向
    2. 如果 Risk Engine 输出不可用，基于 Signal Engine 的状态进行简单判断
    3. 如果不确定信号过多 → UNKNOWN → WAIT
    4. 如果信号一致看多 → BULLISH → INCREASE
    5. 如果信号一致看空 → BEARISH → REDUCE
    6. 如果信号分歧 → NEUTRAL → HOLD
    """
    if not signal_states:
        return DIRECTION_UNKNOWN, ACTION_WAIT

    # 优先使用 Risk Engine 的输出
    if risk_result and "components" in risk_result:
        signal_disagreement = risk_result["components"].get("signal_disagreement")
        if signal_disagreement:
            # 基于 Risk Engine 的信号分歧评估判断方向
            # Risk Engine 已经统计了看多和看空信号的数量
            # 我们可以从 signal_disagreement 推断方向
            
            # 如果信号分歧为 LOW，说明信号一致（3-4 个信号一致）
            # 需要进一步判断是看多还是看空
            if signal_disagreement == RISK_LOW:
                # 信号一致，需要判断方向
                # 使用简单的启发式：检查 trend 和 valuation
                trend = signal_states.get("trend", "").upper()
                valuation = signal_states.get("valuation", "").upper()
                
                if trend == TREND_UP and valuation in ("CHEAP", "FAIR"):
                    return DIRECTION_BULLISH, ACTION_INCREASE
                elif trend == TREND_DOWN and valuation == "EXPENSIVE":
                    return DIRECTION_BEARISH, ACTION_REDUCE
                elif trend == TREND_UP:
                    return DIRECTION_BULLISH, ACTION_INCREASE
                elif trend == TREND_DOWN:
                    return DIRECTION_BEARISH, ACTION_REDUCE
                else:
                    return DIRECTION_NEUTRAL, ACTION_HOLD
            elif signal_disagreement == RISK_HIGH:
                # 信号严重分歧（2-2），返回中性
                return DIRECTION_NEUTRAL, ACTION_HOLD
            else:
                # 信号部分分歧（MEDIUM），返回中性
                return DIRECTION_NEUTRAL, ACTION_HOLD

    # 如果 Risk Engine 输出不可用，使用简单的启发式判断
    trend = signal_states.get("trend", "").upper()
    valuation = signal_states.get("valuation", "").upper()
    
    # 检查不确定信号
    unknown_count = 0
    for key in ("trend", "momentum", "valuation", "volatility"):
        state = signal_states.get(key, "").upper()
        if state.endswith("UNKNOWN"):
            unknown_count += 1
    
    if unknown_count >= 2:
        return DIRECTION_UNKNOWN, ACTION_WAIT

    # 基于 trend 和 valuation 进行简单判断
    if trend == TREND_UP and valuation in ("CHEAP", "FAIR"):
        return DIRECTION_BULLISH, ACTION_INCREASE
    elif trend == TREND_DOWN and valuation == "EXPENSIVE":
        return DIRECTION_BEARISH, ACTION_REDUCE
    elif trend == TREND_UP:
        return DIRECTION_BULLISH, ACTION_INCREASE
    elif trend == TREND_DOWN:
        return DIRECTION_BEARISH, ACTION_REDUCE
    elif trend in (TREND_SIDEWAYS, TREND_UNKNOWN):
        return DIRECTION_NEUTRAL, ACTION_HOLD
    else:
        return DIRECTION_NEUTRAL, ACTION_HOLD
