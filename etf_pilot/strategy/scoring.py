# -*- coding: utf-8 -*-
"""
加权评分制决策逻辑：技术面(4) + 趋势面(3) + 溢价面(3)，总分 10 分。
相对溢价：溢价偏离度 = (当前溢价 - 22日均值) / 22日标准差；>2.5 一票否决。
"""
from __future__ import annotations

import math
from typing import Any

# 相对溢价：偏离度 > 2 视为异常过热，> 2.5 一票否决
PREMIUM_DEVIATION_HOT = 2.0
PREMIUM_DEVIATION_VETO = 2.5

# 总分阈值
SCORE_STRONG_BUY = 7   # >= 7 强烈建议补仓
SCORE_HOLD = 4         # 4 <= x < 7 持有观望，< 4 考虑套利/减仓


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


def _score_rsi(rsi: float | None) -> float:
    """RSI 子分 0~1.33：低 RSI 利于补仓。"""
    if rsi is None or not math.isfinite(rsi):
        return 0.67
    if rsi < 45:
        return 1.33
    if rsi <= 70:
        return 0.65
    return 0.0


def _score_bias_ma20(bias: float | None) -> float:
    """MA20 乖离子分 0~1.33：接近均线或略低利于补仓。"""
    if bias is None or not math.isfinite(bias):
        return 0.67
    if bias < -2:
        return 1.33
    if bias <= 2:
        return 1.0
    if bias <= 5:
        return 0.5
    return 0.0


def _score_bias_ma200(bias: float | None) -> float:
    """MA200 乖离/距离子分 0~1.34：低于或接近 200 日线利于补仓。"""
    if bias is None or not math.isfinite(bias):
        return 0.67
    if bias < 0:
        return 1.34
    if bias <= 5:
        return 0.9
    if bias <= 10:
        return 0.4
    return 0.0


def _score_trend(r2: float | None, slope: float | None) -> float:
    """趋势面 0~3：R² 与斜率，趋势明确向上给高分。"""
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


def _score_premium_pctile(pctile_60: float | None) -> float:
    """溢价面 0~3：分位低（便宜）给满分，分位高扣分。"""
    if pctile_60 is None or not math.isfinite(pctile_60):
        return 1.5
    if pctile_60 <= 25:
        return 3.0
    if pctile_60 <= 50:
        return 2.25
    if pctile_60 <= 75:
        return 1.5
    return 0.75


def calculate_score(
    last_row: Any,
    r2: float | None = None,
    slope: float | None = None,
    premium_pctile_60: float | None = None,
    bias_ma20: float | None = None,
    bias_ma200: float | None = None,
) -> dict[str, float]:
    """
    加权评分，总分 10 分。
    - 技术面 (4 分)：RSI、Bias_MA20、Bias_MA200（距离 200 日线位置）。
    - 趋势面 (3 分)：R² 与斜率。
    - 溢价面 (3 分)：溢价分位低给满分，高分位扣分。
    返回 {"tech": float, "trend": float, "premium": float, "total": float}。
    """
    rsi = None
    close = None
    if hasattr(last_row, "get"):
        rsi = last_row.get("RSI")
        close = last_row.get("收盘")
    if bias_ma20 is None and hasattr(last_row, "get"):
        ma20 = last_row.get("MA20")
        if close is not None and ma20 is not None and ma20 != 0:
            try:
                bias_ma20 = (float(close) - float(ma20)) / float(ma20) * 100
            except (TypeError, ValueError):
                pass
    if bias_ma200 is None and hasattr(last_row, "get"):
        ma200 = last_row.get("MA200")
        if close is not None and ma200 is not None and ma200 != 0:
            try:
                bias_ma200 = (float(close) - float(ma200)) / float(ma200) * 100
            except (TypeError, ValueError):
                pass
    tech = _score_rsi(rsi) + _score_bias_ma20(bias_ma20) + _score_bias_ma200(bias_ma200)
    trend = _score_trend(r2, slope)
    prem = _score_premium_pctile(premium_pctile_60)
    total = tech + trend + prem
    return {
        "tech": round(tech, 2),
        "trend": round(trend, 2),
        "premium": round(prem, 2),
        "total": round(min(10.0, total), 2),
    }


def get_signal_from_score(
    score_result: dict[str, float],
    premium_deviation_val: float | None,
) -> tuple[str, str]:
    """
    根据总分与溢价偏离度输出建议。
    - 一票否决：溢价偏离度 > 2.5 -> 极度过热，禁买。
    - 总分 >= 7：强烈建议补仓
    - 4 <= 总分 < 7：持有观望
    - 总分 < 4：考虑套利/减仓
    """
    total = score_result.get("total", 0) or 0
    if premium_deviation_val is not None and premium_deviation_val > PREMIUM_DEVIATION_VETO:
        return "极度过热，禁买", "溢价偏离度>2.5，无论技术面多高均禁止买入"
    if total >= SCORE_STRONG_BUY:
        return "强烈建议补仓", f"综合评分{total}分，技术/趋势/溢价面均偏利多"
    if total >= SCORE_HOLD:
        return "持有观望", f"综合评分{total}分，暂无明确加仓或减仓信号"
    return "考虑套利/减仓", f"综合评分{total}分，技术或溢价面偏空，可考虑兑现部分仓位"
