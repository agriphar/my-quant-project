# -*- coding: utf-8 -*-
"""信号分歧风险：多因子状态方向不一致时风险升高，输出 LOW/MEDIUM/HIGH。"""
from __future__ import annotations

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"

# 与 signal_engine.states 对齐（仅读状态名，不导入避免循环）
BULLISH_MOMENTUM = "oversold"
BEARISH_MOMENTUM = "overbought"
BULLISH_TREND = ("strong_up", "weak_up")
BEARISH_TREND = "down"
BULLISH_VALUATION = ("cheap", "fair_low")
BEARISH_VALUATION = ("expensive", "fair_high")
BULLISH_VOL = "low"
BEARISH_VOL = "high"


def _is_bullish(state: str, factor: str) -> bool:
    if factor == "momentum":
        return state == BULLISH_MOMENTUM
    if factor == "trend":
        return state in BULLISH_TREND
    if factor == "valuation":
        return state in BULLISH_VALUATION
    if factor == "volatility":
        return state == BULLISH_VOL
    return False


def _is_bearish(state: str, factor: str) -> bool:
    if factor == "momentum":
        return state == BEARISH_MOMENTUM
    if factor == "trend":
        return state == BEARISH_TREND
    if factor == "valuation":
        return state in BEARISH_VALUATION
    if factor == "volatility":
        return state == BEARISH_VOL
    return False


def signal_disagreement_risk(signal_states: dict[str, str]) -> str:
    """
    信号分歧风险：统计四因子中「偏多」与「偏空」数量；严重分歧为 HIGH。
    - 4–0 或 3–1 一致: LOW
    - 2–2 分歧: HIGH
    - 1–3 或 0–4 一致但偏空: MEDIUM（方向一致但不利）
    """
    if not signal_states:
        return RISK_MEDIUM
    bullish = 0
    bearish = 0
    for factor in ("momentum", "trend", "valuation", "volatility"):
        state = signal_states.get(factor)
        if not state:
            continue
        if _is_bullish(state, factor):
            bullish += 1
        elif _is_bearish(state, factor):
            bearish += 1
    total = bullish + bearish
    if total == 0:
        return RISK_MEDIUM
    if bullish >= 3 or bearish >= 3:
        return RISK_LOW
    if bullish == 2 and bearish == 2:
        return RISK_HIGH
    return RISK_MEDIUM
