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

# 相对溢价：偏离度 > 2 视为异常过热，> 2.5 一票否决
PREMIUM_DEVIATION_HOT = 2.0
PREMIUM_DEVIATION_VETO = 2.5

# 总分阈值
SCORE_STRONG_BUY = 7   # >= 7 强烈建议补仓
SCORE_HOLD = 4         # 4 <= x < 7 持有观望，< 4 考虑套利/减仓

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


def _score_valuation_premium(pctile_60: float | None) -> float:
    """估值因子 0~3：溢价 60d 分位低（便宜）给满分，高分位扣分。"""
    if pctile_60 is None or not math.isfinite(pctile_60):
        return 1.5
    if pctile_60 <= 25:
        return 3.0
    if pctile_60 <= 50:
        return 2.25
    if pctile_60 <= 75:
        return 1.5
    return 0.75


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
) -> dict[str, float]:
    """
    加权评分，总分 10 分（按因子去冗余后）。
    - 趋势 (3)：R² + slope
    - 动量 (2)：RSI
    - 估值 (3)：溢价 60d 分位
    - 波动 (2)：ATR%
    返回 {"trend": float, "momentum": float, "valuation": float, "volatility": float, "total": float}。
    兼容旧键 "tech"（= momentum）、"premium"（= valuation）。
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
    valuation = _score_valuation_premium(premium_pctile_60)
    volatility = _score_volatility(atr_pct)
    total = trend + momentum + valuation + volatility
    return {
        "trend": round(trend, 2),
        "momentum": round(momentum, 2),
        "valuation": round(valuation, 2),
        "volatility": round(volatility, 2),
        "total": round(min(10.0, total), 2),
        "tech": round(momentum, 2),
        "premium": round(valuation, 2),
    }


def state_to_score(signal_states: dict[str, str]) -> dict[str, float]:
    """
    将 Signal Engine 的状态字典转为 10 分制各因子分与总分。
    仅做状态→分数映射，不产生建议。
    """
    m = signal_states.get("momentum") or MOMENTUM_NEUTRAL
    t = signal_states.get("trend") or TREND_UNKNOWN
    v = signal_states.get("valuation") or VALUATION_UNKNOWN
    vol = signal_states.get("volatility") or VOLATILITY_UNKNOWN

    momentum = 2.0 if m == MOMENTUM_OVERSOLD else (1.0 if m == MOMENTUM_NEUTRAL else 0.0)
    trend = 3.0 if t == TREND_STRONG_UP else (2.0 if t == TREND_WEAK_UP else (0.5 if t == TREND_DOWN else 1.0))
    valuation = (
        3.0 if v == VALUATION_CHEAP
        else (2.25 if v == VALUATION_FAIR_LOW else (1.5 if v == VALUATION_FAIR_HIGH else (0.75 if v == VALUATION_EXPENSIVE else 1.5)))
    )
    volatility = 2.0 if vol == VOLATILITY_LOW else (1.0 if vol == VOLATILITY_MEDIUM else (0.0 if vol == VOLATILITY_HIGH else 1.0))

    total = momentum + trend + valuation + volatility
    return {
        "trend": round(trend, 2),
        "momentum": round(momentum, 2),
        "valuation": round(valuation, 2),
        "volatility": round(volatility, 2),
        "total": round(min(10.0, total), 2),
        "tech": round(momentum, 2),
        "premium": round(valuation, 2),
    }


def get_advice(
    signal_states: dict[str, str],
    premium_deviation_val: float | None,
    market_regime: dict[str, str] | None = None,
    risk_level: str | None = None,
) -> tuple[str, str]:
    """
    组合：信号状态 + 风险（溢价偏离度）+ 可选市场状态 + 风险引擎等级 → 明日建议与理由。
    Decision Engine 依赖 Risk Engine：risk_level 为 HIGH 时提高强烈补仓/持有门槛。
    """
    from risk_engine import RISK_HIGH, RISK_MEDIUM

    score_result = state_to_score(signal_states)
    total = score_result.get("total", 0) or 0
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
    vetoed = premium_deviation_val is not None and premium_deviation_val > PREMIUM_DEVIATION_VETO
    if vetoed:
        action = "极度过热，禁买"
    elif total >= strong_buy:
        action = "强烈建议补仓"
    elif total >= hold:
        action = "持有观望"
    else:
        action = "考虑套利/减仓"
    reason = get_reason_for_signal(action, total, vetoed)
    return action, reason


def get_signal_from_score(
    score_result: dict[str, float],
    premium_deviation_val: float | None,
) -> tuple[str, str]:
    """
    根据总分与溢价偏离度输出建议（兼容旧入口：已有 score 时使用）。
    - 一票否决：溢价偏离度 > 2.5 -> 极度过热，禁买。
    - 总分 >= 7：强烈建议补仓
    - 4 <= 总分 < 7：持有观望
    - 总分 < 4：考虑套利/减仓
    理由文案由 explanation_engine 生成。
    """
    total = score_result.get("total", 0) or 0
    vetoed = premium_deviation_val is not None and premium_deviation_val > PREMIUM_DEVIATION_VETO
    if vetoed:
        action = "极度过热，禁买"
    elif total >= SCORE_STRONG_BUY:
        action = "强烈建议补仓"
    elif total >= SCORE_HOLD:
        action = "持有观望"
    else:
        action = "考虑套利/减仓"
    reason = get_reason_for_signal(action, total, vetoed)
    return action, reason
