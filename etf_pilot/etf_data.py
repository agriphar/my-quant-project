# -*- coding: utf-8 -*-
"""ETF 数据获取与指标计算（RSI、布林带、多因子信号、建议仓位）。"""
from pathlib import Path
from datetime import datetime, timedelta
from typing import Callable
import pandas as pd
import numpy as np
import akshare as ak

from config.settings import RSI_PERIOD, BB_PERIOD, BB_STD
from strategy import (
    get_asset_type,
    compute_signal,
    compute_deviation,
    check_chase_high,
    compute_addon_suggestion,
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
    """从 data/ETF汇总.xlsx 读取 ETF 列表，返回 代码、名称、指数简称、类型(Core/Tactical)。"""
    from strategy.asset_type import get_asset_type

    ensure_data_dir()
    if not ETF_LIST_PATH.exists():
        df = pd.DataFrame(DEFAULT_ETF_LIST)
        df["指数简称"] = "其他"
        df["类型"] = df["名称"].map(get_asset_type)
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
    # 类型：Excel 列 类型/type/资产类型 优先；否则使用自动分类（classify_etfs + 缓存）
    type_col = next((c for c in df.columns if str(c).strip() in ("类型", "type", "资产类型")), None)
    if type_col is not None:
        df["类型"] = df.apply(lambda r: get_asset_type(r.get("名称", ""), r.get(type_col)), axis=1)
    else:
        try:
            from strategy.classification import get_cached_classification
            df = get_cached_classification(df)
        except Exception:
            df["类型"] = df["名称"].map(lambda n: get_asset_type(n, None))
    df = df.loc[
        df["代码"].notna()
        & (df["代码"].astype(str).str.len() >= 5)
        & (df["代码"].astype(str).str.lower() != "nan")
    ]
    return df[["代码", "名称", "指数简称", "类型"]].dropna(subset=["代码"]).drop_duplicates(subset=["代码"])


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


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """ATR = SMA(TR, period), TR = max(H-L, |H-prev_C|, |L-prev_C|)。"""
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    return tr.rolling(period, min_periods=1).mean()


def fetch_etf_daily(
    symbol: str,
    days: int = 30,
    ma_short: int = 5,
    ma_long: int = 20,
) -> pd.DataFrame | None:
    """获取单只 ETF 日线并计算 MA5/20/60/200、RSI、布林带。失败返回 None。"""
    end_date = datetime.now()
    need_days = max(days, 280)  # MA200 需要约 250 根 K 线
    start_date = end_date - timedelta(days=need_days)
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
    df = df.sort_values("日期").tail(max(days + 30, 250)).reset_index(drop=True)
    close = df["收盘"]
    df["MA_short"] = close.rolling(ma_short, min_periods=1).mean()
    df["MA_long"] = close.rolling(ma_long, min_periods=1).mean()
    df["MA20"] = close.rolling(20, min_periods=1).mean()
    df["MA60"] = close.rolling(60, min_periods=1).mean()
    df["MA200"] = close.rolling(200, min_periods=1).mean()
    df["RSI"] = _rsi(close, RSI_PERIOD)
    mid, upper, lower = _bollinger(close, BB_PERIOD, BB_STD)
    df["BB_upper"], df["BB_lower"] = upper, lower
    return df


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
        asset_type = row.get("类型") or get_asset_type(name, None)
        err_msg = None
        try:
            hist = get_hist(code, days, ma_short, ma_long)
        except Exception as e:
            hist = None
            err_msg = str(e)[:80]
        if hist is None or hist.empty:
            rows.append({
                "代码": code, "名称": name, "指数简称": category, "类型": asset_type,
                "最新价": None, "涨跌幅": None, "MA_short": None, "MA_long": None,
                "RSI": None, "BB_lower": None, "偏离度": None, "追高提示": "", "补仓建议": "",
                "信号": "—", "建议仓位": "—",
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
        signal = compute_signal(asset_type, last, prev, vol_avg)
        dev_pct = compute_deviation(float(close) if close is not None else None, float(last["MA20"]) if last.get("MA20") is not None else None)
        chase = check_chase_high(dev_pct)
        high_20 = hist["收盘"].tail(20).max() if len(hist) >= 20 else None
        addon = compute_addon_suggestion(asset_type, float(close) if close is not None else None, last.get("MA200"), high_20)
        ret = hist["收盘"].pct_change().dropna().tail(20)
        vol = float(ret.std()) if len(ret) > 0 else None
        if vol is not None:
            volatilities.append(vol)
        rows.append({
            "代码": code, "名称": name, "指数简称": category, "类型": asset_type,
            "最新价": round(float(close), 4),
            "涨跌幅": round(pct, 2) if pct is not None else None,
            "MA_short": round(float(last["MA_short"]), 4) if last.get("MA_short") is not None else None,
            "MA_long": round(float(last["MA_long"]), 4) if last.get("MA_long") is not None else None,
            "RSI": round(float(last["RSI"]), 1) if last.get("RSI") is not None and not pd.isna(last["RSI"]) else None,
            "BB_lower": round(float(last["BB_lower"]), 4) if last.get("BB_lower") is not None and not pd.isna(last.get("BB_lower")) else None,
            "偏离度": dev_pct,
            "追高提示": chase,
            "补仓建议": addon,
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


def fetch_etf_hist_for_backtest(symbol: str, years: int = 3) -> pd.DataFrame | None:
    """获取单只 ETF 过去 years 年的日线及 MA20/60/200、RSI、布林带，供回测用。"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years * 365 + 100)
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
    df = _normalize_hist(raw)
    if df is None or df.empty:
        return None
    df = df.sort_values("日期").reset_index(drop=True)
    # 回测需「昨日信号、今日开盘执行」及 ATR/吊灯止损，故保留开盘、最高、最低
    raw["日期"] = pd.to_datetime(raw["日期"])
    for col in ["开盘", "最高", "最低"]:
        if col in raw.columns:
            aux = raw[["日期", col]].drop_duplicates("日期")
            df = df.merge(aux, on="日期", how="left")
        else:
            df[col] = np.nan
    if "开盘" not in df.columns:
        df["开盘"] = np.nan
    if "最高" not in df.columns:
        df["最高"] = df["收盘"]
    if "最低" not in df.columns:
        df["最低"] = df["收盘"]
    close = df["收盘"]
    df["MA_long"] = close.rolling(20, min_periods=1).mean()
    df["MA20"] = df["MA_long"]
    df["MA60"] = close.rolling(60, min_periods=1).mean()
    df["MA200"] = close.rolling(200, min_periods=1).mean()
    df["RSI"] = _rsi(close, RSI_PERIOD)
    _, _, lower = _bollinger(close, BB_PERIOD, BB_STD)
    df["BB_lower"] = lower
    return df


def get_universe_20d_ranks(
    etf_codes: list[str],
    years: int = 3,
) -> pd.DataFrame | None:
    """
    计算全市场 ETF 过去 20 日涨幅的每日排名，供回测「相对强度」使用。
    返回 DataFrame：列 日期、代码、20d_return、rank_pct。
    rank_pct 为 0~1，1 表示涨幅排名第一（前 25% 为 rank_pct >= 0.75，跌出前 50% 为 rank_pct < 0.5）。
    """
    if not etf_codes:
        return None
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years * 365 + 100)
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    all_series = []
    for code in etf_codes:
        code = str(code).strip()
        try:
            raw = ak.fund_etf_hist_em(
                symbol=code,
                period="daily",
                start_date=start_str,
                end_date=end_str,
                adjust="qfq",
            )
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        raw = raw.rename(columns=lambda c: str(c).strip())
        close_col = next((c for c in ["收盘", "收盘价"] if c in raw.columns), None)
        date_col = "日期" if "日期" in raw.columns else raw.columns[0]
        if not close_col:
            continue
        df = raw[[date_col, close_col]].copy()
        df = df.rename(columns={date_col: "日期", close_col: "收盘"})
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.sort_values("日期").dropna(subset=["收盘"])
        if len(df) < 25:
            continue
        df["20d_return"] = df["收盘"].pct_change(20)
        df["代码"] = code
        all_series.append(df[["日期", "代码", "20d_return"]])
    if not all_series:
        return None
    combined = pd.concat(all_series, ignore_index=True)
    combined = combined.dropna(subset=["20d_return"]).drop_duplicates(subset=["日期", "代码"], keep="last")
    # 按日期分组，按 20d_return 降序排名，rank_pct 为 0~1，1 表示当日涨幅最强（前 25% 即 rank_pct >= 0.75）
    def rank_group(g: pd.DataFrame) -> pd.DataFrame:
        g = g.copy()
        r = g["20d_return"].rank(ascending=False, method="average")
        n = len(g)
        g["rank_pct"] = (n + 1 - r) / n if n else 0
        return g
    ranked = combined.groupby("日期", as_index=False).apply(rank_group).reset_index(drop=True)
    return ranked[["日期", "代码", "20d_return", "rank_pct"]]


def get_rsr_panel(etf_codes: list[str], years: int = 3, atr_period: int = 14) -> pd.DataFrame | None:
    """
    多因子轮动用全市场 panel：OHLC + MA20 + 20日涨跌幅 + 20日收益标准差 + 动量效率(涨幅/标准差) + ATR + 排名。
    返回列：日期、代码、开盘、最高、最低、收盘、MA20、20d_return、20d_std、momentum_eff、ATR、rank。
    rank 按 momentum_eff 降序，1 = 涨势最稳（风险调整后动量最优）。
    """
    if not etf_codes:
        return None
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years * 365 + 100)
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    need = ["日期", "开盘", "最高", "最低", "收盘"]
    all_dfs = []
    for code in etf_codes:
        code = str(code).strip()
        try:
            raw = ak.fund_etf_hist_em(
                symbol=code,
                period="daily",
                start_date=start_str,
                end_date=end_str,
                adjust="qfq",
            )
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        raw = raw.rename(columns=lambda c: str(c).strip())
        if not all(k in raw.columns for k in need):
            continue
        df = raw[need].copy()
        df["日期"] = pd.to_datetime(df["日期"])
        df["代码"] = code
        df = df.sort_values("日期").dropna(subset=["收盘"])
        if len(df) < 25:
            continue
        close = df["收盘"]
        high = df["最高"]
        low = df["最低"]
        df["MA20"] = close.rolling(20, min_periods=1).mean()
        df["20d_return"] = close.pct_change(20)
        daily_ret = close.pct_change()
        df["20d_std"] = daily_ret.rolling(20, min_periods=1).std()
        # 动量效率 = 20日涨幅 / 20日波动，避免除零
        df["momentum_eff"] = df["20d_return"] / (df["20d_std"].replace(0, np.nan).fillna(1e-8))
        df["ATR"] = _atr(high, low, close, period=atr_period)
        all_dfs.append(df)
    if not all_dfs:
        return None
    panel = pd.concat(all_dfs, ignore_index=True)
    panel = panel.dropna(subset=["20d_return", "momentum_eff"]).drop_duplicates(subset=["日期", "代码"], keep="last")
    # 按 momentum_eff 降序排名，1 = 风险调整后动量最佳
    panel["rank"] = panel.groupby("日期")["momentum_eff"].rank(ascending=False, method="min").astype(int)
    return panel


def get_equal_weight_panel(etf_codes: list[str], years: int = 3) -> pd.DataFrame | None:
    """
    等权再平衡用 panel：仅 5 只标的的 日期、代码、开盘、收盘，按日期对齐（仅保留全部标的有数据的交易日）。
    """
    if not etf_codes:
        return None
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years * 365 + 100)
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    need = ["日期", "开盘", "收盘"]
    all_dfs = []
    for code in etf_codes:
        code = str(code).strip()
        try:
            raw = ak.fund_etf_hist_em(
                symbol=code,
                period="daily",
                start_date=start_str,
                end_date=end_str,
                adjust="qfq",
            )
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        raw = raw.rename(columns=lambda c: str(c).strip())
        close_col = next((c for c in ["收盘", "收盘价"] if c in raw.columns), None)
        open_col = next((c for c in ["开盘"] if c in raw.columns), None)
        date_col = "日期" if "日期" in raw.columns else raw.columns[0]
        if not close_col or not date_col:
            continue
        df = raw[[date_col, close_col]].copy()
        df = df.rename(columns={date_col: "日期", close_col: "收盘"})
        if open_col and open_col in raw.columns:
            df["开盘"] = raw[open_col].values
        else:
            df["开盘"] = df["收盘"]
        df["日期"] = pd.to_datetime(df["日期"])
        df["代码"] = code
        df = df.sort_values("日期").dropna(subset=["收盘"])
        if len(df) < 20:
            continue
        all_dfs.append(df[["日期", "代码", "开盘", "收盘"]])
    if len(all_dfs) < len(etf_codes):
        return None
    panel = pd.concat(all_dfs, ignore_index=True)
    # 仅保留所有代码都存在的日期
    dates_per_code = panel.groupby("代码")["日期"].apply(set)
    common_dates = set(dates_per_code.iloc[0])
    for s in dates_per_code.iloc[1:]:
        common_dates &= s
    if not common_dates:
        return None
    panel = panel.loc[panel["日期"].isin(common_dates)].sort_values(["日期", "代码"]).reset_index(drop=True)
    return panel


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
