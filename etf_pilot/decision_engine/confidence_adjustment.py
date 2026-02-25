# -*- coding: utf-8 -*-
"""
Layer 3: Confidence Adjustment（置信度调整）

基于 Confidence Engine 的输出调整激进程度。

只能使用 Confidence Engine 的输出，禁止重新计算置信度。
"""
from __future__ import annotations

from typing import Any

# 动作常量
ACTION_INCREASE = "INCREASE"
ACTION_HOLD = "HOLD"
ACTION_REDUCE = "REDUCE"
ACTION_WAIT = "WAIT"

# 激进程度常量
AGGRESSIVENESS_LOW = "LOW"
AGGRESSIVENESS_MEDIUM = "MEDIUM"
AGGRESSIVENESS_HIGH = "HIGH"

# 置信度常量
CONFIDENCE_LOW = "LOW"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_HIGH = "HIGH"


def apply_confidence_adjustment(
    action: str,
    confidence_result: dict[str, Any] | None,
) -> tuple[str, str, list[str]]:
    """
    应用置信度调整，确定激进程度和最终动作。

    参数:
    - action: Layer 2 调整后的动作
        "INCREASE" | "HOLD" | "REDUCE" | "WAIT"
    - confidence_result: Confidence Engine 输出的置信度结果
        {
            "confidence": "LOW" | "MEDIUM" | "HIGH",
            "confidence_reason": [...]
        }

    返回:
    - (final_action, aggressiveness, reason_tags)
      - final_action: 最终动作（可能根据置信度进一步调整）
      - aggressiveness: 激进程度
      - reason_tags: 原因标签列表

    逻辑:
    1. 激进程度映射：
       - confidence = "HIGH" → aggressiveness = "HIGH"
       - confidence = "MEDIUM" → aggressiveness = "MEDIUM"
       - confidence = "LOW" → aggressiveness = "LOW"

    2. 动作调整（可选）：
       - 如果 confidence = "LOW" 且 action = "INCREASE"：
         - 可以考虑降级为 HOLD（低置信度时更保守）
       - 如果 confidence = "LOW" 且 action = "REDUCE"：
         - 保持 REDUCE（风险控制优先）
    """
    if not confidence_result:
        # 没有置信度信息，使用中等激进程度
        return action, AGGRESSIVENESS_MEDIUM, []

    confidence = confidence_result.get("confidence", "").upper()
    confidence_reasons = confidence_result.get("confidence_reason", [])
    reason_tags = []

    # 确定激进程度
    if confidence == CONFIDENCE_HIGH:
        aggressiveness = AGGRESSIVENESS_HIGH
        reason_tags.append("high_confidence")
    elif confidence == CONFIDENCE_LOW:
        aggressiveness = AGGRESSIVENESS_LOW
        reason_tags.append("low_confidence")
    else:
        aggressiveness = AGGRESSIVENESS_MEDIUM
        # 中等置信度不添加标签

    # 根据置信度调整动作（保守策略）
    final_action = action
    if confidence == CONFIDENCE_LOW:
        # 低置信度时，如果原动作是增加仓位，降级为持有
        if action == ACTION_INCREASE:
            final_action = ACTION_HOLD
            reason_tags.append("low_confidence_adjustment")
        # REDUCE 和 WAIT 保持不变（风险控制优先）

    return final_action, aggressiveness, reason_tags
