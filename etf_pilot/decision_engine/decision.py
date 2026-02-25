# -*- coding: utf-8 -*-
"""
Decision Engine 汇总：综合三层决策逻辑，生成最终投资组合操作。

只能使用 Signal Engine、Risk Engine 和 Confidence Engine 的输出。
"""
from __future__ import annotations

from typing import Any

from .signal_direction import determine_signal_direction
from .risk_constraint import apply_risk_constraint
from .confidence_adjustment import apply_confidence_adjustment

# 动作常量
ACTION_INCREASE = "INCREASE"
ACTION_HOLD = "HOLD"
ACTION_REDUCE = "REDUCE"
ACTION_WAIT = "WAIT"

# 激进程度常量
AGGRESSIVENESS_LOW = "LOW"
AGGRESSIVENESS_MEDIUM = "MEDIUM"
AGGRESSIVENESS_HIGH = "HIGH"


def _generate_reason_tags(
    direction: str,
    risk_tags: list[str],
    confidence_tags: list[str],
) -> list[str]:
    """
    生成完整的原因标签列表。

    参数:
    - direction: 信号方向（"BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN"）
    - risk_tags: 风险约束标签
    - confidence_tags: 置信度标签

    返回:
    - 完整的原因标签列表
    """
    tags = []

    # 添加信号方向标签
    if direction == "BULLISH":
        tags.append("bullish_signals")
    elif direction == "BEARISH":
        tags.append("bearish_signals")
    elif direction == "NEUTRAL":
        tags.append("neutral_signals")
    elif direction == "UNKNOWN":
        tags.append("uncertain_signals")

    # 添加风险约束标签
    tags.extend(risk_tags)

    # 添加置信度标签
    tags.extend(confidence_tags)

    return tags


def make_decision(
    signal_states: dict[str, str] | None = None,
    risk_result: dict[str, Any] | None = None,
    confidence_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    生成最终投资组合操作决策。

    参数:
    - signal_states: Signal Engine 输出的状态字典
        {
            "trend": "UP" | "DOWN" | "SIDEWAYS" | "UNKNOWN",
            "momentum": "ACCELERATING" | "WEAKENING" | "NEUTRAL" | "UNKNOWN",
            "valuation": "CHEAP" | "FAIR" | "EXPENSIVE" | "UNKNOWN",
            "volatility": "LOW" | "NORMAL" | "HIGH" | "UNKNOWN"
        }
    - risk_result: Risk Engine 输出的风险结果
        {
            "risk_level": "LOW" | "MEDIUM" | "HIGH",
            "risk_flags": [...],
            "components": {...}
        }
    - confidence_result: Confidence Engine 输出的置信度结果
        {
            "confidence": "LOW" | "MEDIUM" | "HIGH",
            "confidence_reason": [...]
        }

    返回:
    {
        "action": "INCREASE" | "HOLD" | "REDUCE" | "WAIT",
        "aggressiveness": "LOW" | "MEDIUM" | "HIGH",
        "reason_tags": [
            "bullish_signals" | "bearish_signals" | "neutral_signals" |
            "high_risk_constraint" | "medium_risk_constraint" |
            "high_confidence" | "low_confidence" | ...
        ]
    }

    决策流程:
    1. Layer 1: Signal Direction - 确定初步动作
    2. Layer 2: Risk Constraint - 根据风险调整动作
    3. Layer 3: Confidence Adjustment - 确定激进程度和最终动作
    """
    if not signal_states:
        # 如果没有信号状态，返回等待
        return {
            "action": ACTION_WAIT,
            "aggressiveness": AGGRESSIVENESS_LOW,
            "reason_tags": ["uncertain_signals"],
        }

    # Layer 1: Signal Direction（使用 Risk Engine 的输出）
    direction, preliminary_action = determine_signal_direction(
        signal_states, risk_result
    )

    # Layer 2: Risk Constraint
    adjusted_action, risk_tags = apply_risk_constraint(
        preliminary_action, risk_result
    )

    # Layer 3: Confidence Adjustment
    final_action, aggressiveness, confidence_tags = apply_confidence_adjustment(
        adjusted_action, confidence_result
    )

    # 生成完整的原因标签
    reason_tags = _generate_reason_tags(direction, risk_tags, confidence_tags)

    return {
        "action": final_action,
        "aggressiveness": aggressiveness,
        "reason_tags": reason_tags,
    }
