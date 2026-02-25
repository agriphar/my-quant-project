# -*- coding: utf-8 -*-
"""
置信度引擎汇总：综合四个置信度维度，输出单一置信度等级和置信度原因。

只能使用 Signal Engine 和 Risk Engine 的输出，禁止使用原始数据。
"""
from __future__ import annotations

from typing import Any, Sequence

from .signal_agreement import signal_agreement_confidence
from .regime_stability import regime_stability_confidence
from .valuation_trend_conflict import valuation_trend_conflict_confidence

# Risk Engine 的风险等级常量
RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"

CONFIDENCE_LOW = "LOW"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_HIGH = "HIGH"

# 置信度原因常量
REASON_HIGH_SIGNAL_AGREEMENT = "high_signal_agreement"
REASON_LOW_SIGNAL_AGREEMENT = "low_signal_agreement"
REASON_STABLE_REGIME = "stable_regime"
REASON_UNSTABLE_REGIME = "unstable_regime"
REASON_PERSISTENT_SIGNALS = "persistent_signals"
REASON_VOLATILE_SIGNALS = "volatile_signals"
REASON_VALUATION_TREND_ALIGNED = "valuation_trend_aligned"
REASON_VALUATION_TREND_CONFLICT = "valuation_trend_conflict"


def _confidence_ordinal(level: str) -> int:
    """将置信度等级转换为序数（用于聚合计算）。"""
    if level == CONFIDENCE_LOW:
        return 2
    elif level == CONFIDENCE_MEDIUM:
        return 1
    else:
        return 0


def _rapid_transitions_risk_to_confidence(rapid_transitions_risk: str | None) -> str:
    """
    将 Risk Engine 的 rapid_transitions 风险等级转换为置信度等级。

    参数:
    - rapid_transitions_risk: Risk Engine 输出的 rapid_transitions 风险等级
        "LOW" | "MEDIUM" | "HIGH"

    返回:
    - "HIGH": 高置信度（状态稳定，LOW 风险）
    - "MEDIUM": 中等置信度（状态中等稳定，MEDIUM 风险）
    - "LOW": 低置信度（状态不稳定，HIGH 风险）

    逻辑:
    - LOW 风险（状态稳定）→ HIGH 置信度（状态持续）
    - MEDIUM 风险（状态中等稳定）→ MEDIUM 置信度（状态中等持续）
    - HIGH 风险（状态不稳定）→ LOW 置信度（状态不持续）
    """
    if not rapid_transitions_risk:
        return CONFIDENCE_MEDIUM

    rapid_transitions_risk = rapid_transitions_risk.upper()

    if rapid_transitions_risk == RISK_LOW:
        # 状态稳定，高置信度
        return CONFIDENCE_HIGH
    elif rapid_transitions_risk == RISK_HIGH:
        # 状态不稳定，低置信度
        return CONFIDENCE_LOW
    else:
        # 状态中等稳定，中等置信度
        return CONFIDENCE_MEDIUM


def _generate_confidence_reasons(
    agreement_conf: str,
    regime_conf: str,
    persistence_conf: str,
    conflict_conf: str,
) -> list[str]:
    """
    生成置信度原因列表，标识具体的置信度来源。

    参数:
    - agreement_conf: 信号一致性置信度
    - regime_conf: 制度稳定性置信度
    - persistence_conf: 信号持续性置信度
    - conflict_conf: 估值趋势冲突置信度

    返回:
    - 置信度原因列表
    """
    reasons = []

    # 信号一致性原因
    if agreement_conf == CONFIDENCE_HIGH:
        reasons.append(REASON_HIGH_SIGNAL_AGREEMENT)
    elif agreement_conf == CONFIDENCE_LOW:
        reasons.append(REASON_LOW_SIGNAL_AGREEMENT)

    # 制度稳定性原因
    if regime_conf == CONFIDENCE_HIGH:
        reasons.append(REASON_STABLE_REGIME)
    elif regime_conf == CONFIDENCE_LOW:
        reasons.append(REASON_UNSTABLE_REGIME)

    # 信号持续性原因
    if persistence_conf == CONFIDENCE_HIGH:
        reasons.append(REASON_PERSISTENT_SIGNALS)
    elif persistence_conf == CONFIDENCE_LOW:
        reasons.append(REASON_VOLATILE_SIGNALS)

    # 估值趋势冲突原因
    if conflict_conf == CONFIDENCE_HIGH:
        reasons.append(REASON_VALUATION_TREND_ALIGNED)
    elif conflict_conf == CONFIDENCE_LOW:
        reasons.append(REASON_VALUATION_TREND_CONFLICT)

    return reasons


def calculate_confidence(
    signal_states: dict[str, str] | None = None,
    risk_result: dict[str, Any] | None = None,
    market_regime: dict[str, Any] | None = None,
    history: Sequence[dict[str, str]] | None = None,
    lookback_days: int = 5,
) -> dict[str, Any]:
    """
    计算置信度等级和置信度原因，独立于评分系统和决策逻辑。

    参数:
    - signal_states: Signal Engine 输出的当前状态字典
        {
            "trend": "UP" | "DOWN" | "SIDEWAYS" | "UNKNOWN",
            "momentum": "ACCELERATING" | "WEAKENING" | "NEUTRAL" | "UNKNOWN",
            "valuation": "CHEAP" | "FAIR" | "EXPENSIVE" | "UNKNOWN",
            "volatility": "LOW" | "NORMAL" | "HIGH" | "UNKNOWN"
        }
    - risk_result: Risk Engine 输出的风险结果（必需，用于获取 signal_disagreement 和 rapid_transitions）
        {
            "risk_level": "LOW" | "MEDIUM" | "HIGH",
            "components": {
                "signal_disagreement": "LOW" | "MEDIUM" | "HIGH",
                "rapid_transitions": "LOW" | "MEDIUM" | "HIGH",
                ...
            }
        }
    - market_regime: 市场制度字典（可选）
        {
            "confidence": "high" | "medium" | "low",
            "risk_regime": "risk_on" | "risk_off"
        }
    - history: Signal Engine 的历史状态序列（已废弃，不再使用）
    - lookback_days: 历史窗口天数（已废弃，不再使用）

    返回:
    {
        "confidence": "LOW" | "MEDIUM" | "HIGH",
        "confidence_reason": [
            "high_signal_agreement" | "low_signal_agreement" |
            "stable_regime" | "unstable_regime" |
            "persistent_signals" | "volatile_signals" |
            "valuation_trend_aligned" | "valuation_trend_conflict"
        ]
    }

    聚合规则:
    1. 所有维度均为 HIGH → 整体置信度为 HIGH
    2. 任一维度为 LOW → 降级
       - 若只有一个 LOW 且其他都是 HIGH → MEDIUM（轻微降级）
       - 否则 → LOW（严重降级）
    3. 最差维度为 MEDIUM → 整体置信度为 MEDIUM

    重要:
    - 置信度不能直接与信号方向相关
    - 置信度评估的是信号的可靠性，而不是信号的方向（看多或看空）
    - 信号持续性置信度现在使用 Risk Engine 的 rapid_transitions 输出，不再重新计算
    """
    if not signal_states:
        # 如果没有信号状态，返回中等置信度
        return {
            "confidence": CONFIDENCE_MEDIUM,
            "confidence_reason": [],
        }

    # 1. 信号一致性置信度（使用 Risk Engine 的输出）
    signal_disagreement = None
    if risk_result and "components" in risk_result:
        signal_disagreement = risk_result["components"].get("signal_disagreement")
    agreement_conf = signal_agreement_confidence(signal_disagreement)

    # 2. 制度稳定性置信度（使用外部输入）
    regime_conf = regime_stability_confidence(market_regime)

    # 3. 信号持续性置信度（使用 Risk Engine 的 rapid_transitions 输出）
    # 修复：不再重新计算，而是使用 Risk Engine 的输出
    rapid_transitions_risk = None
    if risk_result and "components" in risk_result:
        rapid_transitions_risk = risk_result["components"].get("rapid_transitions")
    persistence_conf = _rapid_transitions_risk_to_confidence(rapid_transitions_risk)

    # 4. 估值趋势冲突置信度（使用 Signal Engine 的输出）
    trend_state = signal_states.get("trend")
    valuation_state = signal_states.get("valuation")
    conflict_conf = valuation_trend_conflict_confidence(trend_state, valuation_state)

    # 聚合置信度等级
    confidences = [agreement_conf, regime_conf, persistence_conf, conflict_conf]
    ordinals = [_confidence_ordinal(c) for c in confidences]
    max_ordinal = max(ordinals)
    low_count = sum(1 for o in ordinals if o == 2)
    high_count = sum(1 for o in ordinals if o == 0)

    # 聚合规则（最保守策略）
    if max_ordinal == 0:
        # 所有维度都是 HIGH
        confidence_level = CONFIDENCE_HIGH
    elif max_ordinal == 2:
        # 存在 LOW 维度
        if low_count == 1 and high_count == 3:
            # 只有一个 LOW，其他都是 HIGH，轻微降级为 MEDIUM
            confidence_level = CONFIDENCE_MEDIUM
        else:
            # 多个 LOW 或混合情况，严重降级为 LOW
            confidence_level = CONFIDENCE_LOW
    else:
        # max_ordinal == 1，最差维度为 MEDIUM
        confidence_level = CONFIDENCE_MEDIUM

    # 生成置信度原因
    confidence_reasons = _generate_confidence_reasons(
        agreement_conf, regime_conf, persistence_conf, conflict_conf
    )

    return {
        "confidence": confidence_level,
        "confidence_reason": confidence_reasons,
    }
