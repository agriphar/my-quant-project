# -*- coding: utf-8 -*-
"""ETF 数据获取与指标计算（RSI、布林带、多因子信号、建议仓位）。"""
from pathlib import Path
from datetime import datetime, timedelta
from typing import Callable
import pandas as pd
import numpy as np
import akshare as ak

from config.settings import RSI_PERIOD, BB_PERIOD, BB_STD
from strategy import compute_deviation, check_chase_high

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
SIGNAL_FWD_DAYS = 3       # 信号准确率：看 N 日后收益
SIGNAL_LOOKBACK_DAYS = 30 # 过去 30 天统计准确率


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


def compute_daily_action(last: pd.Series) -> tuple:
    """
    每日操作建议：返回 (操作, 理由)。
    操作: 分批吸纳 / 套利离场 / 持有观望。
    - 分批吸纳：价格回落至 MA60 附近且 RSI < 45
    - 套利离场：价格触及布林带上轨（若网格利润覆盖 5 倍手续费更佳，此处简化为触及上轨）
    - 持有观望：其余
    """
    close = last.get("收盘")
    ma60 = last.get("MA60")
    rsi = last.get("RSI")
    bb_upper = last.get("BB_upper")
    if close is None or pd.isna(close):
        return "持有观望", "数据不足"
    if ma60 is not None and not pd.isna(ma60) and ma60 > 0:
        near_ma60 = abs(float(close) - float(ma60)) / float(ma60) <= MA60_NEAR_PCT
        if near_ma60 and rsi is not None and not pd.isna(rsi) and rsi < RSI_ADDON_MAX:
            return "分批吸纳", "价格回落至MA60附近且RSI<45，适合分批吸纳"
    if bb_upper is not None and not pd.isna(bb_upper) and bb_upper > 0:
        if float(close) >= float(bb_upper) * BB_UPPER_TOUCH:
            return "套利离场", "价格触及布林带上轨，可考虑套利离场"
    return "持有观望", "价格在均线之上平稳运行，无极值信号"


def compute_action_frequency(hist: pd.DataFrame, days: int = SIGNAL_LOOKBACK_DAYS) -> int:
    """过去 N 天内「分批吸纳」或「套利离场」出现次数，用于排序（建议操作频率）。"""
    if hist is None or len(hist) < 2 or "收盘" not in hist.columns:
        return 0
    need = ["收盘", "MA60", "RSI", "BB_upper"]
    if not all(c in hist.columns for c in need):
        return 0
    tail = hist.tail(days)
    count = 0
    for _, row in tail.iterrows():
        act, _ = compute_daily_action(row)
        if act in ("分批吸纳", "套利离场"):
            count += 1
    return count


def compute_signal_accuracy_30d(hist: pd.DataFrame) -> float | None:
    """
    过去 30 天信号准确率：若按当日建议操作，看 3 日后收益是否一致。
    买入(分批吸纳)且 3 日后涨 -> 正确；卖出(套利离场)且 3 日后跌 -> 正确；持有不参与统计。
    返回 0~100 的准确率，无有效样本时返回 None。
    """
    if hist is None or len(hist) < SIGNAL_LOOKBACK_DAYS + SIGNAL_FWD_DAYS + 5:
        return None
    need = ["收盘", "MA60", "RSI", "BB_upper"]
    if not all(c in hist.columns for c in need):
        return None
    close = hist["收盘"].reset_index(drop=True)
    correct = 0
    total = 0
    for i in range(len(hist) - SIGNAL_FWD_DAYS):
        if i + SIGNAL_FWD_DAYS >= len(hist):
            break
        row = hist.iloc[i]
        act, _ = compute_daily_action(row)
        if act == "持有观望":
            continue
        p0 = close.iloc[i]
        p3 = close.iloc[i + SIGNAL_FWD_DAYS]
        if p0 is None or p0 <= 0 or pd.isna(p0) or pd.isna(p3):
            continue
        ret3 = (float(p3) - float(p0)) / float(p0)
        total += 1
        if act == "分批吸纳" and ret3 > 0:
            correct += 1
        elif act == "套利离场" and ret3 < 0:
            correct += 1
    if total == 0:
        return None
    return round(correct / total * 100, 1)


def drawdown_15pct_value(current_value: float) -> float:
    """极端风险模拟：若标的发生 15% 回撤，账户会变成多少。"""
    if current_value is None or pd.isna(current_value) or current_value < 0:
        return 0.0
    return round(float(current_value) * (1 - 0.15), 2)


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
    df["MA60"] = close.rolling(60, min_periods=1).mean()
    df["MA200"] = close.rolling(200, min_periods=1).mean()
    df["RSI"] = _rsi(close, RSI_PERIOD)
    mid, upper, lower = _bollinger(close, BB_PERIOD, BB_STD)
    df["BB_upper"], df["BB_lower"] = upper, lower
    return df


def _qdii_premium_placeholder(_code: str) -> str:
    """QDII ETF 溢价率：接口允许时填入，否则返回占位。"""
    return "—"


def build_monitor_table_advanced(
    etf_list: pd.DataFrame,
    days: int = 30,
    ma_short: int = 5,
    ma_long: int = 20,
    fetcher: Callable[[str, int, int, int], pd.DataFrame | None] | None = None,
) -> pd.DataFrame:
    """拉取日线，计算行情透视、偏离度、每日操作建议与建议操作频率；单只失败则该行填错误。"""
    get_hist = fetcher or (lambda s, d, ms, ml: fetch_etf_daily(s, d, ms, ml))
    rows = []
    for _, row in etf_list.iterrows():
        code = str(row["代码"]).strip()
        name = row.get("名称", code)
        category = row.get("指数简称", "其他")
        err_msg = None
        try:
            hist = get_hist(code, max(days, SIGNAL_LOOKBACK_DAYS + 10), ma_short, ma_long)
        except Exception as e:
            hist = None
            err_msg = str(e)[:80]
        if hist is None or hist.empty:
            rows.append({
                "代码": code, "名称": name, "指数简称": category,
                "最新价": None, "涨跌幅": None,
                "距一年高%": None, "距一年低%": None,
                "Bias_MA20": None, "Bias_MA60": None, "Bias_MA200": None,
                "明日建议": "—", "建议理由": "",
                "建议操作频率": 0,
                "溢价率": _qdii_premium_placeholder(code),
                "信号准确率30d": None,
                "错误": err_msg or "获取失败",
            })
            continue
        last = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) >= 2 else last
        close = last["收盘"]
        prev_close = prev["收盘"]
        pct = (float((close - prev_close) / prev_close * 100)) if prev_close and prev_close != 0 else None
        pct_high, pct_low = _pct_from_1y_high_low(hist)
        bias_20 = _bias_pct(float(close) if close is not None else None, last.get("MA20"))
        bias_60 = _bias_pct(float(close) if close is not None else None, last.get("MA60"))
        bias_200 = _bias_pct(float(close) if close is not None else None, last.get("MA200"))
        action, reason = compute_daily_action(last)
        freq = compute_action_frequency(hist, SIGNAL_LOOKBACK_DAYS)
        acc = compute_signal_accuracy_30d(hist)
        rows.append({
            "代码": code, "名称": name, "指数简称": category,
            "最新价": round(float(close), 4),
            "涨跌幅": round(pct, 2) if pct is not None else None,
            "距一年高%": round(pct_high, 2) if pct_high is not None else None,
            "距一年低%": round(pct_low, 2) if pct_low is not None else None,
            "Bias_MA20": bias_20, "Bias_MA60": bias_60, "Bias_MA200": bias_200,
            "明日建议": action, "建议理由": reason,
            "建议操作频率": freq,
            "溢价率": _qdii_premium_placeholder(code),
            "信号准确率30d": acc,
            "错误": None,
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
