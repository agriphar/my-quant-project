# -*- coding: utf-8 -*-
"""
Signal Engine — 仅输出状态，不输出买卖建议。

- 网格/偏离度：输出相对位置状态（below_center / near_center / above_center 等）。
- Core/Tactical：输出方向状态（bullish / neutral / bearish），不输出「买入」「减仓」。
- 补仓机会：输出状态（addon_opportunity / no_addon）及可选数值，由 Decision Engine 生成文案。
"""
import pandas as pd

from config.settings import (
    RSI_PERIOD,
    BB_PERIOD,
    BB_STD,
    RSI_OVERBOUGHT,
    RSI_BULLISH_MAX,
    VOL_SHRINK_RATIO,
    GRID_STEP_PCT,
)
# 资产类型与策略常数，与 strategy 一致，避免循环依赖
ASSET_TYPE_CORE = "Core"
ASSET_TYPE_TACTICAL = "Tactical"
DEVIATION_CHASE_HIGH_PCT = 10.0
ADDON_DROP_PCT = 5.0
CORE_RSI_PULLBACK = 45
CORE_MA200_DEVIATION_SELL_PCT = 15.0

# 状态常量（非建议）
GRID_BELOW_CENTER = "below_center"
GRID_NEAR_CENTER = "near_center"
GRID_ABOVE_CENTER = "above_center"

DIRECTION_BULLISH = "bullish"
DIRECTION_NEUTRAL = "neutral"
DIRECTION_BEARISH = "bearish"

ADDON_OPPORTUNITY = "addon_opportunity"
ADDON_NONE = "no_addon"


def compute_grid_signal(price: float | None, center_30: float | None, step_pct: float = GRID_STEP_PCT) -> str:
    """
    步进式网格：仅输出价格相对参考价的状态，不输出买卖建议。
    返回 below_center | near_center | above_center。
    """
    if price is None or center_30 is None or pd.isna(price) or pd.isna(center_30) or center_30 <= 0:
        return GRID_NEAR_CENTER
    p, c = float(price), float(center_30)
    if p <= c * (1 - step_pct):
        return GRID_BELOW_CENTER
    if p >= c * (1 + step_pct):
        return GRID_ABOVE_CENTER
    return GRID_NEAR_CENTER


def compute_deviation(price: float | None, ma20: float | None) -> float | None:
    """当前价格相对 MA20 的偏离度（百分比）。纯数值，非建议。"""
    if price is None or ma20 is None or pd.isna(price) or pd.isna(ma20) or ma20 == 0:
        return None
    return round((float(price) - float(ma20)) / float(ma20) * 100, 2)


def check_chase_high(deviation_pct: float | None) -> str:
    """
    偏离度过高时的状态标签，供 Decision Engine 生成文案用。
    返回 "high_deviation" 或 ""，不直接返回「不建议追高」等建议文案。
    """
    if deviation_pct is None or pd.isna(deviation_pct):
        return ""
    if deviation_pct >= DEVIATION_CHASE_HIGH_PCT:
        return "high_deviation"
    return ""


def _core_buy(last: pd.Series) -> bool:
    """Core 偏多条件（内部用，不对外输出建议）。"""
    price = last.get("收盘")
    ma20 = last.get("MA20")
    ma200 = last.get("MA200")
    rsi = last.get("RSI")
    if any(pd.isna(x) or x is None for x in (price, ma20, ma200)):
        return False
    if price <= ma200:
        return False
    pullback_ma20 = ma20 and (price <= ma20 * 1.02 or abs(price - ma20) / ma20 < 0.02)
    rsi_pullback = rsi is not None and not pd.isna(rsi) and rsi < CORE_RSI_PULLBACK
    return bool(pullback_ma20 or rsi_pullback)


def _core_sell(last: pd.Series, prev: pd.Series) -> bool:
    """Core 偏空条件（内部用）。"""
    price = last.get("收盘")
    ma60 = last.get("MA60")
    ma200 = last.get("MA200")
    if any(pd.isna(x) or x is None for x in (price, ma60)):
        return False
    if price < ma60:
        return True
    if ma200 is not None and not pd.isna(ma200) and ma200 > 0:
        deviation_ma200 = (price - ma200) / ma200 * 100
        if deviation_ma200 >= CORE_MA200_DEVIATION_SELL_PCT:
            return True
    return False


def _tactical_buy(last: pd.Series, prev_vol_avg: float) -> bool:
    """Tactical 偏多条件（内部用）。"""
    close = last["收盘"]
    ma_long = last["MA_long"]
    rsi_val = last.get("RSI")
    bb_lower = last.get("BB_lower")
    vol = last.get("成交量") or 0
    if pd.isna(close) or pd.isna(ma_long):
        return False
    if close <= ma_long:
        return False
    if bb_lower is not None and not pd.isna(bb_lower) and close <= bb_lower * 1.002 and prev_vol_avg > 0 and vol < prev_vol_avg * VOL_SHRINK_RATIO:
        return True
    if rsi_val is not None and not pd.isna(rsi_val) and rsi_val < RSI_BULLISH_MAX:
        return True
    return False


def _tactical_sell(last: pd.Series) -> bool:
    """Tactical 偏空条件（内部用）。"""
    close = last["收盘"]
    ma_long = last["MA_long"]
    rsi_val = last.get("RSI")
    if pd.isna(close) or pd.isna(ma_long):
        return False
    if close < ma_long:
        return True
    if rsi_val is not None and not pd.isna(rsi_val) and rsi_val > RSI_OVERBOUGHT:
        return True
    return False


def compute_signal(
    asset_type: str,
    last: pd.Series,
    prev: pd.Series,
    prev_vol_avg: float,
) -> str:
    """
    根据资产类型输出方向状态，不输出买卖建议。
    返回 bullish | neutral | bearish。
    """
    if asset_type == ASSET_TYPE_CORE:
        if _core_sell(last, prev):
            return DIRECTION_BEARISH
        if _core_buy(last):
            return DIRECTION_BULLISH
        return DIRECTION_NEUTRAL
    if _tactical_sell(last):
        return DIRECTION_BEARISH
    if _tactical_buy(last, prev_vol_avg):
        return DIRECTION_BULLISH
    return DIRECTION_NEUTRAL


def compute_addon_suggestion(
    asset_type: str,
    price: float | None,
    ma200: float | None,
    high_20d: float | None,
) -> tuple[str, float | None]:
    """
    仅输出补仓相关状态及可选数值，不输出建议文案。
    返回 (addon_opportunity | no_addon, drop_pct | None)。
    """
    if asset_type != ASSET_TYPE_CORE:
        return ADDON_NONE, None
    if price is None or ma200 is None or price <= 0 or price < ma200:
        return ADDON_NONE, None
    if high_20d is None or pd.isna(high_20d) or high_20d <= 0:
        return ADDON_NONE, None
    if price >= high_20d:
        return ADDON_NONE, None
    drop_pct = (high_20d - price) / high_20d * 100
    if drop_pct < ADDON_DROP_PCT:
        return ADDON_NONE, None
    return ADDON_OPPORTUNITY, round(drop_pct, 1)
