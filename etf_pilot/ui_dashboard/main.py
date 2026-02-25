# -*- coding: utf-8 -*-
"""跨境 ETF 决策辅助仪表盘：单一纵向推理流，仅保留四层（Signal → Risk → Confidence → Decision）。"""
import logging
import sys
import warnings

import pandas as pd
import streamlit as st

from config import (
    MA_SHORT_DEFAULT,
    MA_LONG_DEFAULT,
    CACHE_TTL,
    CATEGORY_KEYWORDS,
    CATEGORY_ALL,
)
from etf_data import (
    load_etf_list,
    build_monitor_table_advanced,
    fetch_etf_daily,
    ensure_data_dir,
)
from risk_engine import drawdown_15pct_value
from ui_dashboard.styling import filter_by_category, sort_for_dashboard
from ui_dashboard.etf_drilldown import render_etf_drilldown

_log_handler = logging.StreamHandler(sys.stderr)
_log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))
logging.getLogger("etf_data").addHandler(_log_handler)
logging.getLogger("etf_data").setLevel(logging.INFO)

warnings.filterwarnings(
    "ignore",
    message="Could not infer format, so each element will be parsed individually",
    category=UserWarning,
    module="pandas",
)


def run():
    st.set_page_config(page_title="跨境 ETF 决策辅助仪表盘", page_icon="📊", layout="wide")
    st.title("跨境 ETF 决策辅助仪表盘")
    st.caption("四层推理流：Signal → Risk → Confidence → Decision。本项目仅供学习研究，不构成投资建议。")

    ensure_data_dir()
    etf_list_full = load_etf_list()
    if etf_list_full.empty:
        st.warning("未找到有效的 ETF 列表，请检查 data/ETF汇总.xlsx 是否包含「代码」「名称」列。")
        st.stop()

    with st.sidebar:
        st.subheader("筛选与参数")
        category_options = [CATEGORY_ALL] + list(CATEGORY_KEYWORDS.keys())
        selected_category = st.selectbox(
            "ETF 类别",
            options=category_options,
            index=0,
            help="按指数/主题筛选 ETF",
        )
        ma_short = st.number_input("MA 短期", min_value=3, max_value=60, value=MA_SHORT_DEFAULT, step=1)
        ma_long = st.number_input("MA 长期", min_value=5, max_value=120, value=MA_LONG_DEFAULT, step=1)
        if ma_short >= ma_long:
            st.warning("建议短期 < 长期")
        days = 250
        st.caption(f"数据：最近 {days} 个交易日 · 缓存 {CACHE_TTL}s")

        st.subheader("极端风险模拟")
        account_value = st.number_input(
            "当前账户/持仓市值（元）",
            min_value=0,
            value=100000,
            step=10000,
            help="用于估算若标的发生 15% 回撤后的账户金额",
        )
        if account_value > 0:
            after_drawdown = drawdown_15pct_value(account_value)
            st.metric("若发生 15% 回撤后", f"¥{after_drawdown:,.0f}", None)

    @st.cache_data(ttl=CACHE_TTL)
    def _cached_fetch(symbol: str, days: int, ma_short: int, ma_long: int):
        return fetch_etf_daily(symbol, days=days, ma_short=ma_short, ma_long=ma_long)

    def _cached_build(etf_df: pd.DataFrame, days: int, ma_short: int, ma_long: int) -> pd.DataFrame:
        def fetcher(sym: str, d: int, ms: int, ml: int):
            return _cached_fetch(sym, d, ms, ml)
        return build_monitor_table_advanced(etf_df, days=days, ma_short=ma_short, ma_long=ma_long, fetcher=fetcher)

    @st.cache_data(ttl=CACHE_TTL)
    def _cached_build_table(records: list, days: int, ma_short: int, ma_long: int) -> pd.DataFrame:
        df_etf = pd.DataFrame(records)
        return _cached_build(df_etf, days=days, ma_short=ma_short, ma_long=ma_long)

    table_key = (tuple(sorted(etf_list_full["代码"].astype(str))), days, int(ma_short), int(ma_long))
    if st.session_state.get("_table_key") != table_key or "_table_df_full" not in st.session_state:
        with st.spinner("正在拉取数据并计算四层输出…"):
            try:
                df_full = _cached_build_table(
                    etf_list_full.to_dict("records"),
                    days=days,
                    ma_short=int(ma_short),
                    ma_long=int(ma_long),
                )
                st.session_state._table_key = table_key
                st.session_state._table_df_full = df_full
            except Exception as e:
                st.error(f"拉取数据失败：{e}")
                st.stop()
    else:
        df_full = st.session_state._table_df_full

    df = filter_by_category(df_full, selected_category, CATEGORY_ALL, CATEGORY_KEYWORDS)
    if df.empty:
        st.warning(f"类别「{selected_category}」下暂无 ETF。")
        st.stop()

    df_display = sort_for_dashboard(df)

    # 单一纵向推理流：先选标的，再自上而下展示四层
    card_options = [f"{row['名称']} ({row['代码']})" for _, row in df_display.iterrows()]
    display_to_code = {f"{row['名称']} ({row['代码']})": str(row["代码"]) for _, row in df_display.iterrows()}
    selected_display = st.selectbox("选择标的", options=card_options, key="main_etf_select", label_visibility="visible")

    if not selected_display or selected_display not in display_to_code:
        st.info("请从上方选择一只标的，查看四层推理流（市场状态 → 风险评估 → 置信度 → 决策输出）。")
        st.stop()

    code = display_to_code[selected_display]
    sel_mask = df_display["代码"].astype(str) == code
    if not sel_mask.any():
        st.warning("未找到该标的数据。")
        st.stop()

    sel_row = df_display.loc[sel_mask].iloc[0]

    # ETF Drill-down：仅该标的的四层结果，不重复全局逻辑
    render_etf_drilldown(sel_row, selected_display)
