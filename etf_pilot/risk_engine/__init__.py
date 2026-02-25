# -*- coding: utf-8 -*-
"""
风险引擎：基于 Signal Engine 的输出评估交易风险条件。

职责：
- 评估波动率制度风险
- 评估趋势不稳定性风险
- 评估信号分歧风险
- 评估快速状态转换风险
- 综合输出风险等级和风险标志

约束：
- ✅ 只能使用 Signal Engine 的输出
- ❌ 禁止使用价格指标（价格、收益率等）
- ❌ 禁止使用技术指标（RSI、MA、ATR 等）
- ❌ 禁止重新计算信号
- ❌ 禁止使用评分系统
"""
from .volatility_regime import volatility_regime_risk
from .trend_instability import trend_instability_risk
from .signal_disagreement import signal_disagreement_risk
from .rapid_transitions import rapid_transitions_risk
from .assessment import (
    evaluate_risk,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_HIGH,
    RISK_FLAG_HIGH_VOLATILITY,
    RISK_FLAG_TREND_UNKNOWN,
    RISK_FLAG_SIGNAL_CONFLICT,
    RISK_FLAG_RAPID_TRANSITIONS,
)

# 向后兼容：保留旧的函数和常量（如果存在）
try:
    from .drawdown import drawdown_15pct_value
    from .drawdown_risk import drawdown_from_high, drawdown_risk_level
    from .concentration_risk import concentration_risk_level
    __all__ = [
        # 新的风险评估函数
        "evaluate_risk",
        "volatility_regime_risk",
        "trend_instability_risk",
        "signal_disagreement_risk",
        "rapid_transitions_risk",
        # 风险等级常量
        "RISK_LOW",
        "RISK_MEDIUM",
        "RISK_HIGH",
        # 风险标志常量
        "RISK_FLAG_HIGH_VOLATILITY",
        "RISK_FLAG_TREND_UNKNOWN",
        "RISK_FLAG_SIGNAL_CONFLICT",
        "RISK_FLAG_RAPID_TRANSITIONS",
        # 向后兼容：旧函数
        "drawdown_15pct_value",
        "drawdown_from_high",
        "drawdown_risk_level",
        "concentration_risk_level",
    ]
except ImportError:
    __all__ = [
        # 新的风险评估函数
        "evaluate_risk",
        "volatility_regime_risk",
        "trend_instability_risk",
        "signal_disagreement_risk",
        "rapid_transitions_risk",
        # 风险等级常量
        "RISK_LOW",
        "RISK_MEDIUM",
        "RISK_HIGH",
        # 风险标志常量
        "RISK_FLAG_HIGH_VOLATILITY",
        "RISK_FLAG_TREND_UNKNOWN",
        "RISK_FLAG_SIGNAL_CONFLICT",
        "RISK_FLAG_RAPID_TRANSITIONS",
    ]
