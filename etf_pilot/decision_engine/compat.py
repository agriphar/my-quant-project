# -*- coding: utf-8 -*-
"""
向后兼容适配器：将新架构的输出转换为旧格式。

此模块提供适配器函数，帮助从旧接口平滑迁移到新架构。
"""
from __future__ import annotations

import math
from typing import Any


def decision_to_legacy_format(decision: dict[str, Any]) -> tuple[str, str, str, str, bool, float]:
    """
    将新架构的决策输出转换为旧格式。

    参数:
    - decision: 新架构的决策输出
        {
            "action": "INCREASE" | "HOLD" | "REDUCE" | "WAIT",
            "aggressiveness": "LOW" | "MEDIUM" | "HIGH",
            "reason_tags": [...],
            ...
        }

    返回:
    - (action_cn, reason, display_label, confidence_band, conflicting_signals, total_score)
      - action_cn: 中文动作（"强烈建议补仓" | "持有观望" | "考虑套利/减仓" | "等待"）
      - reason: 理由（字符串）
      - display_label: 显示标签（"偏多，可考虑补仓" | "观望" | "偏空，可考虑减仓" | "等待"）
      - confidence_band: 置信度区间（"high" | "medium" | "low"）
      - conflicting_signals: 信号冲突标志（bool）
      - total_score: 总分（float，已废弃，返回0.0）
    """
    action = decision.get("action", "WAIT")
    aggressiveness = decision.get("aggressiveness", "MEDIUM")
    reason_tags = decision.get("reason_tags", [])
    risk_result = decision.get("risk_result", {})

    # 转换动作为中文
    action_map = {
        "INCREASE": "强烈建议补仓",
        "HOLD": "持有观望",
        "REDUCE": "考虑套利/减仓",
        "WAIT": "等待",
    }
    action_cn = action_map.get(action, "持有观望")

    # 生成理由（基于 reason_tags）
    reason_parts = []
    if "bullish_signals" in reason_tags:
        reason_parts.append("信号看多")
    elif "bearish_signals" in reason_tags:
        reason_parts.append("信号看空")
    elif "neutral_signals" in reason_tags:
        reason_parts.append("信号中性")
    
    if "high_risk_constraint" in reason_tags:
        reason_parts.append("高风险约束")
    elif "medium_risk_constraint" in reason_tags:
        reason_parts.append("中等风险")
    
    if "high_confidence" in reason_tags:
        reason_parts.append("高置信度")
    elif "low_confidence" in reason_tags:
        reason_parts.append("低置信度")
    
    reason = "；".join(reason_parts) if reason_parts else "综合评估"

    # 生成显示标签
    display_label_map = {
        "INCREASE": "偏多，可考虑补仓",
        "HOLD": "观望",
        "REDUCE": "偏空，可考虑减仓",
        "WAIT": "等待",
    }
    display_label = display_label_map.get(action, "观望")

    # 转换置信度为小写（兼容旧代码）
    aggressiveness_to_confidence = {
        "HIGH": "high",
        "MEDIUM": "medium",
        "LOW": "low",
    }
    confidence_band = aggressiveness_to_confidence.get(aggressiveness, "medium")

    # 检查信号冲突
    conflicting_signals = False
    if risk_result:
        components = risk_result.get("components", {})
        signal_disagreement = components.get("signal_disagreement", "")
        if signal_disagreement == "HIGH":
            conflicting_signals = True
        # 或者从 risk_flags 检查
        risk_flags = risk_result.get("risk_flags", [])
        if "signal_conflict" in risk_flags:
            conflicting_signals = True

    # 总分已废弃，返回0.0
    total_score = 0.0

    return action_cn, reason, display_label, confidence_band, conflicting_signals, total_score


def compute_daily_action_compat(
    last: Any,
    premium_pct: float | None = None,
    avg_premium_22d: float | None = None,
    premium_std_22d: float | None = None,
    premium_pctile_60: float | None = None,
    r2: float | None = None,
    slope: float | None = None,
    atr_pct: float | None = None,
    market_regime: dict | None = None,
    pct_drawdown_from_high: float | None = None,
    weight_pct: float | None = None,
) -> tuple[str, str, str, str, bool, float]:
    """
    向后兼容的 compute_daily_action 函数。

    使用新架构，但返回旧格式的元组。

    参数:
    - 与旧的 compute_daily_action() 相同

    返回:
    - (action, reason, display_label, confidence_band, conflicting_signals, total_score)
    """
    from .daily_action import compute_daily_action_v2

    # 准备历史状态序列（如果需要）
    # 注意：旧接口不提供历史，所以这里传 None
    history = None

    # 调用新架构
    decision = compute_daily_action_v2(
        last=last,
        premium_pctile_60=premium_pctile_60,
        r2=r2,
        slope=slope,
        atr_pct=atr_pct,
        market_regime=market_regime,
        history=history,
    )

    # 转换为旧格式
    return decision_to_legacy_format(decision)


def premium_deviation(
    current_premium: float | None,
    mean_22: float | None,
    std_22: float | None,
) -> float | None:
    """
    相对溢价偏离度：(当前溢价 - 22日均值) / 22日标准差。
    仅当 std_22 > 0 时有效；否则返回 None。
    
    此函数保留用于向后兼容，新代码不需要使用。
    """
    if current_premium is None or mean_22 is None or std_22 is None:
        return None
    if std_22 <= 0 or not math.isfinite(std_22):
        return None
    try:
        return (float(current_premium) - float(mean_22)) / float(std_22)
    except (TypeError, ValueError):
        return None
