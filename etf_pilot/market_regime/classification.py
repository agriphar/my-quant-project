# -*- coding: utf-8 -*-
"""自动资产分类：基于 3 年年化波动率与最大回撤，区分 Core / Tactical。"""
from pathlib import Path
from datetime import datetime, timedelta
import json
import pandas as pd
import numpy as np
import akshare as ak

from config.asset_types import CORE_KEYWORDS
from config.settings import (
    CLASSIFICATION_VOL_THRESHOLD,
    CLASSIFICATION_CACHE_DAYS,
    CLASSIFICATION_LOOKBACK_YEARS,
)
from strategy.asset_type import ASSET_TYPE_CORE, ASSET_TYPE_TACTICAL

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_PATH = DATA_DIR / "etf_classification.json"
TRADING_DAYS_PER_YEAR = 252


def _fetch_hist_3y(symbol: str) -> pd.DataFrame | None:
    """获取单只 ETF 过去约 3 年的日线（仅日期、收盘）。"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=CLASSIFICATION_LOOKBACK_YEARS * 365 + 100)
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
    date_col = "日期" if "日期" in raw.columns else (raw.columns[0] if len(raw.columns) else None)
    close_col = next((c for c in ["收盘", "收盘价"] if c in raw.columns), None)
    if not date_col or not close_col:
        return None
    df = raw[[date_col, close_col]].copy()
    df = df.rename(columns={date_col: "日期", close_col: "收盘"})
    df["日期"] = pd.to_datetime(df["日期"])
    df = df.sort_values("日期").dropna(subset=["收盘"])
    return df


def _annualized_volatility(close: pd.Series) -> float | None:
    """年化波动率（小数，如 0.25 表示 25%）。"""
    if close is None or len(close) < 22:
        return None
    ret = close.pct_change().dropna()
    if len(ret) < 22:
        return None
    return float(ret.std() * np.sqrt(TRADING_DAYS_PER_YEAR))


def _max_drawdown(close: pd.Series) -> float | None:
    """最大回撤（负数，如 -0.15 表示 15%）。"""
    if close is None or len(close) < 2:
        return None
    cummax = close.cummax()
    dd = (close - cummax) / cummax
    return float(dd.min())


def _is_broad_index(name: str) -> bool:
    """是否属于宽基指数（名称含 CORE_KEYWORDS）。"""
    name = str(name or "")
    return any(kw in name for kw in CORE_KEYWORDS)


def classify_etfs(etf_list: pd.DataFrame) -> pd.DataFrame:
    """
    根据过去 3 年日线计算年化波动率、最大回撤，并分类：
    - 年化波动率 < 25% 且 宽基指数 -> Core（核心稳健）
    - 年化波动率 >= 25% 或 行业/商品 -> Tactical（战术进攻）
    返回 DataFrame：代码、名称、年化波动率、最大回撤、类型。
    """
    rows = []
    for _, row in etf_list.iterrows():
        code = str(row["代码"]).strip()
        name = row.get("名称", code)
        hist = _fetch_hist_3y(code)
        if hist is None or len(hist) < 22:
            vol = None
            mdd = None
            asset_type = ASSET_TYPE_TACTICAL
        else:
            close = hist["收盘"]
            vol = _annualized_volatility(close)
            mdd = _max_drawdown(close)
            is_broad = _is_broad_index(name)
            if vol is not None and vol < CLASSIFICATION_VOL_THRESHOLD and is_broad:
                asset_type = ASSET_TYPE_CORE
            else:
                asset_type = ASSET_TYPE_TACTICAL
        rows.append({
            "代码": code,
            "名称": name,
            "年化波动率": round(vol, 4) if vol is not None else None,
            "最大回撤": round(mdd, 4) if mdd is not None else None,
            "类型": asset_type,
        })
    return pd.DataFrame(rows)


def get_cached_classification(etf_list: pd.DataFrame) -> pd.DataFrame:
    """
    获取分类结果：若缓存存在且未过期则读取，否则调用 classify_etfs 并写入缓存。
    返回与 etf_list 对齐的 类型（及可选 年化波动率、最大回撤）；未命中缓存的标的用 Tactical。
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    codes = set(etf_list["代码"].astype(str).str.strip())
    now = datetime.now()
    cache_ok = False
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            updated = data.get("updated", "")
            try:
                dt = datetime.strptime(updated, "%Y-%m-%d")
                if (now - dt).days <= CLASSIFICATION_CACHE_DAYS:
                    cache_ok = True
            except Exception:
                pass
            if cache_ok and data.get("rows"):
                cached = pd.DataFrame(data["rows"])
                cached_codes = set(cached["代码"].astype(str))
                if codes <= cached_codes:
                    type_map = cached.set_index("代码")["类型"].to_dict()
                    etf_list = etf_list.copy()
                    etf_list["类型"] = etf_list["代码"].astype(str).map(lambda c: type_map.get(c, ASSET_TYPE_TACTICAL))
                    return etf_list
        except Exception:
            pass
    # 重新计算并写缓存
    result = classify_etfs(etf_list)
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "updated": now.strftime("%Y-%m-%d"),
                "rows": result.to_dict("records"),
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    type_map = result.set_index("代码")["类型"].to_dict()
    etf_list = etf_list.copy()
    etf_list["类型"] = etf_list["代码"].astype(str).map(lambda c: type_map.get(c, ASSET_TYPE_TACTICAL))
    return etf_list
