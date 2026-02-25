# -*- coding: utf-8 -*-
"""
置信度引擎：基于 Signal Engine 和 Risk Engine 的输出评估信号可靠性。

职责：
- 评估信号一致性水平
- 评估制度稳定性
- 评估信号状态的持续性
- 评估估值与趋势的冲突
- 综合输出置信度等级和置信度原因

约束：
- ✅ 只能使用 Signal Engine 的输出
- ✅ 只能使用 Risk Engine 的输出
- ❌ 禁止使用价格数据（价格、收益率等）
- ❌ 禁止使用技术指标（RSI、MA、ATR 等）
- ❌ 禁止重用评分系统
- ❌ 禁止包含决策逻辑

重要：置信度不能直接与信号方向相关。
"""
from .signal_agreement import signal_agreement_confidence
from .regime_stability import regime_stability_confidence
from .valuation_trend_conflict import valuation_trend_conflict_confidence

# 向后兼容：signal_persistence_confidence 已废弃，现在使用 Risk Engine 的输出
try:
    from .signal_persistence import signal_persistence_confidence
except ImportError:
    signal_persistence_confidence = None
from .assessment import (
    calculate_confidence,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_HIGH,
    REASON_HIGH_SIGNAL_AGREEMENT,
    REASON_LOW_SIGNAL_AGREEMENT,
    REASON_STABLE_REGIME,
    REASON_UNSTABLE_REGIME,
    REASON_PERSISTENT_SIGNALS,
    REASON_VOLATILE_SIGNALS,
    REASON_VALUATION_TREND_ALIGNED,
    REASON_VALUATION_TREND_CONFLICT,
)

__all__ = [
    # 置信度计算函数
    "calculate_confidence",
    # 各维度置信度评估函数
    "signal_agreement_confidence",
    "regime_stability_confidence",
    "valuation_trend_conflict_confidence",
    # 向后兼容：signal_persistence_confidence 已废弃
    "signal_persistence_confidence",
    # 置信度等级常量
    "CONFIDENCE_LOW",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_HIGH",
    # 置信度原因常量
    "REASON_HIGH_SIGNAL_AGREEMENT",
    "REASON_LOW_SIGNAL_AGREEMENT",
    "REASON_STABLE_REGIME",
    "REASON_UNSTABLE_REGIME",
    "REASON_PERSISTENT_SIGNALS",
    "REASON_VOLATILE_SIGNALS",
    "REASON_VALUATION_TREND_ALIGNED",
    "REASON_VALUATION_TREND_CONFLICT",
]
