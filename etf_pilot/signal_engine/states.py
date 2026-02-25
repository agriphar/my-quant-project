# -*- coding: utf-8 -*-
"""
Signal Engine — 仅输出市场状态，不输出买卖建议。

所有函数仅返回状态标签，禁止返回「买入」「卖出」「补仓」「减仓」等建议文案。
禁止计算评分、风险评估或置信度。
"""
from __future__ import annotations

import math
from typing import Any

# ============================================================================
# 状态常量定义
# ============================================================================

# Trend State（趋势状态）
TREND_UP = "UP"
TREND_DOWN = "DOWN"
TREND_SIDEWAYS = "SIDEWAYS"
TREND_UNKNOWN = "UNKNOWN"

# Momentum State（动量状态）
MOMENTUM_ACCELERATING = "ACCELERATING"
MOMENTUM_WEAKENING = "WEAKENING"
MOMENTUM_NEUTRAL = "NEUTRAL"
MOMENTUM_UNKNOWN = "UNKNOWN"

# Valuation State（估值状态）
VALUATION_CHEAP = "CHEAP"
VALUATION_FAIR = "FAIR"
VALUATION_EXPENSIVE = "EXPENSIVE"
VALUATION_UNKNOWN = "UNKNOWN"

# Volatility State（波动率状态）
VOLATILITY_LOW = "LOW"
VOLATILITY_NORMAL = "NORMAL"
VOLATILITY_HIGH = "HIGH"
VOLATILITY_UNKNOWN = "UNKNOWN"

# ============================================================================
# 阈值常量
# ============================================================================

# Trend State 阈值
R2_TREND_THRESHOLD = 0.4  # R² >= 0.4 视为有明确趋势
SLOPE_NEAR_ZERO_THRESHOLD = 0.0001  # 斜率接近 0 的阈值

# Momentum State 阈值（基于 RSI）
RSI_OVERSOLD = 30  # RSI < 30 视为超卖（可能反弹加速）
RSI_OVERBOUGHT = 70  # RSI > 70 视为超买（可能加速上涨）
RSI_WEAK_LOW = 45  # RSI <= 45 视为动能减弱（偏弱）
RSI_WEAK_HIGH = 55  # RSI >= 55 视为动能减弱（偏强）
RSI_NEUTRAL_LOW = 45  # 中性区间下界
RSI_NEUTRAL_HIGH = 55  # 中性区间上界

# Valuation State 阈值（基于溢价率 60 日分位数）
VALUATION_CHEAP_THRESHOLD = 25  # 分位数 <= 25 视为便宜
VALUATION_EXPENSIVE_THRESHOLD = 75  # 分位数 > 75 视为昂贵

# Volatility State 阈值（基于 ATR%）
VOLATILITY_LOW_THRESHOLD = 1.0  # ATR% <= 1.0 视为低波动
VOLATILITY_HIGH_THRESHOLD = 3.0  # ATR% >= 3.0 视为高波动

# ============================================================================
# 状态计算函数
# ============================================================================


def trend_state(r2: float | None, slope: float | None) -> str:
    """
    计算趋势状态：描述价格的中长期方向性运动。

    参数:
    - r2: 线性回归的 R² 值（0-1），表示趋势的明确程度
    - slope: 线性回归的斜率，表示每日价格变动（元/日）

    返回:
    - "UP": 上升趋势（R² >= 0.4 且 slope > 0）
    - "DOWN": 下降趋势（R² >= 0.4 且 slope < 0）
    - "SIDEWAYS": 横盘震荡（R² < 0.4 或 slope 接近 0）
    - "UNKNOWN": 数据不足或无法计算

    规则:
    - R² >= 0.4 且 slope > SLOPE_NEAR_ZERO_THRESHOLD → UP
    - R² >= 0.4 且 slope < -SLOPE_NEAR_ZERO_THRESHOLD → DOWN
    - 其他情况 → SIDEWAYS
    - 输入无效 → UNKNOWN
    """
    # 检查输入有效性
    if r2 is None or slope is None:
        return TREND_UNKNOWN
    if not math.isfinite(r2) or not math.isfinite(slope):
        return TREND_UNKNOWN

    r2_val = float(r2)
    slope_val = float(slope)

    # 检查是否有明确趋势（R² >= 0.4）
    if r2_val >= R2_TREND_THRESHOLD:
        # 有明确趋势，根据斜率判断方向
        if slope_val > SLOPE_NEAR_ZERO_THRESHOLD:
            return TREND_UP
        elif slope_val < -SLOPE_NEAR_ZERO_THRESHOLD:
            return TREND_DOWN
        else:
            # 斜率接近 0，视为横盘
            return TREND_SIDEWAYS
    else:
        # R² < 0.4，趋势不明确，视为横盘
        return TREND_SIDEWAYS


def momentum_state(rsi: float | None) -> str:
    """
    计算动量状态：描述价格短期动能的强弱和方向。

    参数:
    - rsi: RSI 值（0-100）

    返回:
    - "ACCELERATING": 加速（RSI < 30 超卖或 RSI > 70 超买，可能加速）
    - "WEAKENING": 减弱（30 <= RSI <= 45 或 55 <= RSI <= 70，动能减弱）
    - "NEUTRAL": 中性（45 < RSI < 55）
    - "UNKNOWN": 数据不足或无法计算

    规则:
    - RSI < 30 → ACCELERATING（超卖，可能反弹加速）
    - RSI > 70 → ACCELERATING（超买，可能加速上涨）
    - 30 <= RSI <= 45 → WEAKENING（动能减弱，偏弱）
    - 55 <= RSI <= 70 → WEAKENING（动能减弱，偏强）
    - 45 < RSI < 55 → NEUTRAL（中性）
    - 输入无效 → UNKNOWN
    """
    # 检查输入有效性
    if rsi is None:
        return MOMENTUM_UNKNOWN
    if not math.isfinite(rsi):
        return MOMENTUM_UNKNOWN

    rsi_val = float(rsi)

    # 检查边界值
    if rsi_val < RSI_OVERSOLD:
        # 超卖区域，可能反弹加速
        return MOMENTUM_ACCELERATING
    elif rsi_val > RSI_OVERBOUGHT:
        # 超买区域，可能加速上涨
        return MOMENTUM_ACCELERATING
    elif RSI_OVERSOLD <= rsi_val <= RSI_WEAK_LOW:
        # 偏弱区域，动能减弱
        return MOMENTUM_WEAKENING
    elif RSI_WEAK_HIGH <= rsi_val <= RSI_OVERBOUGHT:
        # 偏强区域，动能减弱
        return MOMENTUM_WEAKENING
    elif RSI_NEUTRAL_LOW < rsi_val < RSI_NEUTRAL_HIGH:
        # 中性区域
        return MOMENTUM_NEUTRAL
    else:
        # 理论上不应该到达这里，但为了安全返回中性
        return MOMENTUM_NEUTRAL


def valuation_state(premium_pctile_60: float | None) -> str:
    """
    计算估值状态：描述当前价格相对于历史水平的估值位置。

    参数:
    - premium_pctile_60: 溢价率在 60 日历史中的分位数（0-100）

    返回:
    - "CHEAP": 便宜（分位数 <= 25）
    - "FAIR": 合理（25 < 分位数 <= 75）
    - "EXPENSIVE": 昂贵（分位数 > 75）
    - "UNKNOWN": 数据不足或无法计算

    规则:
    - 分位数 <= 25 → CHEAP
    - 25 < 分位数 <= 75 → FAIR
    - 分位数 > 75 → EXPENSIVE
    - 输入无效 → UNKNOWN
    """
    # 检查输入有效性
    if premium_pctile_60 is None:
        return VALUATION_UNKNOWN
    if not math.isfinite(premium_pctile_60):
        return VALUATION_UNKNOWN

    pctile = float(premium_pctile_60)

    # 检查分位数范围
    if pctile <= VALUATION_CHEAP_THRESHOLD:
        return VALUATION_CHEAP
    elif pctile <= VALUATION_EXPENSIVE_THRESHOLD:
        return VALUATION_FAIR
    else:
        return VALUATION_EXPENSIVE


def volatility_state(atr_pct: float | None) -> str:
    """
    计算波动率状态：描述价格波动的剧烈程度。

    参数:
    - atr_pct: ATR / 收盘价 * 100

    返回:
    - "LOW": 低波动（ATR% <= 1.0）
    - "NORMAL": 正常波动（1.0 < ATR% < 3.0）
    - "HIGH": 高波动（ATR% >= 3.0）
    - "UNKNOWN": 数据不足或无法计算

    规则:
    - ATR% <= 1.0 → LOW
    - 1.0 < ATR% < 3.0 → NORMAL
    - ATR% >= 3.0 → HIGH
    - 输入无效或负数 → UNKNOWN
    """
    # 检查输入有效性
    if atr_pct is None:
        return VOLATILITY_UNKNOWN
    if not math.isfinite(atr_pct) or atr_pct < 0:
        return VOLATILITY_UNKNOWN

    atr_val = float(atr_pct)

    # 检查波动率范围
    if atr_val <= VOLATILITY_LOW_THRESHOLD:
        return VOLATILITY_LOW
    elif atr_val < VOLATILITY_HIGH_THRESHOLD:
        return VOLATILITY_NORMAL
    else:
        return VOLATILITY_HIGH


# ============================================================================
# 向后兼容：旧状态常量（保持原始字符串值）
# ============================================================================

# 注意：这些旧状态常量保持原始字符串值以保持向后兼容性
# 新代码应使用新的状态值（TREND_UP, MOMENTUM_ACCELERATING 等）
# 这些常量将在后续重构中逐步移除

# Momentum 旧状态（保持原始字符串值）
MOMENTUM_OVERSOLD = "oversold"  # 旧值，新代码应使用 MOMENTUM_ACCELERATING
MOMENTUM_OVERBOUGHT = "overbought"  # 旧值，新代码应使用 MOMENTUM_ACCELERATING

# Trend 旧状态（保持原始字符串值）
TREND_STRONG_UP = "strong_up"  # 旧值，新代码应使用 TREND_UP
TREND_WEAK_UP = "weak_up"  # 旧值，新代码应使用 TREND_UP

# Valuation 旧状态（保持原始字符串值）
VALUATION_FAIR_LOW = "fair_low"  # 旧值，新代码应使用 VALUATION_FAIR
VALUATION_FAIR_HIGH = "fair_high"  # 旧值，新代码应使用 VALUATION_FAIR

# Volatility 旧状态（保持原始字符串值）
VOLATILITY_MEDIUM = "medium"  # 旧值，新代码应使用 VOLATILITY_NORMAL


# ============================================================================
# 统一接口：获取所有信号状态
# ============================================================================


def get_signal_states(
    last_row: Any,
    r2: float | None = None,
    slope: float | None = None,
    premium_pctile_60: float | None = None,
    atr_pct: float | None = None,
) -> dict[str, str]:
    """
    汇总各因子状态，仅返回状态字典，不包含任何买卖建议、评分、风险评估或置信度。

    参数:
    - last_row: 最后一行数据（Series 或 dict），用于提取 RSI 和 ATR
    - r2: 线性回归的 R² 值（可选，如果未提供则从 last_row 计算）
    - slope: 线性回归的斜率（可选）
    - premium_pctile_60: 溢价率 60 日分位数（可选）
    - atr_pct: ATR 百分比（可选，如果未提供则从 last_row 计算）

    返回:
    {
        "trend": "UP" | "DOWN" | "SIDEWAYS" | "UNKNOWN",
        "momentum": "ACCELERATING" | "WEAKENING" | "NEUTRAL" | "UNKNOWN",
        "valuation": "CHEAP" | "FAIR" | "EXPENSIVE" | "UNKNOWN",
        "volatility": "LOW" | "NORMAL" | "HIGH" | "UNKNOWN"
    }

    注意:
    - 此函数仅描述市场状态，不提供任何投资建议
    - 如果 last_row 中包含 RSI 和 ATR，会自动提取
    - 如果 atr_pct 未提供，会尝试从 last_row 计算（ATR / 收盘 * 100）
    """
    # 提取 RSI
    rsi_val = None
    if hasattr(last_row, "get"):
        rsi_val = last_row.get("RSI")
    elif isinstance(last_row, dict):
        rsi_val = last_row.get("RSI")

    # 提取或计算 ATR%
    if atr_pct is None and hasattr(last_row, "get"):
        atr = last_row.get("ATR")
        close = last_row.get("收盘")
        if atr is not None and close is not None and close != 0:
            try:
                c = float(close)
                if c > 0 and math.isfinite(c):
                    atr_pct = float(atr) / c * 100
            except (TypeError, ValueError):
                pass
    elif atr_pct is None and isinstance(last_row, dict):
        atr = last_row.get("ATR")
        close = last_row.get("收盘")
        if atr is not None and close is not None and close != 0:
            try:
                c = float(close)
                if c > 0 and math.isfinite(c):
                    atr_pct = float(atr) / c * 100
            except (TypeError, ValueError):
                pass

    # 计算各状态
    return {
        "trend": trend_state(r2, slope),
        "momentum": momentum_state(rsi_val),
        "valuation": valuation_state(premium_pctile_60),
        "volatility": volatility_state(atr_pct),
    }
