# -*- coding: utf-8 -*-
"""
估值与趋势冲突评估：评估估值状态和趋势状态之间的冲突。

只能使用 Signal Engine 的输出，禁止使用原始数据。
"""
from __future__ import annotations

from signal_engine.states import (
    TREND_UP,
    TREND_DOWN,
    TREND_SIDEWAYS,
    TREND_UNKNOWN,
    VALUATION_CHEAP,
    VALUATION_FAIR,
    VALUATION_EXPENSIVE,
    VALUATION_UNKNOWN,
)

CONFIDENCE_LOW = "LOW"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_HIGH = "HIGH"


def valuation_trend_conflict_confidence(
    trend_state: str | None,
    valuation_state: str | None,
) -> str:
    """
    评估估值状态和趋势状态之间的冲突，冲突越大，置信度越低。

    参数:
    - trend_state: Signal Engine 输出的 trend 状态
        "UP" | "DOWN" | "SIDEWAYS" | "UNKNOWN"
    - valuation_state: Signal Engine 输出的 valuation 状态
        "CHEAP" | "FAIR" | "EXPENSIVE" | "UNKNOWN"

    返回:
    - "HIGH": 无冲突（估值和趋势方向一致）
    - "MEDIUM": 部分冲突（估值和趋势方向部分一致或不确定）
    - "LOW": 严重冲突（估值和趋势方向相反）

    逻辑:
    - **偏多组合**：
      - trend = "UP" 且 valuation = "CHEAP" 或 "FAIR" → HIGH（一致看多）
      - trend = "UP" 且 valuation = "EXPENSIVE" → MEDIUM（趋势看多但估值高）
    - **偏空组合**：
      - trend = "DOWN" 且 valuation = "EXPENSIVE" → HIGH（一致看空）
      - trend = "DOWN" 且 valuation = "CHEAP" 或 "FAIR" → MEDIUM（趋势看空但估值低）
    - **不确定组合**：
      - trend = "SIDEWAYS" 或 "UNKNOWN" → MEDIUM（无法判断）
      - valuation = "UNKNOWN" → MEDIUM（无法判断）
    """
    if not trend_state or not valuation_state:
        # 缺少状态信息，视为中等置信度
        return CONFIDENCE_MEDIUM

    trend_state = trend_state.upper()
    valuation_state = valuation_state.upper()

    # 处理不确定状态
    if trend_state in (TREND_SIDEWAYS, TREND_UNKNOWN):
        return CONFIDENCE_MEDIUM
    if valuation_state == VALUATION_UNKNOWN:
        return CONFIDENCE_MEDIUM

    # 评估趋势和估值的组合
    if trend_state == TREND_UP:
        # 上升趋势
        if valuation_state in (VALUATION_CHEAP, VALUATION_FAIR):
            # 趋势看多且估值合理/便宜，一致看多，高置信度
            return CONFIDENCE_HIGH
        elif valuation_state == VALUATION_EXPENSIVE:
            # 趋势看多但估值高，部分冲突，中等置信度
            return CONFIDENCE_MEDIUM
    elif trend_state == TREND_DOWN:
        # 下降趋势
        if valuation_state == VALUATION_EXPENSIVE:
            # 趋势看空且估值高，一致看空，高置信度
            return CONFIDENCE_HIGH
        elif valuation_state in (VALUATION_CHEAP, VALUATION_FAIR):
            # 趋势看空但估值低/合理，部分冲突，中等置信度
            return CONFIDENCE_MEDIUM

    # 其他情况，视为中等置信度
    return CONFIDENCE_MEDIUM
