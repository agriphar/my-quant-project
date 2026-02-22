# -*- coding: utf-8 -*-
"""
风险引擎汇总：波动率状态、回撤、信号分歧、集中度 → 单一风险等级 LOW / MEDIUM / HIGH。
"""
from __future__ import annotations

from typing import Any

from .volatility_regime import volatility_risk_level
from .drawdown_risk import drawdown_from_high, drawdown_risk_level
from .signal_disagreement import signal_disagreement_risk
from .concentration_risk import concentration_risk_level

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"


def _ordinal(level: str) -> int:
    return 0 if level == RISK_LOW else (1 if level == RISK_MEDIUM else 2)


def evaluate_risk(
    *,
    atr_pct: float | None = None,
    pct_drawdown_from_high: float | None = None,
    current_price: float | None = None,
    high_60d: float | None = None,
    signal_states: dict[str, str] | None = None,
    weight_pct: float | None = None,
    n_positions: int | None = None,
) -> dict[str, Any]:
    """
    综合四维风险，输出单一风险等级及明细。

    参数:
    - atr_pct: 波动率（ATR/收盘*100）
    - pct_drawdown_from_high: 当前距近期高点的回撤百分比；若未提供且给出 current_price 与 high_60d 则内部计算
    - current_price, high_60d: 可选，用于计算回撤
    - signal_states: 信号状态字典（用于分歧风险）
    - weight_pct: 该标的占组合权重%
    - n_positions: 组合持仓数

    返回:
    {
        "level": "LOW" | "MEDIUM" | "HIGH",
        "volatility_regime": "LOW"|"MEDIUM"|"HIGH",
        "drawdown_risk": "LOW"|"MEDIUM"|"HIGH",
        "signal_disagreement": "LOW"|"MEDIUM"|"HIGH",
        "concentration_risk": "LOW"|"MEDIUM"|"HIGH",
    }
    """
    vol_level = volatility_risk_level(atr_pct)
    if pct_drawdown_from_high is None and current_price is not None and high_60d is not None:
        pct_drawdown_from_high = drawdown_from_high(current_price, high_60d)
    dd_level = drawdown_risk_level(pct_drawdown_from_high)
    sig_level = signal_disagreement_risk(signal_states or {})
    conc_level = concentration_risk_level(weight_pct=weight_pct, n_positions=n_positions)

    components = [vol_level, dd_level, sig_level, conc_level]
    ordinals = [_ordinal(c) for c in components]
    max_o = max(ordinals)
    sum_o = sum(ordinals)
    if max_o >= 2:
        level = RISK_HIGH
    elif max_o >= 1 or sum_o >= 2:
        level = RISK_MEDIUM
    else:
        level = RISK_LOW

    return {
        "level": level,
        "volatility_regime": vol_level,
        "drawdown_risk": dd_level,
        "signal_disagreement": sig_level,
        "concentration_risk": conc_level,
    }
