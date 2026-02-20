# -*- coding: utf-8 -*-
"""ETF 数据获取与指标计算（RSI、布林带、多因子信号、建议仓位）。"""
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Callable
import pandas as pd
import numpy as np
import akshare as ak

from config.settings import RSI_PERIOD, BB_PERIOD, BB_STD
from strategy import compute_deviation, check_chase_high
from strategy.scoring import premium_deviation, calculate_score, get_signal_from_score

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


# 趋势/震荡分类：180 日线性回归，R²>0.4 且斜率>0 为 Trend
REGRESSION_WINDOW = 180
R2_TREND_THRESHOLD = 0.4
ASSET_TREND = "Trend (趋势型)"
ASSET_OSCILLATING = "Oscillating (震荡型)"

# 每日操作建议算法
TRADING_DAYS_1Y = 250
MA60_NEAR_PCT = 0.02      # 价格在 MA60 上下 2% 内视为「MA60 附近」
RSI_ADDON_MAX = 45        # RSI < 45 视为可分批吸纳
BB_UPPER_TOUCH = 0.998    # 收盘 >= 布林上轨*此系数视为触及上轨
SIGNAL_FWD_DAYS = 5       # 信号准确率：看 N 日后涨跌
SIGNAL_LOOKBACK_DAYS = 30 # 过去 30 天统计准确率
# 溢价基准与动态信号
PREMIUM_AVG_DAYS = 22           # 过去 22 个交易日（约一个月）平均溢价率
PREMIUM_PCTILE_DAYS = 60       # 分位统计窗口 60 天
PREMIUM_FETCH_DAYS = 100       # 抓取最近 100 个交易日数据，确保扣除节假日仍能填满 60 日窗口
PREMIUM_SAFE_PLUS_PCT = 1.0    # 当前溢价 < 平均溢价 + 1% 视为安全，允许按技术面给建议
PREMIUM_EXTREME_MULT = 1.5     # 当前溢价 > 平均溢价 * 1.5
PREMIUM_PCTILE_HIGH = 90       # 分位 > 90% 且满足倍数时强制减仓/观望
PREMIUM_PCTILE_MIN_DAYS = 10   # 至少 10 天即计算分位（软化窗口），否则仅显示当前溢价率
MIN_ACCURACY_SAMPLE = 3        # 准确率至少 N 次买/卖建议才显示百分比


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


def _pct_from_1y_high_low(hist: pd.DataFrame) -> tuple:
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


def _bias_pct(price: float | None, ma: float | None) -> float | None:
    """乖离率：(price - ma) / ma * 100。"""
    if price is None or ma is None or pd.isna(ma) or ma == 0:
        return None
    return round((float(price) - float(ma)) / float(ma) * 100, 2)


def compute_daily_action(
    last: pd.Series,
    premium_pct: float | None = None,
    avg_premium_22d: float | None = None,
    premium_std_22d: float | None = None,
    premium_pctile_60: float | None = None,
    r2: float | None = None,
    slope: float | None = None,
    bias_ma20: float | None = None,
    bias_ma200: float | None = None,
) -> tuple:
    """
    每日操作建议（加权评分制 + 相对溢价）：
    - 溢价偏离度 = (当前溢价 - 22日均值) / 22日标准差；>2.5 一票否决 -> 极度过热，禁买。
    - 否则按 calculate_score（技术4 + 趋势3 + 溢价3）总分：>=7 强烈建议补仓，4~7 持有观望，<4 考虑套利/减仓。
    """
    if last.get("收盘") is None or pd.isna(last.get("收盘")):
        return "持有观望", "数据不足"
    dev = premium_deviation(premium_pct, avg_premium_22d, premium_std_22d)
    score_result = calculate_score(
        last,
        r2=r2,
        slope=slope,
        premium_pctile_60=premium_pctile_60,
        bias_ma20=bias_ma20,
        bias_ma200=bias_ma200,
    )
    return get_signal_from_score(score_result, dev)


def compute_action_frequency(hist: pd.DataFrame, days: int = SIGNAL_LOOKBACK_DAYS) -> int:
    """过去 N 天内「强烈建议补仓」或「考虑套利/减仓」出现次数，用于排序（建议操作频率）。"""
    if hist is None or len(hist) < 2 or "收盘" not in hist.columns:
        return 0
    need = ["收盘", "MA60", "RSI", "BB_upper"]
    if not all(c in hist.columns for c in need):
        return 0
    tail = hist.tail(days)
    count = 0
    for _, row in tail.iterrows():
        act, _ = compute_daily_action(row)
        if act in ("强烈建议补仓", "考虑套利/减仓"):
            count += 1
    return count


def _hist_daily_premium_merged(hist: pd.DataFrame, nav_hist: pd.DataFrame | None) -> pd.DataFrame | None:
    """
    将日线 hist 与净值 nav_hist 按日期合并，得到每日的场内价与溢价率（场内价=收盘）。
    返回 DataFrame：日期、收盘、溢价率（及 hist 中已有的 MA60/RSI/BB_upper 等，若存在则保留）。
    用于回溯时逐日使用「技术指标 + 溢价水位」重算建议。
    """
    if hist is None or hist.empty or "收盘" not in hist.columns:
        return None
    hist = hist.copy()
    hist["日期"] = pd.to_datetime(hist["日期"]).dt.normalize()
    if nav_hist is None or nav_hist.empty or "单位净值" not in nav_hist.columns:
        return hist.assign(溢价率=np.nan)
    nav = nav_hist.copy()
    nav["日期"] = pd.to_datetime(nav["日期"]).dt.normalize()
    merged = hist.merge(nav[["日期", "单位净值"]], on="日期", how="left")
    merged["单位净值"] = merged["单位净值"].replace(0, np.nan)
    merged["溢价率"] = np.nan
    valid = merged["单位净值"].notna() & (merged["单位净值"] > 0)
    merged.loc[valid, "溢价率"] = (
        (merged.loc[valid, "收盘"].astype(float) - merged.loc[valid, "单位净值"].astype(float))
        / merged.loc[valid, "单位净值"].astype(float) * 100
    )
    return merged


def compute_signal_accuracy_30d(
    hist: pd.DataFrame,
    nav_hist: pd.DataFrame | None = None,
) -> dict:
    """
    过去 30 天信号准确率（仅统计补仓/减仓，且信号须已跑满 5 日）：
    - 对比「信号发出日收盘价」与「信号发出后第 5 个交易日收盘价」。
    - 若信号发出距今不足 5 天，则该信号不计入。
    - 仅当建议次数 >= MIN_ACCURACY_SAMPLE 时显示百分比；否则返回状态文案。
    返回 {"信号准确率30d": float|None, "实战建议次数": int, "信号准确率显示": str}。
    """
    out = {"信号准确率30d": None, "实战建议次数": 0, "信号准确率显示": "—"}
    if hist is None or len(hist) < SIGNAL_LOOKBACK_DAYS + SIGNAL_FWD_DAYS + 5:
        return out
    need = ["收盘", "MA60", "RSI", "BB_upper"]
    if not all(c in hist.columns for c in need):
        return out
    merged = _hist_daily_premium_merged(hist, nav_hist)
    if merged is None:
        return out
    merged = merged.sort_values("日期").reset_index(drop=True)
    close = merged["收盘"].astype(float)
    start_i = max(0, len(merged) - SIGNAL_LOOKBACK_DAYS)
    end_i = len(merged) - SIGNAL_FWD_DAYS
    if start_i >= end_i:
        return out
    correct = 0
    total = 0
    for i in range(start_i, end_i):
        if i + SIGNAL_FWD_DAYS >= len(merged):
            break
        row_i = merged.iloc[i]
        p0 = close.iloc[i]
        p5 = close.iloc[i + SIGNAL_FWD_DAYS]
        if p0 is None or p0 <= 0 or pd.isna(p0) or pd.isna(p5):
            continue
        ret5 = (float(p5) - float(p0)) / float(p0)
        premium_i = row_i.get("溢价率")
        if pd.isna(premium_i) or premium_i is None:
            avg_22_i = None
            pct_60_i = None
            std_22_i = None
        else:
            sub = merged.loc[merged["日期"] <= row_i["日期"], "溢价率"].dropna().tail(PREMIUM_PCTILE_DAYS)
            if len(sub) < 5:
                avg_22_i = None
                pct_60_i = None
                std_22_i = None
            else:
                tail22 = sub.tail(PREMIUM_AVG_DAYS)
                avg_22_i = float(tail22.mean())
                std_22_i = float(tail22.std()) if len(tail22) > 1 and tail22.std() and not pd.isna(tail22.std()) else None
                pct_60_i = _percentileofscore(sub.values, float(premium_i))
        action = compute_daily_action(
            row_i,
            premium_pct=float(premium_i) if premium_i is not None and not pd.isna(premium_i) else None,
            avg_premium_22d=avg_22_i,
            premium_std_22d=std_22_i,
            premium_pctile_60=pct_60_i,
        )[0]
        if action in ("持有观望", "极度过热，禁买"):
            continue
        if action == "强烈建议补仓":
            total += 1
            if ret5 > 0:
                correct += 1
            continue
        if action == "考虑套利/减仓":
            total += 1
            if ret5 < 0:
                correct += 1
            continue
    out["实战建议次数"] = total
    if total == 0:
        out["信号准确率显示"] = "近期无动作"
        return out
    if total < MIN_ACCURACY_SAMPLE:
        out["信号准确率显示"] = "样本不足"
        return out
    pct = round(correct / total * 100, 1)
    out["信号准确率30d"] = pct
    out["信号准确率显示"] = f"{pct}%"
    return out


def drawdown_15pct_value(current_value: float) -> float:
    """极端风险模拟：若标的发生 15% 回撤，账户会变成多少。"""
    if current_value is None or pd.isna(current_value) or current_value < 0:
        return 0.0
    return round(float(current_value) * (1 - 0.15), 2)


def get_etf_nav_hist(symbol: str, days: int = 70) -> pd.DataFrame | None:
    """获取单只 ETF 历史单位净值，用于计算历史溢价率。返回 日期、单位净值。
    若接口无「单位净值」则尝试「基金净值」「net_value」；均无或全为空则返回 None。
    API 失败或返回空时最多重试 3 次，每次间隔 0.5 秒。
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=int(days * 1.8) + 20)
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    raw = None
    for attempt in range(3):
        try:
            raw = ak.fund_etf_fund_info_em(
                fund=symbol.strip(),
                start_date=start_str,
                end_date=end_str,
            )
        except Exception:
            raw = None
        if raw is not None and not raw.empty:
            break
        if attempt < 2:
            time.sleep(0.5)
    if raw is None or raw.empty:
        return None
    raw = raw.rename(columns=lambda c: str(c).strip())
    date_col = next((c for c in ["净值日期", "日期", "date"] if c in raw.columns), None)
    nav_col = None
    for c in ["单位净值", "基金净值", "net_value"]:
        if c in raw.columns and raw[c].notna().any() and (raw[c].astype(str).str.strip() != "").any():
            nav_col = c
            break
    if not date_col or not nav_col:
        return None
    df = raw[[date_col, nav_col]].copy()
    df["日期"] = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
    df = df.dropna(subset=["日期", nav_col])
    df[nav_col] = pd.to_numeric(df[nav_col], errors="coerce")
    df = df[df[nav_col].notna() & (df[nav_col] > 0)].sort_values("日期").tail(days).reset_index(drop=True)
    if df.empty:
        return None
    return df[["日期", nav_col]].rename(columns={nav_col: "单位净值"})


def _percentileofscore(arr: np.ndarray, score: float) -> float:
    """0~100，表示 score 在 arr 中的百分位（小于等于 score 的比例 * 100）。"""
    if arr is None or len(arr) == 0:
        return np.nan
    arr = np.asarray(arr, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return np.nan
    return float(np.sum(arr <= score) / len(arr) * 100)


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


def rsi_status_label(rsi: float | None) -> str:
    """RSI 状态灯：超跌准备买 / 安全区间 / 警惕超买 / 危险准备卖。"""
    if rsi is None or pd.isna(rsi):
        return "—"
    r = float(rsi)
    if r < 45:
        return "超跌准备买"
    if r <= 70:
        return "安全区间"
    if r <= 80:
        return "警惕超买"
    return "危险准备卖"


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
    df["RSI"] = _rsi(close, RSI_PERIOD)
    mid, upper, lower = _bollinger(close, BB_PERIOD, BB_STD)
    df["BB_upper"], df["BB_lower"] = upper, lower
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
            if nav_hist is None or nav_hist.empty:
                avg_premium_22d, premium_pctile_60d, premium_std_22d = None, None, None
                premium_valid_count, no_premium_data, sample_very_small = 0, True, False
                premium_display = "无净值数据"
                action_no_nav = "缺少 IOPV/净值数据，无法评估溢价"
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
            pct_high, pct_low = _pct_from_1y_high_low(hist)
            bias_20 = _bias_pct(float(close) if close is not None else None, last.get("MA20"))
            bias_60 = _bias_pct(float(close) if close is not None else None, last.get("MA60"))
            bias_200 = _bias_pct(float(close) if close is not None else None, last.get("MA200"))
            if action_no_nav is not None:
                action, reason = action_no_nav, "接口未返回 IOPV/净值列或数据全为空"
            else:
                action, reason = compute_daily_action(
                    last,
                    premium_pct=premium_pct,
                    avg_premium_22d=avg_premium_22d,
                    premium_std_22d=premium_std_22d,
                    premium_pctile_60=premium_pctile_60d,
                    r2=r2,
                    slope=slope,
                    bias_ma20=bias_20,
                    bias_ma200=bias_200,
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
    df["MA60"] = close.rolling(60, min_periods=10).mean()
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
