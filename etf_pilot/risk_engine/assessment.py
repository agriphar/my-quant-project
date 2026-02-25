# -*- coding: utf-8 -*-
"""
风险引擎汇总：综合四个风险维度，输出单一风险等级和风险标志。

只能使用 Signal Engine 的输出，禁止使用原始数据。
"""
from __future__ import annotations

from typing import Any, Sequence

from .volatility_regime import volatility_regime_risk
from .trend_instability import trend_instability_risk
from .signal_disagreement import signal_disagreement_risk
from .rapid_transitions import rapid_transitions_risk

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"

# 风险标志
RISK_FLAG_HIGH_VOLATILITY = "high_volatility"
RISK_FLAG_TREND_UNKNOWN = "trend_unknown"
RISK_FLAG_SIGNAL_CONFLICT = "signal_conflict"
RISK_FLAG_RAPID_TRANSITIONS = "rapid_transitions"


def _ordinal(level: str) -> int:
    """将风险等级转换为序数（用于聚合计算）。"""
    if level == RISK_LOW:
        return 0
    elif level == RISK_MEDIUM:
        return 1
    else:
        return 2


def _generate_risk_flags(
    volatility_risk: str,
    trend_risk: str,
    disagreement_risk: str,
    transitions_risk: str,
) -> list[str]:
    """
    生成风险标志列表，标识具体的风险来源。

    参数:
    - volatility_risk: 波动率风险等级
    - trend_risk: 趋势不稳定性风险等级
    - disagreement_risk: 信号分歧风险等级
    - transitions_risk: 快速状态转换风险等级

    返回:
    - 风险标志列表
    """
    flags = []

    if volatility_risk == RISK_HIGH:
        flags.append(RISK_FLAG_HIGH_VOLATILITY)

    if trend_risk == RISK_HIGH:
        flags.append(RISK_FLAG_TREND_UNKNOWN)

    if disagreement_risk == RISK_HIGH:
        flags.append(RISK_FLAG_SIGNAL_CONFLICT)

    if transitions_risk == RISK_HIGH:
        flags.append(RISK_FLAG_RAPID_TRANSITIONS)

    return flags


def evaluate_risk(
    signal_states: dict[str, str] | None,
    history: Sequence[dict[str, str]] | None = None,
    lookback_days: int = 5,
) -> dict[str, Any]:
    """
    综合四个风险维度，输出单一风险等级、风险标志和明细。

    参数:
    - signal_states: Signal Engine 输出的当前状态字典
        {
            "trend": "UP" | "DOWN" | "SIDEWAYS" | "UNKNOWN",
            "momentum": "ACCELERATING" | "WEAKENING" | "NEUTRAL" | "UNKNOWN",
            "valuation": "CHEAP" | "FAIR" | "EXPENSIVE" | "UNKNOWN",
            "volatility": "LOW" | "NORMAL" | "HIGH" | "UNKNOWN"
        }
    - history: Signal Engine 的历史状态序列（可选，用于评估快速状态转换）
    - lookback_days: 历史窗口天数（默认 5 天）

    返回:
    {
        "risk_level": "LOW" | "MEDIUM" | "HIGH",
        "risk_flags": [
            "high_volatility" | "trend_unknown" | 
            "signal_conflict" | "rapid_transitions"
        ],
        "components": {
            "volatility_regime": "LOW" | "MEDIUM" | "HIGH",
            "trend_instability": "LOW" | "MEDIUM" | "HIGH",
            "signal_disagreement": "LOW" | "MEDIUM" | "HIGH",
            "rapid_transitions": "LOW" | "MEDIUM" | "HIGH"
        }
    }

    聚合规则:
    1. 任一维度为 HIGH → 整体风险为 HIGH
    2. 两个或以上维度为 MEDIUM → 整体风险为 MEDIUM
    3. 所有维度均为 LOW → 整体风险为 LOW
    4. 其他情况 → 整体风险为 MEDIUM
    """
    if not signal_states:
        # 如果没有信号状态，返回中等风险
        return {
            "risk_level": RISK_MEDIUM,
            "risk_flags": [],
            "components": {
                "volatility_regime": RISK_MEDIUM,
                "trend_instability": RISK_MEDIUM,
                "signal_disagreement": RISK_MEDIUM,
                "rapid_transitions": RISK_MEDIUM,
            },
        }

    # 1. 波动率制度风险
    volatility_state = signal_states.get("volatility")
    vol_risk = volatility_regime_risk(volatility_state)

    # 2. 趋势不稳定性风险
    trend_state = signal_states.get("trend")
    trend_risk = trend_instability_risk(trend_state)

    # 3. 信号分歧风险
    disagreement_risk = signal_disagreement_risk(signal_states)

    # 4. 快速状态转换风险
    transitions_risk = rapid_transitions_risk(
        current_states=signal_states,
        history=history,
        lookback_days=lookback_days,
    )

    # 聚合风险等级
    components = [vol_risk, trend_risk, disagreement_risk, transitions_risk]
    ordinals = [_ordinal(c) for c in components]
    max_ordinal = max(ordinals)
    medium_count = sum(1 for o in ordinals if o == 1)
    high_count = sum(1 for o in ordinals if o == 2)

    # 聚合规则
    if max_ordinal >= 2:
        # 任一维度为 HIGH
        risk_level = RISK_HIGH
    elif medium_count >= 2 or max_ordinal == 1:
        # 两个或以上维度为 MEDIUM，或最差维度为 MEDIUM
        risk_level = RISK_MEDIUM
    else:
        # 所有维度均为 LOW
        risk_level = RISK_LOW

    # 生成风险标志
    risk_flags = _generate_risk_flags(
        vol_risk, trend_risk, disagreement_risk, transitions_risk
    )

    return {
        "risk_level": risk_level,
        "risk_flags": risk_flags,
        "components": {
            "volatility_regime": vol_risk,
            "trend_instability": trend_risk,
            "signal_disagreement": disagreement_risk,
            "rapid_transitions": transitions_risk,
        },
    }
