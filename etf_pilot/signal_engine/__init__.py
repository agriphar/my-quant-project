# -*- coding: utf-8 -*-
"""
Signal Engine：仅产出指标与状态，不产出买卖建议。

职责：
- 计算技术指标（RSI、ATR、趋势回归等）
- 将指标转换为状态标签
- 描述市场正在做什么，而非投资者应该做什么

禁止：
- ❌ 输出买卖建议
- ❌ 计算聚合评分
- ❌ 包含风险评估
- ❌ 包含置信度逻辑
"""
from .indicators import (
    rsi,
    bollinger,
    atr,
    pct_from_1y_high_low,
    bias_pct,
)
from .states import (
    # 状态计算函数
    get_signal_states,
    trend_state,
    momentum_state,
    valuation_state,
    volatility_state,
    # 状态常量 - Trend（新）
    TREND_UP,
    TREND_DOWN,
    TREND_SIDEWAYS,
    TREND_UNKNOWN,
    # 状态常量 - Momentum（新）
    MOMENTUM_ACCELERATING,
    MOMENTUM_WEAKENING,
    MOMENTUM_NEUTRAL,
    MOMENTUM_UNKNOWN,
    # 状态常量 - Valuation（新）
    VALUATION_CHEAP,
    VALUATION_FAIR,
    VALUATION_EXPENSIVE,
    VALUATION_UNKNOWN,
    # 状态常量 - Volatility（新）
    VOLATILITY_LOW,
    VOLATILITY_NORMAL,
    VOLATILITY_HIGH,
    VOLATILITY_UNKNOWN,
    # 向后兼容：旧状态常量
    MOMENTUM_OVERSOLD,
    MOMENTUM_OVERBOUGHT,
    TREND_STRONG_UP,
    TREND_WEAK_UP,
    VALUATION_FAIR_LOW,
    VALUATION_FAIR_HIGH,
    VOLATILITY_MEDIUM,
)

# 向后兼容：保留旧的 signals 模块（如果存在）
try:
    from .signals import (
        compute_grid_signal,
        compute_deviation,
        check_chase_high,
        compute_signal,
        compute_addon_suggestion,
    )
    __all__ = [
        # 指标计算
        "rsi",
        "bollinger",
        "atr",
        "pct_from_1y_high_low",
        "bias_pct",
        # 状态计算
        "get_signal_states",
        "trend_state",
        "momentum_state",
        "valuation_state",
        "volatility_state",
        # 状态常量 - Trend
        "TREND_UP",
        "TREND_DOWN",
        "TREND_SIDEWAYS",
        "TREND_UNKNOWN",
        # 状态常量 - Momentum
        "MOMENTUM_ACCELERATING",
        "MOMENTUM_WEAKENING",
        "MOMENTUM_NEUTRAL",
        "MOMENTUM_UNKNOWN",
        # 状态常量 - Valuation
        "VALUATION_CHEAP",
        "VALUATION_FAIR",
        "VALUATION_EXPENSIVE",
        "VALUATION_UNKNOWN",
        # 状态常量 - Volatility
        "VOLATILITY_LOW",
        "VOLATILITY_NORMAL",
        "VOLATILITY_HIGH",
        "VOLATILITY_UNKNOWN",
        # 向后兼容：旧状态常量
        "MOMENTUM_OVERSOLD",
        "MOMENTUM_OVERBOUGHT",
        "TREND_STRONG_UP",
        "TREND_WEAK_UP",
        "VALUATION_FAIR_LOW",
        "VALUATION_FAIR_HIGH",
        "VOLATILITY_MEDIUM",
        # 向后兼容：旧的 signals 模块
        "compute_grid_signal",
        "compute_deviation",
        "check_chase_high",
        "compute_signal",
        "compute_addon_suggestion",
    ]
except ImportError:
    # 如果 signals 模块不存在，只导出核心功能
    __all__ = [
        # 指标计算
        "rsi",
        "bollinger",
        "atr",
        "pct_from_1y_high_low",
        "bias_pct",
        # 状态计算
        "get_signal_states",
        "trend_state",
        "momentum_state",
        "valuation_state",
        "volatility_state",
        # 状态常量 - Trend
        "TREND_UP",
        "TREND_DOWN",
        "TREND_SIDEWAYS",
        "TREND_UNKNOWN",
        # 状态常量 - Momentum
        "MOMENTUM_ACCELERATING",
        "MOMENTUM_WEAKENING",
        "MOMENTUM_NEUTRAL",
        "MOMENTUM_UNKNOWN",
        # 状态常量 - Valuation
        "VALUATION_CHEAP",
        "VALUATION_FAIR",
        "VALUATION_EXPENSIVE",
        "VALUATION_UNKNOWN",
        # 状态常量 - Volatility
        "VOLATILITY_LOW",
        "VOLATILITY_NORMAL",
        "VOLATILITY_HIGH",
        "VOLATILITY_UNKNOWN",
        # 向后兼容：旧状态常量
        "MOMENTUM_OVERSOLD",
        "MOMENTUM_OVERBOUGHT",
        "TREND_STRONG_UP",
        "TREND_WEAK_UP",
        "VALUATION_FAIR_LOW",
        "VALUATION_FAIR_HIGH",
        "VOLATILITY_MEDIUM",
    ]
