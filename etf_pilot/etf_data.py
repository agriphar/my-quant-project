# -*- coding: utf-8 -*-
"""ETF 数据获取与指标计算（RSI、布林带、多因子信号、建议仓位）。"""
from pathlib import Path
from datetime import datetime, timedelta
from typing import Callable
import pandas as pd
import numpy as np
import akshare as ak

from config.settings import (
    RSI_PERIOD,
    BB_PERIOD,
    BB_STD,
    RSI_OVERBOUGHT,
    RSI_BULLISH_MAX,
    VOL_SHRINK_RATIO,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
ETF_LIST_PATH = DATA_DIR / "ETF汇总.xlsx"

DEFAULT_ETF_LIST = [
    {"代码": "513100", "名称": "纳指ETF"},
    {"代码": "513500", "名称": "标普500ETF"},
    {"代码": "159941", "名称": "纳指100ETF"},
    {"代码": "513030", "名称": "恒生科技ETF"},
    {"代码": "513050", "名称": "中概互联网ETF"},
]


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_etf_list() -> pd.DataFrame:
    """从 data/ETF汇总.xlsx 读取 ETF 列表，返回 代码、名称、指数简称。"""
    ensure_data_dir()
    if not ETF_LIST_PATH.exists():
        df = pd.DataFrame(DEFAULT_ETF_LIST)
        df["指数简称"] = "其他"
        df.to_excel(ETF_LIST_PATH, index=False)
        return df
    df = pd.read_excel(ETF_LIST_PATH, header=1)
    df = df.rename(columns=lambda c: str(c).strip())
    if "产品代码" in df.columns and "跟踪产品" in df.columns:
        df["代码"] = df["产品代码"].astype(str).str.strip().str.upper()
        df["代码"] = df["代码"].str.replace(r"\.(SH|SZ)$", "", regex=True)
        df["名称"] = df["跟踪产品"].astype(str).str.strip()
        if "指数简称" in df.columns:
            df["指数简称"] = df["指数简称"].ffill()
        else:
            df["指数简称"] = "其他"
    else:
        for c in df.columns:
            if str(c).strip() in ("代码", "code", "产品代码"):
                df = df.rename(columns={c: "代码"})
            elif str(c).strip() in ("名称", "name", "跟踪产品"):
                df = df.rename(columns={c: "名称"})
        if "指数简称" not in df.columns:
            df["指数简称"] = "其他"
    df = df.loc[
        df["代码"].notna()
        & (df["代码"].astype(str).str.len() >= 5)
        & (df["代码"].astype(str).str.lower() != "nan")
    ]
    return df[["代码", "名称", "指数简称"]].dropna(subset=["代码"]).drop_duplicates(subset=["代码"])


def _normalize_hist(raw: pd.DataFrame) -> pd.DataFrame | None:
    """统一列为 日期、收盘、成交量。"""
    if raw is None or raw.empty:
        return None
    raw = raw.rename(columns=lambda c: str(c).strip())
    date_col = "日期" if "日期" in raw.columns else (raw.columns[0] if len(raw.columns) else None)
    close_col = next((c for c in ["收盘", "收盘价"] if c in raw.columns), None)
    if not date_col or not close_col:
        return None
    df = raw.rename(columns={date_col: "日期", close_col: "收盘"})
    df["成交量"] = raw["成交量"] if "成交量" in raw.columns else np.nan
    df["日期"] = pd.to_datetime(df["日期"])
    return df[["日期", "收盘", "成交量"]].copy()


def _rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _bollinger(close: pd.Series, period: int = BB_PERIOD, num_std: float = BB_STD):
    mid = close.rolling(period, min_periods=1).mean()
    std = close.rolling(period, min_periods=1).std()
    return mid, mid + num_std * std, mid - num_std * std


def fetch_etf_daily(
    symbol: str,
    days: int = 30,
    ma_short: int = 5,
    ma_long: int = 20,
) -> pd.DataFrame | None:
    """获取单只 ETF 日线并计算 MA、RSI、布林带。失败返回 None。"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=max(days, 60))
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    try:
        raw = ak.fund_etf_hist_em(
            symbol=symbol.strip(),
            period="daily",
            start_date=start_str,
            end_date=end_str,
            adjust="qfq",
        )
    except Exception:
        return None
    if raw is None or raw.empty:
        return None
    df = _normalize_hist(raw)
    if df is None or df.empty:
        return None
    df = df.sort_values("日期").tail(days + 30).reset_index(drop=True)
    close = df["收盘"]
    df["MA_short"] = close.rolling(ma_short, min_periods=1).mean()
    df["MA_long"] = close.rolling(ma_long, min_periods=1).mean()
    df["RSI"] = _rsi(close, RSI_PERIOD)
    mid, upper, lower = _bollinger(close, BB_PERIOD, BB_STD)
    df["BB_upper"], df["BB_lower"] = upper, lower
    return df


def _composite_signal(last: pd.Series, prev_vol_avg: float) -> str:
    """多因子综合信号：买入 / 持有 / 减仓。"""
    close = last["收盘"]
    ma_long = last["MA_long"]
    rsi = last["RSI"]
    bb_lower = last.get("BB_lower")
    vol = last.get("成交量") or 0
    if pd.isna(close) or pd.isna(ma_long):
        return "持有"
    if rsi is not None and not pd.isna(rsi) and rsi > RSI_OVERBOUGHT:
        return "减仓"
    if close < ma_long:
        return "减仓"
    if bb_lower is not None and not pd.isna(bb_lower) and close <= bb_lower * 1.002 and prev_vol_avg > 0 and vol < prev_vol_avg * VOL_SHRINK_RATIO:
        return "买入"
    if rsi is not None and not pd.isna(rsi) and close > ma_long and rsi < RSI_BULLISH_MAX:
        return "买入"
    return "持有"


def _suggested_position(volatility: float, volatilities: list[float]) -> str:
    """根据波动率：波动大仓位轻，平稳仓位重。"""
    if not volatilities or volatility is None or pd.isna(volatility):
        return "—"
    arr = np.array([v for v in volatilities if v is not None and not pd.isna(v)])
    if len(arr) == 0:
        return "—"
    pct = (arr < volatility).mean() * 100
    if pct >= 75:
        return "高(60-80%)"
    if pct >= 40:
        return "中(40-60%)"
    return "低(20-40%)"


def build_monitor_table_advanced(
    etf_list: pd.DataFrame,
    days: int = 30,
    ma_short: int = 5,
    ma_long: int = 20,
    fetcher: Callable[[str, int, int, int], pd.DataFrame | None] | None = None,
) -> pd.DataFrame:
    """拉取日线、计算指标与建议仓位；单只失败则该行填错误信息不崩溃。"""
    get_hist = fetcher or (lambda s, d, ms, ml: fetch_etf_daily(s, d, ms, ml))
    rows = []
    volatilities: list[float] = []
    for _, row in etf_list.iterrows():
        code = str(row["代码"]).strip()
        name = row.get("名称", code)
        category = row.get("指数简称", "其他")
        err_msg = None
        try:
            hist = get_hist(code, days, ma_short, ma_long)
        except Exception as e:
            hist = None
            err_msg = str(e)[:80]
        if hist is None or hist.empty:
            rows.append({
                "代码": code, "名称": name, "指数简称": category,
                "最新价": None, "涨跌幅": None, "MA_short": None, "MA_long": None,
                "RSI": None, "BB_lower": None, "信号": "—", "建议仓位": "—",
                "错误": err_msg or "获取失败",
            })
            continue
        last = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) >= 2 else last
        close = last["收盘"]
        prev_close = prev["收盘"]
        pct = (float((close - prev_close) / prev_close * 100)) if prev_close and prev_close != 0 else None
        vol_avg = hist["成交量"].replace(0, np.nan).dropna().tail(5).mean() if "成交量" in hist.columns else 0
        vol_avg = vol_avg if not pd.isna(vol_avg) else 0
        signal = _composite_signal(last, vol_avg)
        ret = hist["收盘"].pct_change().dropna().tail(20)
        vol = float(ret.std()) if len(ret) > 0 else None
        if vol is not None:
            volatilities.append(vol)
        rows.append({
            "代码": code, "名称": name, "指数简称": category,
            "最新价": round(float(close), 4),
            "涨跌幅": round(pct, 2) if pct is not None else None,
            "MA_short": round(float(last["MA_short"]), 4) if last.get("MA_short") is not None else None,
            "MA_long": round(float(last["MA_long"]), 4) if last.get("MA_long") is not None else None,
            "RSI": round(float(last["RSI"]), 1) if last.get("RSI") is not None and not pd.isna(last["RSI"]) else None,
            "BB_lower": round(float(last["BB_lower"]), 4) if last.get("BB_lower") is not None and not pd.isna(last.get("BB_lower")) else None,
            "信号": signal,
            "建议仓位": None,
            "错误": None,
            "_vol": vol,
        })
    for r in rows:
        if r.get("建议仓位") is None and r.get("错误") is None:
            r["建议仓位"] = _suggested_position(r.pop("_vol", None), volatilities)
        r.pop("_vol", None)
    return pd.DataFrame(rows)


def get_etf_hist_for_chart(
    symbol: str,
    days: int = 60,
    ma_short: int = 5,
    ma_long: int = 20,
) -> pd.DataFrame | None:
    """获取单只 ETF 的 OHLC + 均线 + 布林带，用于 Plotly K 线图。"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=max(days, 90))
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    try:
        raw = ak.fund_etf_hist_em(
            symbol=symbol.strip(),
            period="daily",
            start_date=start_str,
            end_date=end_str,
            adjust="qfq",
        )
    except Exception:
        return None
    if raw is None or raw.empty:
        return None
    raw = raw.rename(columns=lambda c: str(c).strip())
    need = ["日期", "开盘", "最高", "最低", "收盘"]
    if not all(k in raw.columns for k in need):
        return None
    df = raw[need + (["成交量"] if "成交量" in raw.columns else [])].copy()
    if "成交量" not in df.columns:
        df["成交量"] = np.nan
    df["日期"] = pd.to_datetime(df["日期"])
    df = df.sort_values("日期").tail(days + 30).reset_index(drop=True)
    close = df["收盘"]
    df["MA_short"] = close.rolling(ma_short, min_periods=1).mean()
    df["MA_long"] = close.rolling(ma_long, min_periods=1).mean()
    _, up, lo = _bollinger(close, BB_PERIOD, BB_STD)
    df["BB_upper"], df["BB_lower"] = up, lo
    return df
