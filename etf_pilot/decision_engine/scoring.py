# -*- coding: utf-8 -*-
"""
Decision Engine：组合 Signal Engine 的状态 + 市场状态 + 风险 → 买卖建议。

- 不在此计算 RSI/趋势/估值/波动；由 Signal Engine 输出状态。
- 本模块：state_to_score（状态→分数）、溢价偏离度（风险否决）、get_advice（状态+风险+regime→建议）。
"""
from __future__ import annotations

import math
from typing import Any

from explanation_engine.reasons import get_reason_for_signal
from explanation_engine.structured_reasoning import explain_decision
from signal_engine.states import (
    MOMENTUM_OVERSOLD,
    MOMENTUM_NEUTRAL,
    MOMENTUM_OVERBOUGHT,
    TREND_STRONG_UP,
    TREND_WEAK_UP,
    TREND_DOWN,
    TREND_UNKNOWN,
    VALUATION_CHEAP,
    VALUATION_FAIR_LOW,
    VALUATION_FAIR_HIGH,
    VALUATION_EXPENSIVE,
    VALUATION_UNKNOWN,
    VOLATILITY_LOW,
    VOLATILITY_MEDIUM,
    VOLATILITY_HIGH,
    VOLATILITY_UNKNOWN,
)

# 溢价偏离度阈值（用于动态惩罚）
PREMIUM_DEVIATION_HOT = 1.5   # z_score > 1.5 时强制降为 0 分
PREMIUM_DEVIATION_EXTREME = 2.5  # z_score > 2.5 时记为 -4 分（极端过热惩罚）
# 向后兼容：保留旧常量名（已不再用于一票否决）
PREMIUM_DEVIATION_VETO = PREMIUM_DEVIATION_EXTREME

# 总分阈值
SCORE_STRONG_BUY = 7   # >= 7 强烈建议补仓
SCORE_HOLD = 4         # 4 <= x < 7 维持观望/持有，< 4 建议套利/减仓

# 波动（ATR%）阈值：低于下限给满分，高于上限给 0
ATR_PCT_LOW = 1.0     # ATR% < 1 → 低波动，满分
ATR_PCT_HIGH = 3.0    # ATR% > 3 → 高波动，0 分


def premium_deviation(
    current_premium: float | None,
    mean_22: float | None,
    std_22: float | None,
) -> float | None:
    """
    相对溢价偏离度：(当前溢价 - 22日均值) / 22日标准差。
    仅当 std_22 > 0 时有效；否则返回 None。
    """
    if current_premium is None or mean_22 is None or std_22 is None:
        return None
    if std_22 <= 0 or not math.isfinite(std_22):
        return None
    try:
        return (float(current_premium) - float(mean_22)) / float(std_22)
    except (TypeError, ValueError):
        return None


def _score_momentum_rsi(rsi: float | None) -> float:
    """动量因子 0~2：仅用 RSI，低 RSI 利于补仓。"""
    if rsi is None or not math.isfinite(rsi):
        return 1.0
    if rsi < 45:
        return 2.0
    if rsi <= 70:
        return 1.0
    return 0.0


def _score_trend(r2: float | None, slope: float | None) -> float:
    """趋势因子 0~3：R² 与斜率，趋势明确向上给高分。"""
    if slope is None or not math.isfinite(slope):
        return 1.0
    if slope <= 0:
        return 0.5
    r2_val = float(r2) if r2 is not None and math.isfinite(r2) else 0.0
    if r2_val >= 0.4:
        return 3.0
    if r2_val >= 0.2:
        return 2.0
    return 1.0


def _score_valuation_premium(
    pctile_60: float | None,
    premium_deviation_val: float | None = None,
) -> float:
    """
    估值因子（3分变动制）：基于溢价率百分位 + 溢价偏离度动态惩罚。
    
    基准分（0-3分）：
    - 0%分位（最便宜）给3分
    - 100%分位（最贵）给0分
    - 线性插值
    
    动态惩罚项：
    - 若 z_score > 1.5：溢价面分数强制降为 0
    - 若 z_score > 2.5：溢价面分数记为 -4 分（极端过热惩罚）
    
    返回：可能为负值（当 z_score > 2.5 时）
    """
    # 基准分：基于溢价率百分位（0%分位给3分，100%分位给0分）
    if pctile_60 is None or not math.isfinite(pctile_60):
        base_score = 1.5
    else:
        # 线性插值：0% -> 3分, 100% -> 0分
        base_score = 3.0 * (1.0 - float(pctile_60) / 100.0)
        base_score = max(0.0, min(3.0, base_score))
    
    # 动态惩罚：检查溢价偏离度
    if premium_deviation_val is not None and math.isfinite(premium_deviation_val):
        z_score = float(premium_deviation_val)
        if z_score > PREMIUM_DEVIATION_EXTREME:
            # 极端过热：记为 -4 分
            return -4.0
        elif z_score > PREMIUM_DEVIATION_HOT:
            # 轻度过热：强制降为 0
            return 0.0
    
    return base_score


def _score_volatility(atr_pct: float | None) -> float:
    """波动因子 0~2：ATR% 低给高分，高给低分。"""
    if atr_pct is None or not math.isfinite(atr_pct) or atr_pct < 0:
        return 1.0
    if atr_pct <= ATR_PCT_LOW:
        return 2.0
    if atr_pct >= ATR_PCT_HIGH:
        return 0.0
    # 线性插值
    return 2.0 - (float(atr_pct) - ATR_PCT_LOW) / (ATR_PCT_HIGH - ATR_PCT_LOW) * 2.0


def calculate_score(
    last_row: Any,
    r2: float | None = None,
    slope: float | None = None,
    premium_pctile_60: float | None = None,
    atr_pct: float | None = None,
    premium_deviation_val: float | None = None,
) -> dict[str, float]:
    """
    加权评分，总分 10 分（按因子去冗余后）。
    - 趋势 (3)：R² + slope
    - 动量 (2)：RSI
    - 估值 (3)：溢价 60d 分位 + 溢价偏离度动态惩罚（可能为负）
    - 波动 (2)：ATR%
    返回 {"trend": float, "momentum": float, "valuation": float, "volatility": float, "total": float}。
    兼容旧键 "tech"（= momentum）、"premium"（= valuation）。
    
    注意：valuation 可能为负值（当溢价偏离度 z_score > 2.5 时），总分也可能为负。
    """
    rsi_val = None
    if hasattr(last_row, "get"):
        rsi_val = last_row.get("RSI")
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
    trend = _score_trend(r2, slope)
    momentum = _score_momentum_rsi(rsi_val)
    valuation = _score_valuation_premium(premium_pctile_60, premium_deviation_val)
    volatility = _score_volatility(atr_pct)
    total = trend + momentum + valuation + volatility
    return {
        "trend": round(trend, 2),
        "momentum": round(momentum, 2),
        "valuation": round(valuation, 2),
        "volatility": round(volatility, 2),
        "total": round(total, 2),  # 不再限制上限，允许负分
        "tech": round(momentum, 2),
        "premium": round(valuation, 2),
    }


def state_to_score(
    signal_states: dict[str, str],
    premium_pctile_60: float | None = None,
    premium_deviation_val: float | None = None,
) -> dict[str, float]:
    """
    将 Signal Engine 的状态字典转为 10 分制各因子分与总分。
    仅做状态→分数映射，不产生建议。
    
    注意：valuation 分数现在需要溢价偏离度来计算动态惩罚，因此需要传入 premium_pctile_60 和 premium_deviation_val。
    """
    m = signal_states.get("momentum") or MOMENTUM_NEUTRAL
    t = signal_states.get("trend") or TREND_UNKNOWN
    v = signal_states.get("valuation") or VALUATION_UNKNOWN
    vol = signal_states.get("volatility") or VOLATILITY_UNKNOWN

    momentum = 2.0 if m == MOMENTUM_OVERSOLD else (1.0 if m == MOMENTUM_NEUTRAL else 0.0)
    trend = 3.0 if t == TREND_STRONG_UP else (2.0 if t == TREND_WEAK_UP else (0.5 if t == TREND_DOWN else 1.0))
    
    # 估值分数：使用新的评分函数，整合溢价偏离度惩罚
    valuation = _score_valuation_premium(premium_pctile_60, premium_deviation_val)
    
    volatility = 2.0 if vol == VOLATILITY_LOW else (1.0 if vol == VOLATILITY_MEDIUM else (0.0 if vol == VOLATILITY_HIGH else 1.0))

    total = momentum + trend + valuation + volatility
    # 允许负分以更强烈地触发减仓信号
    return {
        "trend": round(trend, 2),
        "momentum": round(momentum, 2),
        "valuation": round(valuation, 2),
        "volatility": round(volatility, 2),
        "total": round(total, 2),  # 不再限制上限，允许负分
        "tech": round(momentum, 2),
        "premium": round(valuation, 2),
    }


def _confidence_band(
    total: float,
    strong_buy: float,
    hold: float,
    risk_level: str | None,
    premium_deviation_val: float | None = None,
) -> str:
    """
    将分数与风险映射为信心区间（非精确分数），用于展示不确定性。
    high / medium / low；高风险或溢价过热时下调。
    """
    from risk_engine import RISK_HIGH

    # 溢价过热时降低信心
    if premium_deviation_val is not None and premium_deviation_val > PREMIUM_DEVIATION_HOT:
        return "low"
    
    if total >= strong_buy:
        return "medium" if risk_level == RISK_HIGH else "high"
    if total >= hold:
        return "low" if risk_level == RISK_HIGH else "medium"
    return "low"


def _display_label(action: str) -> str:
    """
    非确定性、行为金融友好的展示文案：避免「强烈建议」「必买/必卖」等措辞。
    """
    if action == "强烈建议补仓":
        return "偏多，可考虑补仓"
    if action == "维持观望/持有":
        return "观望"
    if action == "建议套利/减仓":
        return "偏空，可考虑减仓"
    return action


def get_advice(
    signal_states: dict[str, str],
    premium_deviation_val: float | None,
    market_regime: dict[str, str] | None = None,
    risk_level: str | None = None,
    premium_pctile_60: float | None = None,
) -> tuple[str, str, str, str]:
    """
    组合：信号状态 + 风险（溢价偏离度）+ 可选市场状态 + 风险引擎等级 → 明日建议与理由。
    返回 (action, reason, display_label, confidence_band)。
    display_label 为界面用非确定性措辞；confidence_band 为 high/medium/low。
    
    注意：溢价偏离度已整合进评分系统，不再使用一票否决制。
    """
    from risk_engine import RISK_HIGH, RISK_MEDIUM

    # 计算分数（包含溢价偏离度惩罚）
    score_result = state_to_score(
        signal_states,
        premium_pctile_60=premium_pctile_60,
        premium_deviation_val=premium_deviation_val,
    )
    total = score_result.get("total", 0) or 0
    
    # 根据市场状态和风险等级调整阈值
    strong_buy = SCORE_STRONG_BUY
    hold = SCORE_HOLD
    if market_regime and market_regime.get("risk_regime") == "risk_off":
        strong_buy = 8
        hold = 5
    if risk_level == RISK_HIGH:
        strong_buy = 8
        hold = 5
    elif risk_level == RISK_MEDIUM:
        strong_buy = 7.5
        hold = 4.5
    
    # 信号映射：基于总分（不再使用一票否决）
    if total >= strong_buy:
        action = "强烈建议补仓"
    elif total >= hold:
        action = "维持观望/持有"
    else:
        action = "建议套利/减仓"
    
    # 使用 Explanation Engine 的结构化理由
    explained = explain_decision(
        regime=market_regime,
        signal_states=signal_states,
        risk_level=risk_level,
        decision=action,
        premium_deviation_val=premium_deviation_val,
        total_score=total,
        score_result=score_result,
    )
    reason = explained["one_liner"]
    display_label = _display_label(action)
    confidence_band = _confidence_band(total, strong_buy, hold, risk_level, premium_deviation_val)
    return action, reason, display_label, confidence_band


def get_signal_from_score(
    score_result: dict[str, float],
    premium_deviation_val: float | None,
) -> tuple[str, str]:
    """
    根据总分输出建议（兼容旧入口：已有 score 时使用）。
    注意：溢价偏离度已整合进评分系统，不再使用一票否决制。
    
    - 总分 >= 7：强烈建议补仓
    - 4 <= 总分 < 7：维持观望/持有
    - 总分 < 4：建议套利/减仓
    理由文案由 explanation_engine 生成。
    """
    total = score_result.get("total", 0) or 0
    
    # 信号映射：基于总分（不再使用一票否决）
    if total >= SCORE_STRONG_BUY:
        action = "强烈建议补仓"
    elif total >= SCORE_HOLD:
        action = "维持观望/持有"
    else:
        action = "建议套利/减仓"
    
    reason = get_reason_for_signal(action, total, premium_deviation_val, score_result)
    return action, reason
