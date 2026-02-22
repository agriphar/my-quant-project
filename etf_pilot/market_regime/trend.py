# -*- coding: utf-8 -*-
"""趋势/震荡分类：基于 180 日线性回归 R² 与斜率。"""
import numpy as np
import pandas as pd

REGRESSION_WINDOW = 180
R2_TREND_THRESHOLD = 0.4
ASSET_TREND = "Trend (趋势型)"
ASSET_OSCILLATING = "Oscillating (震荡型)"


def _linear_regression_r2_slope(close: pd.Series, window: int = REGRESSION_WINDOW) -> tuple:
    """过去 window 日收盘价的线性回归，返回 (R², 斜率)。斜率 = 每日价格变动（元/日）。"""
    if close is None or len(close) < window:
        return None, None
    y = close.iloc[-window:].values.astype(float)
    if np.any(np.isnan(y)) or np.var(y) == 0:
        return None, None
    x = np.arange(len(y), dtype=float)
    n = len(x)
    x_mean = x.mean()
    y_mean = y.mean()
    ss_xy = np.sum((x - x_mean) * (y - y_mean))
    ss_xx = np.sum((x - x_mean) ** 2)
    ss_yy = np.sum((y - y_mean) ** 2)
    if ss_xx == 0 or ss_yy == 0:
        return None, None
    slope = ss_xy / ss_xx
    r_squared = (ss_xy ** 2) / (ss_xx * ss_yy) if (ss_xx * ss_yy) > 0 else 0.0
    return float(r_squared), float(slope)


def compute_trend_classification(hist: pd.DataFrame) -> tuple:
    """根据过去 180 日线性回归：R²>0.4 且斜率>0 为 Trend，否则 Oscillating。返回 (r2, slope, 资产性格)。"""
    if hist is None or len(hist) < REGRESSION_WINDOW or "收盘" not in hist.columns:
        return None, None, None
    close = hist["收盘"]
    r2, slope = _linear_regression_r2_slope(close, REGRESSION_WINDOW)
    if r2 is not None and slope is not None:
        personality = ASSET_TREND if (r2 > R2_TREND_THRESHOLD and slope > 0) else ASSET_OSCILLATING
    else:
        personality = None
    return r2, slope, personality


def linear_regression_r2_slope(close: pd.Series, window: int = REGRESSION_WINDOW) -> tuple:
    """对外暴露：供 decision_engine 等回溯计算使用。"""
    return _linear_regression_r2_slope(close, window)
