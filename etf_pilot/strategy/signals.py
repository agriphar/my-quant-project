# -*- coding: utf-8 -*-
"""Core / Tactical 信号、偏离度、追高提示、补仓建议。"""
import pandas as pd

from config.settings import (
    RSI_PERIOD,
    BB_PERIOD,
    BB_STD,
    RSI_OVERBOUGHT,
    RSI_BULLISH_MAX,
    VOL_SHRINK_RATIO,
)
from .asset_type import ASSET_TYPE_CORE, ASSET_TYPE_TACTICAL
from .constants import DEVIATION_CHASE_HIGH_PCT, ADDON_DROP_PCT, CORE_RSI_PULLBACK


def compute_deviation(price: float | None, ma20: float | None) -> float | None:
    """当前价格相对 MA20 的偏离度（百分比）。(price - MA20) / MA20 * 100"""
    if price is None or ma20 is None or pd.isna(price) or pd.isna(ma20) or ma20 == 0:
        return None
    return round((float(price) - float(ma20)) / float(ma20) * 100, 2)


def check_chase_high(deviation_pct: float | None) -> str:
    """偏离度过高时返回「不建议追高」，否则空串。"""
    if deviation_pct is None or pd.isna(deviation_pct):
        return ""
    if deviation_pct >= DEVIATION_CHASE_HIGH_PCT:
        return "不建议追高"
    return ""


def _core_buy(last: pd.Series) -> bool:
    """Core 买入：价格 > MA200 且 (回踩 MA20 或 RSI < 40)。"""
    price = last.get("收盘")
    ma20 = last.get("MA20")
    ma200 = last.get("MA200")
    rsi = last.get("RSI")
    if any(pd.isna(x) or x is None for x in (price, ma20, ma200)):
        return False
    if price <= ma200:
        return False
    # 回踩 MA20：价格在 MA20 附近（2% 以内）或略低于 MA20
    pullback_ma20 = ma20 and (price <= ma20 * 1.02 or abs(price - ma20) / ma20 < 0.02)
    rsi_oversold = rsi is not None and not pd.isna(rsi) and rsi < CORE_RSI_PULLBACK
    return bool(pullback_ma20 or rsi_oversold)


def _core_sell(last: pd.Series, prev: pd.Series) -> bool:
    """Core 卖出：跌破 MA60 且 MA20 向下交叉 MA60（死叉）。"""
    price = last.get("收盘")
    ma20 = last.get("MA20")
    ma60 = last.get("MA60")
    prev_ma20 = prev.get("MA20")
    prev_ma60 = prev.get("MA60")
    if any(pd.isna(x) or x is None for x in (price, ma20, ma60)):
        return False
    if price >= ma60:
        return False
    if ma20 >= ma60:
        return False
    # 死叉：前一日 MA20 >= MA60，当日 MA20 < MA60（刚发生死叉）
    if prev_ma20 is not None and prev_ma60 is not None and not pd.isna(prev_ma20) and not pd.isna(prev_ma60):
        if prev_ma20 < prev_ma60:
            return True  # 已死叉且价格在 MA60 下，维持卖出
    return True  # 当日 MA20 < MA60 且价格 < MA60 即视为卖出


def _tactical_buy(last: pd.Series, prev_vol_avg: float) -> bool:
    """Tactical 买入：原 MA20 趋势 + RSI/布林下轨。"""
    close = last["收盘"]
    ma_long = last["MA_long"]
    rsi = last.get("RSI")
    bb_lower = last.get("BB_lower")
    vol = last.get("成交量") or 0
    if pd.isna(close) or pd.isna(ma_long):
        return False
    if close <= ma_long:
        return False
    if bb_lower is not None and not pd.isna(bb_lower) and close <= bb_lower * 1.002 and prev_vol_avg > 0 and vol < prev_vol_avg * VOL_SHRINK_RATIO:
        return True
    if rsi is not None and not pd.isna(rsi) and rsi < RSI_BULLISH_MAX:
        return True
    return False


def _tactical_sell(last: pd.Series) -> bool:
    """Tactical 卖出：跌破 MA20 或 RSI > 80。"""
    close = last["收盘"]
    ma_long = last["MA_long"]
    rsi = last.get("RSI")
    if pd.isna(close) or pd.isna(ma_long):
        return False
    if close < ma_long:
        return True
    if rsi is not None and not pd.isna(rsi) and rsi > RSI_OVERBOUGHT:
        return True
    return False


def compute_signal(
    asset_type: str,
    last: pd.Series,
    prev: pd.Series,
    prev_vol_avg: float,
) -> str:
    """根据资产类型计算 买入 / 持有 / 减仓。"""
    if asset_type == ASSET_TYPE_CORE:
        if _core_sell(last, prev):
            return "减仓"
        if _core_buy(last):
            return "买入"
        return "持有"
    # Tactical
    if _tactical_sell(last):
        return "减仓"
    if _tactical_buy(last, prev_vol_avg):
        return "买入"
    return "持有"


def compute_addon_suggestion(
    asset_type: str,
    price: float | None,
    ma200: float | None,
    high_20d: float | None,
) -> str:
    """
    Core 资产在 MA200 之上时，相对近期高点每跌 5% 提示「分批金字塔补仓」。
    """
    if asset_type != ASSET_TYPE_CORE:
        return ""
    if price is None or ma200 is None or price <= 0 or price < ma200:
        return ""
    if high_20d is None or pd.isna(high_20d) or high_20d <= 0:
        return ""
    if price >= high_20d:
        return ""
    drop_pct = (high_20d - price) / high_20d * 100
    if drop_pct < ADDON_DROP_PCT:
        return ""
    n = int(drop_pct / ADDON_DROP_PCT)
    return f"自近期高点回落约 {drop_pct:.1f}%，可考虑分批金字塔补仓（每跌{ADDON_DROP_PCT}%一档）"
