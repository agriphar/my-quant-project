# -*- coding: utf-8 -*-
"""
Layer 2: Risk Constraint（风险约束）

基于 Risk Engine 的输出调整初步动作，风险过高时限制操作。

只能使用 Risk Engine 的输出，禁止重新计算风险。
"""
from __future__ import annotations

from typing import Any

from risk_engine import (
    RISK_LOW,
    RISK_MEDIUM,
    RISK_HIGH,
    RISK_FLAG_HIGH_VOLATILITY,
    RISK_FLAG_TREND_UNKNOWN,
    RISK_FLAG_SIGNAL_CONFLICT,
    RISK_FLAG_RAPID_TRANSITIONS,
)

# 动作常量
ACTION_INCREASE = "INCREASE"
ACTION_HOLD = "HOLD"
ACTION_REDUCE = "REDUCE"
ACTION_WAIT = "WAIT"


def apply_risk_constraint(
    preliminary_action: str,
    risk_result: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    """
    应用风险约束，调整初步动作。

    参数:
    - preliminary_action: Layer 1 确定的初步动作
        "INCREASE" | "HOLD" | "REDUCE" | "WAIT"
    - risk_result: Risk Engine 输出的风险结果
        {
            "risk_level": "LOW" | "MEDIUM" | "HIGH",
            "risk_flags": [...],
            "components": {...}
        }

    返回:
    - (adjusted_action, reason_tags)
      - adjusted_action: 调整后的动作
      - reason_tags: 原因标签列表

    逻辑:
    1. 高风险约束：
       - INCREASE → HOLD（禁止增加仓位）
       - REDUCE → REDUCE（允许减少仓位）
       - HOLD → WAIT（转为等待）
       - WAIT → WAIT（保持等待）

    2. 中等风险约束：
       - INCREASE → HOLD（降低激进程度）
       - 其他动作保持不变

    3. 低风险约束：
       - 不调整初步动作

    4. 特殊风险标志：
       - signal_conflict → 强制 WAIT
       - trend_unknown → INCREASE 降级为 HOLD
       - rapid_transitions → INCREASE 降级为 HOLD
    """
    if not risk_result:
        # 没有风险信息，不调整
        return preliminary_action, []

    risk_level = risk_result.get("risk_level", "").upper()
    risk_flags = risk_result.get("risk_flags", [])
    reason_tags = []

    adjusted_action = preliminary_action

    # 检查特殊风险标志（优先级最高）
    if RISK_FLAG_SIGNAL_CONFLICT in risk_flags:
        # 信号冲突，强制等待
        adjusted_action = ACTION_WAIT
        reason_tags.append("signal_conflict_risk")
        return adjusted_action, reason_tags

    # 根据风险等级调整动作
    if risk_level == RISK_HIGH:
        reason_tags.append("high_risk_constraint")
        if preliminary_action == ACTION_INCREASE:
            # 高风险时禁止增加仓位
            adjusted_action = ACTION_HOLD
        elif preliminary_action == ACTION_HOLD:
            # 高风险时转为等待
            adjusted_action = ACTION_WAIT
        # REDUCE 和 WAIT 保持不变

    elif risk_level == RISK_MEDIUM:
        reason_tags.append("medium_risk_constraint")
        if preliminary_action == ACTION_INCREASE:
            # 中等风险时降低激进程度
            adjusted_action = ACTION_HOLD
        # 其他动作保持不变

    # RISK_LOW 时不调整动作

    # 检查其他风险标志
    if RISK_FLAG_TREND_UNKNOWN in risk_flags:
        reason_tags.append("trend_uncertainty")
        if adjusted_action == ACTION_INCREASE:
            # 趋势不确定时，降低激进程度
            adjusted_action = ACTION_HOLD

    if RISK_FLAG_RAPID_TRANSITIONS in risk_flags:
        reason_tags.append("rapid_transitions")
        if adjusted_action == ACTION_INCREASE:
            # 状态快速转换时，降低激进程度
            adjusted_action = ACTION_HOLD

    if RISK_FLAG_HIGH_VOLATILITY in risk_flags:
        reason_tags.append("volatility_risk")
        if adjusted_action == ACTION_INCREASE:
            # 高波动率时，降低激进程度
            adjusted_action = ACTION_HOLD

    return adjusted_action, reason_tags
