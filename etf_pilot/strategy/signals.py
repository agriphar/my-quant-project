# -*- coding: utf-8 -*-
"""Core / Tactical 信号、偏离度、追高提示、补仓建议；智能网格做T 信号（与回测一致）。"""
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
from .asset_type import ASSET_TYPE_CORE, ASSET_TYPE_TACTICAL
from .constants import (
    DEVIATION_CHASE_HIGH_PCT,
    ADDON_DROP_PCT,
    CORE_RSI_PULLBACK,
    CORE_MA200_DEVIATION_SELL_PCT,
)


def compute_grid_signal(price: float | None, center_30: float | None, step_pct: float = GRID_STEP_PCT) -> str:
    """
    步进式网格信号（与回测一致）：参考价为近 30 日均价，步长 step_pct（1.2%）。
    现价 ≤ 参考×(1-step) → 买入；≥ 参考×(1+step) → 卖出；否则 持有。
    """
    if price is None or center_30 is None or pd.isna(price) or pd.isna(center_30) or center_30 <= 0:
        return "持有"
    p, c = float(price), float(center_30)
    if p <= c * (1 - step_pct):
        return "买入"
    if p >= c * (1 + step_pct):
        return "卖出"
    return "持有"


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
    """Core 买入：价格 > MA200（大趋势向上）且 价格回撤至 MA20 附近 或 RSI < 45。"""
    price = last.get("收盘")
    ma20 = last.get("MA20")
    ma200 = last.get("MA200")
    rsi = last.get("RSI")
    if any(pd.isna(x) or x is None for x in (price, ma20, ma200)):
        return False
    if price <= ma200:
        return False
    # 回踩 MA20 附近：价格在 MA20 上下 2% 以内
    pullback_ma20 = ma20 and (price <= ma20 * 1.02 or abs(price - ma20) / ma20 < 0.02)
    rsi_pullback = rsi is not None and not pd.isna(rsi) and rsi < CORE_RSI_PULLBACK
    return bool(pullback_ma20 or rsi_pullback)


def _core_sell(last: pd.Series, prev: pd.Series) -> bool:
    """Core 卖出：跌破 MA60 或 价格相对 MA200 乖离率过大（过高）时减仓。"""
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
    Core 资产：在已有持仓基础上，若自近期高点进一步下跌 5% 且仍位于 MA200 之上，可增加 0.5 倍仓位（最多 3 批）。
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
    return f"自近期高点回落约 {drop_pct:.1f}%，若仍在 MA200 之上可加仓 0.5 倍仓位（每跌{ADDON_DROP_PCT}%一档，最多 3 批）"
