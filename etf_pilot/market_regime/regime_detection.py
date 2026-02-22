# -*- coding: utf-8 -*-
"""
Market Regime Detection — 简单可解释指标分类.

维度:
- risk_on / risk_off: 基于 VIX 水平
- liquidity tightening / easing: 基于短端利率变化（如 2Y 收益率 1 个月变化）
- USD strength / weakness: 基于 DXY 与均线相对位置

输出: risk_regime, liquidity, usd_trend, confidence（不接 UI）
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 可解释阈值（仅用简单规则）
# ---------------------------------------------------------------------------
VIX_RISK_OFF = 25.0   # VIX >= 25 → risk_off
VIX_RISK_ON = 18.0    # VIX <= 18 → risk_on；18–25 为过渡
VIX_NEUTRAL_HIGH = 22.0  # 用于置信度：越接近 20 越模糊

LIQUIDITY_CHANGE_BPS = 15.0   # 2Y 收益率 1 个月变化超过 ±15 bp 视为明确方向
MA_DAYS_USD = 20             # DXY 趋势用 20 日均线
USD_MA_PCT_THRESHOLD = 0.3    # 现价相对 MA 偏离超过 ±0.3% 才判定方向

CONFIDENCE_STRONG = "high"    # 信号明确
CONFIDENCE_MODERATE = "medium"
CONFIDENCE_WEAK = "low"       # 接近阈值或数据不足


def _last_value(series: pd.Series | None) -> float | None:
    """取序列最后一个有效值。"""
    if series is None or series.empty:
        return None
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    return float(clean.iloc[-1])


def _pct_change_over_period(series: pd.Series | None, days: int) -> float | None:
    """过去 days 个交易日的变化（百分比）。若为收益率序列则用绝对变化更合适，这里统一用 pct。"""
    if series is None or len(series) < 2 or days < 1:
        return None
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) <= days:
        return None
    old, new = s.iloc[-1 - days], s.iloc[-1]
    if old == 0 or np.isnan(old):
        return None
    return float((new - old) / abs(old) * 100.0)


def _level_change_over_period(series: pd.Series | None, days: int) -> float | None:
    """过去 days 个交易日的水平变化（做差），用于收益率等。"""
    if series is None or len(series) < 2 or days < 1:
        return None
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) <= days:
        return None
    return float(s.iloc[-1] - s.iloc[-1 - days])


# ---------------------------------------------------------------------------
# 1) Risk regime: VIX
# ---------------------------------------------------------------------------
def classify_risk_regime(vix: float | None) -> tuple[str, str]:
    """
    仅用 VIX 水平划分 risk_on / risk_off.
    - VIX <= 18: risk_on, 高置信
    - VIX >= 25: risk_off, 高置信
    - 18 < VIX < 25: 取较近一端，置信度 medium/low
    返回 (regime, confidence).
    """
    if vix is None or np.isnan(vix):
        return "unknown", CONFIDENCE_WEAK
    v = float(vix)
    if v <= VIX_RISK_ON:
        dist = VIX_RISK_ON - v
        conf = CONFIDENCE_STRONG if dist >= 3 else CONFIDENCE_MODERATE
        return "risk_on", conf
    if v >= VIX_RISK_OFF:
        dist = v - VIX_RISK_OFF
        conf = CONFIDENCE_STRONG if dist >= 5 else CONFIDENCE_MODERATE
        return "risk_off", conf
    # 过渡区：按更接近哪一侧
    to_low = v - VIX_RISK_ON
    to_high = VIX_RISK_OFF - v
    if to_low <= to_high:
        return "risk_on", CONFIDENCE_WEAK
    return "risk_off", CONFIDENCE_WEAK


# ---------------------------------------------------------------------------
# 2) Liquidity: 短端利率变化（如 2Y 收益率 1 个月变化）
# ---------------------------------------------------------------------------
def classify_liquidity(yield_2y_change_bps: float | None) -> tuple[str, str]:
    """
    基于 2Y 收益率在观测窗口内的变化（bp）.
    - 上升 > 阈值: tightening
    - 下降 > 阈值: easing
    - 否则: neutral，置信度 low
    返回 (liquidity, confidence).
    """
    if yield_2y_change_bps is None or np.isnan(yield_2y_change_bps):
        return "unknown", CONFIDENCE_WEAK
    bps = float(yield_2y_change_bps)
    thresh = LIQUIDITY_CHANGE_BPS
    if bps >= thresh:
        return "tightening", CONFIDENCE_STRONG if bps >= thresh * 1.5 else CONFIDENCE_MODERATE
    if bps <= -thresh:
        return "easing", CONFIDENCE_STRONG if bps <= -thresh * 1.5 else CONFIDENCE_MODERATE
    return "neutral", CONFIDENCE_WEAK


# ---------------------------------------------------------------------------
# 3) USD trend: DXY 现价 vs 均线
# ---------------------------------------------------------------------------
def classify_usd_trend(dxy_level: float | None, dxy_ma20: float | None) -> tuple[str, str]:
    """
    DXY 现价相对 20 日均线: 上方为 strength，下方为 weakness.
    偏离不足时记为 neutral.
    返回 (usd_trend, confidence).
    """
    if dxy_level is None or np.isnan(dxy_level) or dxy_ma20 is None or np.isnan(dxy_ma20) or dxy_ma20 == 0:
        return "unknown", CONFIDENCE_WEAK
    level, ma = float(dxy_level), float(dxy_ma20)
    pct = (level - ma) / ma * 100.0
    if pct >= USD_MA_PCT_THRESHOLD:
        return "strength", CONFIDENCE_STRONG if pct >= 0.5 else CONFIDENCE_MODERATE
    if pct <= -USD_MA_PCT_THRESHOLD:
        return "weakness", CONFIDENCE_STRONG if pct <= -0.5 else CONFIDENCE_MODERATE
    return "neutral", CONFIDENCE_WEAK


# ---------------------------------------------------------------------------
# 综合置信度（取最弱维度）
# ---------------------------------------------------------------------------
def _overall_confidence(parts: list[str]) -> str:
    order = (CONFIDENCE_WEAK, CONFIDENCE_MODERATE, CONFIDENCE_STRONG)
    idx = min(order.index(p) for p in parts if p in order)
    return order[idx]


# ---------------------------------------------------------------------------
# 主入口：输出标准结构，不接 UI
# ---------------------------------------------------------------------------
def detect_regime(
    *,
    vix_series: pd.Series | None = None,
    vix_latest: float | None = None,
    dxy_series: pd.Series | None = None,
    yield_2y_series: pd.Series | None = None,
    liquidity_lookback_days: int = 22,
) -> dict[str, str]:
    """
    根据可选输入的 VIX、DXY、2Y 收益率序列（或最新值）计算当前市场状态.

    可只传 vix_latest 做仅风险维度；也可传 series 由内部取最近值/均线/变化.

    返回:
    {
        "risk_regime": "risk_on" | "risk_off" | "unknown",
        "liquidity": "tightening" | "easing" | "neutral" | "unknown",
        "usd_trend": "strength" | "weakness" | "neutral" | "unknown",
        "confidence": "high" | "medium" | "low"
    }
    """
    confidence_parts: list[str] = []

    # Risk: 优先 vix_latest，否则从 series 取最后值
    vix = vix_latest
    if vix is None and vix_series is not None:
        vix = _last_value(vix_series)
    risk_regime, risk_conf = classify_risk_regime(vix)
    confidence_parts.append(risk_conf)

    # Liquidity: 2Y 收益率在 lookback 内的变化（百分点点数 → bp：0.15 → 15 bp）
    yield_change_bps: float | None = None
    if yield_2y_series is not None and len(yield_2y_series) > liquidity_lookback_days:
        diff = _level_change_over_period(yield_2y_series, liquidity_lookback_days)
        if diff is not None:
            yield_change_bps = diff * 100.0  # 收益率若为 4.5 表示 4.5%，差 0.15 = 15 bp
    liquidity, liq_conf = classify_liquidity(yield_change_bps)
    confidence_parts.append(liq_conf)

    # USD: DXY 现价 vs 20d MA
    dxy_level = _last_value(dxy_series) if dxy_series is not None else None
    dxy_ma20: float | None = None
    if dxy_series is not None and len(dxy_series) >= MA_DAYS_USD:
        s = pd.to_numeric(dxy_series, errors="coerce").dropna()
        if len(s) >= MA_DAYS_USD:
            dxy_ma20 = float(s.tail(MA_DAYS_USD).mean())
    usd_trend, usd_conf = classify_usd_trend(dxy_level, dxy_ma20)
    confidence_parts.append(usd_conf)

    overall = _overall_confidence(confidence_parts) if confidence_parts else CONFIDENCE_WEAK

    return {
        "risk_regime": risk_regime,
        "liquidity": liquidity,
        "usd_trend": usd_trend,
        "confidence": overall,
    }


# ---------------------------------------------------------------------------
# 可选：从 akshare 拉取宏观数据后调用 detect_regime
# ---------------------------------------------------------------------------
def fetch_macro_series(days: int = 60) -> dict[str, pd.Series | None]:
    """
    尝试用 akshare 拉取 VIX、DXY、2Y 收益率历史序列（若接口存在）.
    返回 {"vix": Series|None, "dxy": Series|None, "yield_2y": Series|None}.
    """
    end = datetime.now()
    start = end - timedelta(days=days)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    out: dict[str, pd.Series | None] = {"vix": None, "dxy": None, "yield_2y": None}

    try:
        import akshare as ak
    except ImportError:
        logger.debug("akshare not available for macro fetch")
        return out

    # VIX
    try:
        df = ak.index_vix(symbol="VIX")
        if df is not None and not df.empty:
            df = df.rename(columns=lambda c: str(c).strip())
            date_col = next((c for c in ["日期", "date", "时间"] if c in df.columns), df.columns[0])
            value_col = next((c for c in ["收盘", "收盘价", "当前价", "最新价", "value"] if c in df.columns), None)
            if value_col:
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                df = df.dropna(subset=[date_col]).sort_values(date_col).tail(days * 2)
                out["vix"] = df.set_index(date_col)[value_col]
    except Exception as e:
        logger.debug("fetch VIX failed: %s", e)

    # DXY / 美元指数（部分 akshare 版本为 index_investing_global 或类似）
    try:
        # 尝试常见接口
        if hasattr(ak, "index_investing_global"):
            df = ak.index_investing_global(
                country="美国", index_name="美元指数",
                period="每日", start_date=start_str.replace("-", ""), end_date=end_str.replace("-", "")
            )
        elif hasattr(ak, "fx_spot_quote"):
            # 备用：部分版本用 fx
            df = getattr(ak, "fx_spot_quote", lambda: None)()
        else:
            df = None
        if df is not None and not df.empty:
            df = df.rename(columns=lambda c: str(c).strip())
            date_col = next((c for c in ["日期", "date", "时间"] if c in df.columns), df.columns[0])
            value_col = next((c for c in ["收盘", "收盘价", "当前价", "最新价", "value", "价格"] if c in df.columns), None)
            if value_col and value_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                df = df.dropna(subset=[date_col]).sort_values(date_col).tail(days * 2)
                out["dxy"] = df.set_index(date_col)[value_col]
    except Exception as e:
        logger.debug("fetch DXY failed: %s", e)

    # 2Y 美债收益率（akshare 常见为 bond_usa_yield 等，返回截面或历史）
    try:
        if hasattr(ak, "bond_usa_yield"):
            df = ak.bond_usa_yield()
        elif hasattr(ak, "bond_us_treasury_yield"):
            df = ak.bond_us_treasury_yield()
        else:
            df = None
        if df is not None and not df.empty:
            df = df.rename(columns=lambda c: str(c).strip())
            date_col = next((c for c in ["日期", "date"] if c in df.columns), df.columns[0])
            col_2y = next((c for c in df.columns if c != date_col and ("2" in c or "2年" in c)), None)
            if col_2y is None and len(df.columns) > 1:
                col_2y = df.columns[1]
            if col_2y:
                s = pd.to_numeric(df[col_2y], errors="coerce")
                if date_col in df.columns:
                    df = df.dropna(subset=[date_col]).copy()
                    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                    df = df.dropna(subset=[date_col]).sort_values(date_col)
                    out["yield_2y"] = df.set_index(date_col)[col_2y]
                elif s.notna().any():
                    out["yield_2y"] = s
    except Exception as e:
        logger.debug("fetch 2Y yield failed: %s", e)

    return out


def detect_regime_from_fetch(days: int = 60, liquidity_lookback_days: int = 22) -> dict[str, str]:
    """
    先 fetch_macro_series(days)，再调用 detect_regime.
    无数据时各维度为 unknown，confidence 为 low.
    """
    data = fetch_macro_series(days=days)
    return detect_regime(
        vix_series=data.get("vix"),
        dxy_series=data.get("dxy"),
        yield_2y_series=data.get("yield_2y"),
        liquidity_lookback_days=liquidity_lookback_days,
    )
