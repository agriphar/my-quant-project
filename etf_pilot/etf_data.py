# -*- coding: utf-8 -*-
"""ETF 数据获取与监控表编排（委托 market_regime、signal_engine、decision_engine）。"""
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Callable
import pandas as pd
import numpy as np
import akshare as ak

from config.settings import RSI_PERIOD, BB_PERIOD, BB_STD
from market_regime.trend import compute_trend_classification, REGRESSION_WINDOW
from signal_engine.indicators import rsi, bollinger, atr, pct_from_1y_high_low, bias_pct
from decision_engine.daily_action import (
    compute_daily_action,
    compute_action_frequency,
    compute_signal_accuracy_30d,
)
from decision_engine.daily_action import SIGNAL_LOOKBACK_DAYS
from risk_engine import drawdown_15pct_value  # 向后兼容：原 etf_data 对外提供

DATA_DIR = Path(__file__).resolve().parent / "data"
ETF_LIST_PATH = DATA_DIR / "ETF汇总.xlsx"
logger = logging.getLogger(__name__)

# 场内基金当日净值页缓存，用于历史净值接口返回全 NaN 时的兜底（仅能拿到最近 1～2 个交易日）
_daily_em_cache: pd.DataFrame | None = None
_daily_em_cache_ts: float = 0
DAILY_EM_CACHE_TTL = 300
_nav_warned_codes: set[str] = set()

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
            from market_regime.classification import get_cached_classification
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


# 溢价统计用常量（get_etf_premium_stats、build_monitor_table 使用）
PREMIUM_AVG_DAYS = 22
PREMIUM_PCTILE_DAYS = 60
PREMIUM_FETCH_DAYS = 100


def _get_nav_fallback_daily_em(symbol: str) -> pd.DataFrame | None:
    """当 fund_etf_fund_info_em 返回的净值列全为 NaN 时，用场内基金当日净值页兜底，返回 1～2 天的 日期+单位净值。"""
    global _daily_em_cache, _daily_em_cache_ts
    now = time.time()
    if _daily_em_cache is None or (now - _daily_em_cache_ts) > DAILY_EM_CACHE_TTL:
        try:
            _daily_em_cache = ak.fund_etf_fund_daily_em()
            _daily_em_cache_ts = now
        except Exception as e:
            logger.debug("fund_etf_fund_daily_em 失败: %s", e)
            return None
    if _daily_em_cache is None or _daily_em_cache.empty:
        return None
    df = _daily_em_cache.rename(columns=lambda c: str(c).strip())
    code_col = "基金代码"
    if code_col not in df.columns:
        return None
    row = df[df[code_col].astype(str).str.strip() == symbol.strip()]
    if row.empty:
        return None
    row = row.iloc[0]
    rows = []
    for col in df.columns:
        if "单位净值" not in col or "累计" in col:
            continue
        val = row.get(col)
        if pd.isna(val):
            continue
        try:
            v = float(val)
            if v <= 0:
                continue
        except (TypeError, ValueError):
            continue
        date_part = col.replace("-单位净值", "").strip()
        if not date_part:
            continue
        try:
            dt = pd.to_datetime(date_part, errors="coerce")
            if pd.isna(dt):
                continue
            rows.append({"日期": dt.normalize(), "单位净值": v})
        except Exception:
            continue
    if not rows:
        return None
    out = pd.DataFrame(rows).drop_duplicates(subset=["日期"]).sort_values("日期").reset_index(drop=True)
    return out[["日期", "单位净值"]]


def get_etf_nav_hist(symbol: str, days: int = 70) -> pd.DataFrame | None:
    """获取单只 ETF 历史单位净值，用于计算历史溢价率。返回 日期、单位净值。
    若接口无「单位净值」则尝试「基金净值」「net_value」等；均无或全为空则返回 None。
    API 失败或返回空时最多重试 3 次，每次间隔 0.5 秒。
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=int(days * 1.8) + 20)
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    raw = None
    last_exc = None
    for attempt in range(3):
        try:
            raw = ak.fund_etf_fund_info_em(
                fund=symbol.strip(),
                start_date=start_str,
                end_date=end_str,
            )
        except Exception as e:
            raw = None
            last_exc = e
            logger.debug("get_etf_nav_hist %s attempt %s failed: %s", symbol, attempt + 1, e)
        if raw is not None and not raw.empty:
            break
        if attempt < 2:
            time.sleep(0.5)
    if raw is None or raw.empty:
        logger.info(
            "get_etf_nav_hist %s: 接口无数据 (raw=%s)%s",
            symbol,
            "empty" if raw is not None else "None",
            f", last_error={last_exc!r}" if last_exc else "",
        )
        return None
    raw = raw.rename(columns=lambda c: str(c).strip())
    date_candidates = ["净值日期", "日期", "date", "披露日期"]
    date_col = next((c for c in date_candidates if c in raw.columns), None)
    nav_candidates = ["单位净值", "基金净值", "net_value", "nav", "累计净值"]
    nav_col = None
    for c in nav_candidates:
        if c not in raw.columns:
            continue
        s = pd.to_numeric(raw[c], errors="coerce")
        if s.notna().any() and (s > 0).any():
            nav_col = c
            break
    if not date_col or not nav_col:
        fallback = _get_nav_fallback_daily_em(symbol)
        if fallback is not None and not fallback.empty:
            logger.debug("get_etf_nav_hist %s: 使用场内当日净值页兜底 (%d 条)", symbol, len(fallback))
            return fallback
        global _nav_warned_codes
        if symbol not in _nav_warned_codes:
            _nav_warned_codes.add(symbol)
            sample = {}
            for c in ["单位净值", "累计净值"]:
                if c in raw.columns:
                    sample[c] = raw[c].head(5).tolist()
            logger.warning(
                "get_etf_nav_hist %s: 缺少日期或净值列 (date_col=%s, nav_col=%s), columns=%s, sample=%s",
                symbol,
                date_col,
                nav_col,
                raw.columns.tolist(),
                sample,
            )
        return None
    df = raw[[date_col, nav_col]].copy()
    df["日期"] = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
    df = df.dropna(subset=["日期", nav_col])
    df[nav_col] = pd.to_numeric(df[nav_col], errors="coerce")
    df = df[df[nav_col].notna() & (df[nav_col] > 0)].sort_values("日期").tail(days).reset_index(drop=True)
    if df.empty:
        logger.debug("get_etf_nav_hist %s: 清洗后无有效行", symbol)
        return None
    return df[["日期", nav_col]].rename(columns={nav_col: "单位净值"})


def get_etf_premium_stats(
    hist: pd.DataFrame,
    nav_hist: pd.DataFrame | None,
    current_premium: float | None,
    code: str | None = None,
) -> tuple[float | None, float | None, float | None, int, bool, bool]:
    """
    以场内交易日为主表 left 关联净值，关联后对单位净值 ffill 填补滞后披露。
    合并前对 hist、nav_hist 分别 sort_values('日期').ffill()；算完溢价率后再 dropna。
    只要有 >=1 个有效值即计算分位；valid_count<5 时返回 sample_very_small=True 供界面提醒。
    返回 (avg_22, pct_60, std_22, valid_count, no_premium_data, sample_very_small)。
    """
    if hist is None or hist.empty or "收盘" not in hist.columns or current_premium is None or pd.isna(current_premium):
        return None, None, None, 0, True, False
    if nav_hist is None or nav_hist.empty or "单位净值" not in nav_hist.columns:
        return None, None, None, 0, True, False
    hist = hist[["日期", "收盘"]].copy()
    hist["日期"] = pd.to_datetime(hist["日期"]).dt.normalize()
    hist = hist.sort_values("日期")
    hist["收盘"] = hist["收盘"].astype(float).ffill().bfill()
    nav_hist = nav_hist.copy()
    nav_hist["日期"] = pd.to_datetime(nav_hist["日期"]).dt.normalize()
    nav_hist = nav_hist.sort_values("日期")
    nav_hist["单位净值"] = nav_hist["单位净值"].astype(float).ffill().bfill()
    merged = hist.merge(nav_hist, on="日期", how="left")
    merged["单位净值"] = merged["单位净值"].ffill()
    if merged["单位净值"].isna().all() or (merged["单位净值"] <= 0).all():
        if code is not None:
            print(f"[Auditor] {code} Columns (hist): {hist.columns.tolist()}")
            print(f"[Auditor] {code} Columns (nav): {nav_hist.columns.tolist()}")
        return None, None, None, 0, True, False
    merged["溢价率"] = np.nan
    valid = merged["单位净值"].notna() & (merged["单位净值"] > 0)
    merged.loc[valid, "溢价率"] = (
        (merged.loc[valid, "收盘"].astype(float) - merged.loc[valid, "单位净值"].astype(float))
        / merged.loc[valid, "单位净值"].astype(float) * 100
    )
    merged["溢价率"] = merged["溢价率"].replace([np.inf, -np.inf], np.nan)
    merged = merged.sort_values("日期").ffill()
    merged_60 = merged.tail(PREMIUM_PCTILE_DAYS)
    temp_series = merged_60["溢价率"].dropna()
    if len(temp_series) == 0:
        merged_250 = merged.tail(250)
        temp_series = merged_250["溢价率"].dropna()
    valid_count = int(len(temp_series))
    no_premium_data = valid_count == 0
    sample_very_small = 1 <= valid_count < 5
    if no_premium_data and code is not None:
        print(f"[Auditor] {code} Columns (hist): {hist.columns.tolist()}")
        print(f"[Auditor] {code} Columns (nav): {nav_hist.columns.tolist()}")
    merged = merged_60
    if len(merged) < 1:
        return None, None, None, valid_count, no_premium_data, sample_very_small
    tail22 = merged["溢价率"].tail(PREMIUM_AVG_DAYS).ffill().bfill().fillna(0)
    avg_22 = float(tail22.mean())
    std_22 = float(tail22.std()) if len(tail22) > 1 and tail22.std() and not pd.isna(tail22.std()) else None
    pct_60 = None
    if valid_count >= 1:
        pct_60 = float((temp_series <= float(current_premium)).mean() * 100)
    return (
        round(avg_22, 2),
        round(pct_60, 1) if pct_60 is not None and not (isinstance(pct_60, float) and pd.isna(pct_60)) else None,
        round(std_22, 4) if std_22 is not None else None,
        valid_count,
        no_premium_data,
        sample_very_small,
    )


def get_etf_spot_premium_map(etf_codes: list[str]) -> dict[str, float]:
    """
    通过东方财富 fund_etf_spot_em 获取 IOPV 实时估值，计算溢价率。
    溢价率 = (当前市价 - IOPV) / IOPV * 100%
    返回 {代码: 溢价率%}，缺失或无效的代码不出现或可后续用 None 表示。
    """
    codes_set = {str(c).strip() for c in etf_codes if c}
    out = {}
    try:
        spot = ak.fund_etf_spot_em()
    except Exception:
        return out
    if spot is None or spot.empty:
        return out
    spot = spot.rename(columns=lambda c: str(c).strip())
    price_col = "最新价"
    iopv_col = "IOPV实时估值"
    code_col = "代码"
    if code_col not in spot.columns or price_col not in spot.columns or iopv_col not in spot.columns:
        return out
    for _, r in spot.iterrows():
        code = str(r.get(code_col, "")).strip()
        if code not in codes_set:
            continue
        try:
            price = r.get(price_col)
            iopv = r.get(iopv_col)
            if pd.isna(price) or pd.isna(iopv) or iopv is None or float(iopv) <= 0:
                continue
            price, iopv = float(price), float(iopv)
            premium = (price - iopv) / iopv * 100
            out[code] = round(premium, 2)
        except (TypeError, ValueError):
            continue
    missing = codes_set - set(out.keys())
    for code in missing:
        try:
            nav_hist = get_etf_nav_hist(code, 10)
            hist = fetch_etf_daily(code, days=10)
            if nav_hist is not None and not nav_hist.empty and hist is not None and not hist.empty:
                last_nav = nav_hist.iloc[-1]["单位净值"]
                if "收盘" in hist.columns and last_nav and float(last_nav) > 0:
                    last_close = hist.iloc[-1]["收盘"]
                    if last_close is not None and not pd.isna(last_close):
                        premium = (float(last_close) - float(last_nav)) / float(last_nav) * 100
                        out[code] = round(premium, 2)
                        logger.debug(
                            "get_etf_spot_premium_map %s: 使用日线+最近净值估算溢价 (无 IOPV)",
                            code,
                        )
        except Exception:
            continue
    return out


def format_premium_with_bar(premium_pct: float | None, pctile_60: float | None, bar_len: int = 10) -> str:
    """
    溢价率显示：数字 + 百分位进度条（满格=近期最贵）。
    例如 "2.30% ████████░░ 80"
    """
    if premium_pct is None or pd.isna(premium_pct):
        return "—"
    pct = float(pctile_60) if pctile_60 is not None and not pd.isna(pctile_60) else None
    s = f"{float(premium_pct):.2f}%"
    if pct is not None and 0 <= pct <= 100:
        filled = int(round(bar_len * pct / 100))
        filled = min(bar_len, max(0, filled))
        bar = "█" * filled + "░" * (bar_len - filled)
        s += f" {bar} {pct:.0f}"
    return s


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
    raw["日期"] = pd.to_datetime(raw["日期"])
    for col in ["开盘", "最高", "最低"]:
        if col in raw.columns:
            aux = raw[["日期", col]].drop_duplicates("日期")
            df = df.merge(aux, on="日期", how="left")
        else:
            df[col] = np.nan
    if "最高" not in df.columns:
        df["最高"] = df["收盘"]
    if "最低" not in df.columns:
        df["最低"] = df["收盘"]
    df = df.sort_values("日期").tail(max(days + 30, REGRESSION_WINDOW)).reset_index(drop=True)
    close = df["收盘"]
    df["MA_short"] = close.rolling(ma_short, min_periods=1).mean()
    df["MA_long"] = close.rolling(ma_long, min_periods=1).mean()
    df["MA20"] = close.rolling(20, min_periods=1).mean()
    df["MA60"] = close.rolling(60, min_periods=10).mean()
    df["MA200"] = close.rolling(200, min_periods=1).mean()
    df["RSI"] = rsi(close, RSI_PERIOD)
    mid, upper, lower = bollinger(close, BB_PERIOD, BB_STD)
    df["BB_upper"], df["BB_lower"] = upper, lower
    high = df["最高"] if "最高" in df.columns else close
    low = df["最低"] if "最低" in df.columns else close
    df["ATR"] = atr(high, low, close, 14)
    return df


def build_monitor_table_advanced(
    etf_list: pd.DataFrame,
    days: int = 30,
    ma_short: int = 5,
    ma_long: int = 20,
    fetcher: Callable[[str, int, int, int], pd.DataFrame | None] | None = None,
    spot_premium_map: dict[str, float] | None = None,
) -> pd.DataFrame:
    """拉取日线，计算行情透视、偏离度、溢价率、每日操作建议与建议操作频率；单只失败则该行填错误。"""
    get_hist = fetcher or (lambda s, d, ms, ml: fetch_etf_daily(s, d, ms, ml))
    if spot_premium_map is None:
        try:
            spot_premium_map = get_etf_spot_premium_map(etf_list["代码"].astype(str).tolist())
        except Exception:
            spot_premium_map = {}
    rows = []
    for _, row in etf_list.iterrows():
        code = str(row["代码"]).strip()
        name = row.get("名称", code)
        category = row.get("指数简称", "其他")
        err_msg = None
        premium_pct = spot_premium_map.get(code)
        try:
            hist = get_hist(code, max(days, SIGNAL_LOOKBACK_DAYS + 10), ma_short, ma_long)
        except Exception as e:
            hist = None
            err_msg = str(e)[:80]
        if hist is None or hist.empty:
            rows.append({
                "代码": code, "名称": name, "指数简称": category,
                "最新价": None, "涨跌幅": None,
                "MA5": None, "MA20": None, "MA60": None, "MA200": None,
                "距一年高%": None, "距一年低%": None,
                "Bias_MA20": None, "Bias_MA60": None, "Bias_MA200": None,
                "明日建议": "—", "建议理由": "",
                "建议操作频率": 0,
                "溢价率": premium_pct if premium_pct is not None else None,
                "溢价率均值22d": None,
                "溢价分位60d": None,
                "溢价率显示": "—",
                "样本极少": False,
                "RSI": None,
                "信号准确率30d": None,
                "信号准确率显示": "—",
                "错误": err_msg or "获取失败",
            })
            continue
        try:
            nav_hist = get_etf_nav_hist(code, PREMIUM_FETCH_DAYS)
            reason_no_nav = None
            if nav_hist is None or nav_hist.empty:
                avg_premium_22d, premium_pctile_60d, premium_std_22d = None, None, None
                premium_valid_count, no_premium_data, sample_very_small = 0, True, False
                if premium_pct is not None and not pd.isna(premium_pct):
                    premium_display = format_premium_with_bar(premium_pct, None) + " (仅实时)"
                    action_no_nav = "无历史净值，仅参考实时溢价"
                    reason_no_nav = "仅实时溢价，无历史分位"
                else:
                    premium_display = "无净值数据"
                    action_no_nav = "缺少 IOPV/净值数据，无法评估溢价"
                    reason_no_nav = "接口未返回 IOPV/净值列或数据全为空"
            else:
                avg_premium_22d, premium_pctile_60d, premium_std_22d, premium_valid_count, no_premium_data, sample_very_small = get_etf_premium_stats(
                    hist, nav_hist, premium_pct, code=code
                )
                premium_display = format_premium_with_bar(premium_pct, premium_pctile_60d)
                if no_premium_data or (premium_pctile_60d is None and premium_valid_count == 0):
                    premium_display = "无净值数据"
                if sample_very_small and premium_display != "无净值数据":
                    premium_display = premium_display + " (样本极少)"
                action_no_nav = None
            r2, slope, _ = compute_trend_classification(hist)
            last = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) >= 2 else last
            close = last["收盘"]
            prev_close = prev["收盘"]
            pct = (float((close - prev_close) / prev_close * 100)) if prev_close and prev_close != 0 else None
            pct_high, pct_low = pct_from_1y_high_low(hist)
            bias_20 = bias_pct(float(close) if close is not None else None, last.get("MA20"))
            bias_60 = bias_pct(float(close) if close is not None else None, last.get("MA60"))
            bias_200 = bias_pct(float(close) if close is not None else None, last.get("MA200"))
            if action_no_nav is not None:
                action, reason = action_no_nav, (reason_no_nav or "接口未返回 IOPV/净值列或数据全为空")
            else:
                atr_pct = None
                if last.get("ATR") is not None and last.get("收盘") and float(last.get("收盘", 0) or 0) > 0:
                    try:
                        atr_pct = float(last["ATR"]) / float(last["收盘"]) * 100
                    except (TypeError, ValueError):
                        pass
                pct_drawdown_from_high = None
                if hist is not None and len(hist) >= 60 and "收盘" in hist.columns:
                    high_60d = hist["收盘"].astype(float).tail(60).max()
                    if high_60d and high_60d > 0 and close is not None:
                        try:
                            pct_drawdown_from_high = (float(high_60d) - float(close)) / float(high_60d) * 100
                        except (TypeError, ValueError):
                            pass
                action, reason = compute_daily_action(
                    last,
                    premium_pct=premium_pct,
                    avg_premium_22d=avg_premium_22d,
                    premium_std_22d=premium_std_22d,
                    premium_pctile_60=premium_pctile_60d,
                    r2=r2,
                    slope=slope,
                    atr_pct=atr_pct,
                    pct_drawdown_from_high=pct_drawdown_from_high,
                )
                if no_premium_data and premium_valid_count == 0:
                    action = "溢价数据不足"
                elif premium_pctile_60d is None and premium_valid_count == 0 and not no_premium_data:
                    action = "溢价数据不足"
            freq = compute_action_frequency(hist, SIGNAL_LOOKBACK_DAYS)
            acc_result = compute_signal_accuracy_30d(hist, nav_hist)
            acc = acc_result.get("信号准确率30d")
            acc_display = acc_result.get("信号准确率显示", "—")
            rsi_val = last.get("RSI")
            def _round_ma(v):
                if v is None or pd.isna(v):
                    return None
                return round(float(v), 4)
            rows.append({
                "代码": code, "名称": name, "指数简称": category,
                "最新价": round(float(close), 4),
                "涨跌幅": round(pct, 2) if pct is not None else None,
                "MA5": _round_ma(last.get("MA_short")),
                "MA20": _round_ma(last.get("MA20")),
                "MA60": _round_ma(last.get("MA60")),
                "MA200": _round_ma(last.get("MA200")),
                "距一年高%": round(pct_high, 2) if pct_high is not None else None,
                "距一年低%": round(pct_low, 2) if pct_low is not None else None,
                "Bias_MA20": bias_20, "Bias_MA60": bias_60, "Bias_MA200": bias_200,
                "明日建议": action, "建议理由": reason,
                "建议操作频率": freq,
                "溢价率": premium_pct,
                "溢价率均值22d": avg_premium_22d,
                "溢价分位60d": premium_pctile_60d,
                "溢价率显示": premium_display,
                "样本极少": sample_very_small if action_no_nav is None else False,
                "RSI": round(float(rsi_val), 1) if rsi_val is not None and not pd.isna(rsi_val) else None,
                "信号准确率30d": acc,
                "信号准确率显示": acc_display,
                "错误": None,
            })
        except Exception as e:
            err_msg = str(e)[:80] if e else "处理异常"
            rows.append({
                "代码": code, "名称": name, "指数简称": category,
                "最新价": None, "涨跌幅": None,
                "MA5": None, "MA20": None, "MA60": None, "MA200": None,
                "距一年高%": None, "距一年低%": None,
                "Bias_MA20": None, "Bias_MA60": None, "Bias_MA200": None,
                "明日建议": "—", "建议理由": "",
                "建议操作频率": 0,
                "溢价率": premium_pct if premium_pct is not None else None,
                "溢价率均值22d": None,
                "溢价分位60d": None,
                "溢价率显示": "—",
                "样本极少": False,
                "RSI": None,
                "信号准确率30d": None,
                "信号准确率显示": "—",
                "错误": err_msg,
            })
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
    _, up, lo = bollinger(close, BB_PERIOD, BB_STD)
    df["BB_upper"], df["BB_lower"] = up, lo
    return df
