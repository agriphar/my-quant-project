# -*- coding: utf-8 -*-
"""
Decision Engine：将系统状态转换为投资组合操作。

职责：
- Layer 1: Signal Direction（信号方向）
- Layer 2: Risk Constraint（风险约束）
- Layer 3: Confidence Adjustment（置信度调整）
- 综合输出投资组合操作

约束：
- ✅ 只能使用 Signal Engine 的输出
- ✅ 只能使用 Risk Engine 的输出
- ✅ 只能使用 Confidence Engine 的输出
- ❌ 禁止指标计算
- ❌ 禁止评分聚合
- ❌ 禁止信号重新计算
"""
from .decision import make_decision
from .signal_direction import (
    determine_signal_direction,
    DIRECTION_BULLISH,
    DIRECTION_BEARISH,
    DIRECTION_NEUTRAL,
    DIRECTION_UNKNOWN,
    ACTION_INCREASE,
    ACTION_HOLD,
    ACTION_REDUCE,
    ACTION_WAIT,
)
from .risk_constraint import apply_risk_constraint
from .confidence_adjustment import (
    apply_confidence_adjustment,
    AGGRESSIVENESS_LOW,
    AGGRESSIVENESS_MEDIUM,
    AGGRESSIVENESS_HIGH,
)

# 向后兼容：保留必要的旧函数（通过 compat 模块）
from .compat import premium_deviation
from .daily_action import (
    compute_daily_action,  # ⚠️ 已废弃，但保留以便向后兼容
    compute_action_frequency,
    compute_signal_accuracy_30d,
)

__all__ = [
    # 新的决策函数
    "make_decision",
    # Layer 1: Signal Direction
    "determine_signal_direction",
    "DIRECTION_BULLISH",
    "DIRECTION_BEARISH",
    "DIRECTION_NEUTRAL",
    "DIRECTION_UNKNOWN",
    "ACTION_INCREASE",
    "ACTION_HOLD",
    "ACTION_REDUCE",
    "ACTION_WAIT",
    # Layer 2: Risk Constraint
    "apply_risk_constraint",
    # Layer 3: Confidence Adjustment
    "apply_confidence_adjustment",
    "AGGRESSIVENESS_LOW",
    "AGGRESSIVENESS_MEDIUM",
    "AGGRESSIVENESS_HIGH",
    # 向后兼容：保留的函数
    "premium_deviation",
    "compute_daily_action",  # ⚠️ 已废弃
    "compute_action_frequency",
    "compute_signal_accuracy_30d",
]
