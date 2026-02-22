# -*- coding: utf-8 -*-
"""技术指标：RSI、布林带、ATR、乖离率、1年高低点、线性回归 R²/斜率（委托 market_regime）。"""
import numpy as np
import pandas as pd

from config.settings import RSI_PERIOD, BB_PERIOD, BB_STD


def rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """RSI 指标。"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def bollinger(close: pd.Series, period: int = BB_PERIOD, num_std: float = BB_STD):
    """布林带：返回 (mid, upper, lower)。"""
    mid = close.rolling(period, min_periods=1).mean()
    std = close.rolling(period, min_periods=1).std()
    return mid, mid + num_std * std, mid - num_std * std


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """ATR = SMA(TR, period), TR = max(H-L, |H-prev_C|, |L-prev_C|)。"""
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    return tr.rolling(period, min_periods=1).mean()


def bias_pct(price: float | None, ma: float | None) -> float | None:
    """乖离率：(price - ma) / ma * 100。"""
    if price is None or ma is None or pd.isna(ma) or ma == 0:
        return None
    return round((float(price) - float(ma)) / float(ma) * 100, 2)


TRADING_DAYS_1Y = 250


def pct_from_1y_high_low(hist: pd.DataFrame) -> tuple:
    """距一年内最高点、最低点的百分比。返回 (距最高点%, 距最低点%)。"""
    if hist is None or len(hist) < 20 or "收盘" not in hist.columns:
        return None, None
    window = hist["收盘"].tail(TRADING_DAYS_1Y)
    high_1y = window.max()
    low_1y = window.min()
    close = hist["收盘"].iloc[-1]
    if pd.isna(close) or close <= 0:
        return None, None
    pct_from_high = (float(high_1y - close) / float(high_1y) * 100) if high_1y and high_1y > 0 else None
    pct_from_low = (float(close - low_1y) / float(low_1y) * 100) if low_1y and low_1y > 0 else None
    return pct_from_high, pct_from_low
