# -*- coding: utf-8 -*-
"""跨境 ETF 决策辅助仪表盘：Streamlit 入口，仅布局与调用各层，无业务逻辑。"""
import logging
import sys
import warnings

import numpy as np
import pandas as pd
import streamlit as st
from plotly.subplots import make_subplots
import plotly.graph_objects as go

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
    get_etf_hist_for_chart,
    ETF_LIST_PATH,
    ensure_data_dir,
)
from risk_engine import drawdown_15pct_value
from ui_dashboard.styling import (
    filter_by_category,
    sort_for_dashboard,
    add_明日建议_warning_prefix,
    style_dashboard_table,
    style_radar_rsi,
)
from ui_dashboard.algorithm_text import ALGORITHM_MARKDOWN

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
    st.set_page_config(page_title="跨境 ETF 决策辅助", page_icon="📊", layout="wide")
    st.title("📊 跨境 ETF 决策辅助仪表盘")
    st.caption("本项目仅供学习和研究使用，不构成任何投资建议。股市有风险，投资需谨慎。")

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

    with st.spinner("正在拉取日线与 IOPV 实时估值，计算行情透视、偏离度、溢价率与操作建议…"):
        try:
            df_full = _cached_build_table(
                etf_list_full.to_dict("records"),
                days=days,
                ma_short=int(ma_short),
                ma_long=int(ma_long),
            )
        except Exception as e:
            st.error(f"拉取数据失败：{e}")
            st.stop()

    df = filter_by_category(df_full, selected_category, CATEGORY_ALL, CATEGORY_KEYWORDS)
    if df.empty:
        st.warning(f"类别「{selected_category}」下暂无 ETF。")
        st.stop()

    df_display = sort_for_dashboard(df)

    tab_dashboard, tab_radar, tab_deep, tab_accuracy = st.tabs(["决策看板", "实时雷达", "个股深度分析", "信号准确率"])

    with tab_dashboard:
        st.subheader("行情透视 · 偏离度 · 明日建议（按建议操作频率排序）")
        st.caption("结论为参考区间而非精确预测；存在信号分歧时请综合判断。")
        show_cols = [
            "代码", "名称", "最新价", "涨跌幅",
            "距一年高%", "距一年低%",
            "Bias_MA20", "Bias_MA60", "Bias_MA200",
            "明日建议", "信心区间", "信号分歧显示", "建议操作频率", "溢价率显示", "RSI", "信号准确率显示",
        ]
        show_cols = [c for c in show_cols if c in df_display.columns]
        table_df = df_display[show_cols].copy()
        table_df = add_明日建议_warning_prefix(table_df, df_display)
        table_df = table_df.replace([np.inf, -np.inf], np.nan).fillna("-")
        styled = style_dashboard_table(table_df, df_display)
        st.dataframe(
            styled,
            width="stretch",
            column_config={
                "最新价": st.column_config.NumberColumn(format="%.2f"),
                "涨跌幅": st.column_config.NumberColumn(format="%.2f%%"),
                "距一年高%": st.column_config.NumberColumn(format="%.1f%%"),
                "距一年低%": st.column_config.NumberColumn(format="%.1f%%"),
                "Bias_MA20": st.column_config.NumberColumn(format="%.1f%%"),
                "Bias_MA60": st.column_config.NumberColumn(format="%.1f%%"),
                "Bias_MA200": st.column_config.NumberColumn(format="%.1f%%"),
                "明日建议": st.column_config.TextColumn("明日建议"),
                "信心区间": st.column_config.TextColumn("信心"),
                "信号分歧显示": st.column_config.TextColumn("信号分歧"),
                "溢价率显示": st.column_config.TextColumn("溢价率"),
                "RSI": st.column_config.NumberColumn(format="%.0f"),
                "信号准确率显示": st.column_config.TextColumn("准确率30d"),
            },
            hide_index=True,
        )

        st.subheader("点击查看明日操作卡片")
        card_options = [f"{row['名称']} ({row['代码']})" for _, row in df_display.iterrows()]
        card_display_to_code = {f"{row['名称']} ({row['代码']})": str(row["代码"]) for _, row in df_display.iterrows()}
        selected_display = st.selectbox("选择 ETF", options=card_options, key="card_select")
        if selected_display:
            code = card_display_to_code.get(selected_display)
            sel_mask = df_display["代码"].astype(str) == code
            if code and sel_mask.any():
                sel_row = df_display.loc[sel_mask].iloc[0]
                display_label = sel_row.get("明日建议", "观望")
                reason = sel_row.get("建议理由", "")
                name = sel_row.get("名称", "")
                confidence = sel_row.get("信心区间", "—")
                conflicting = sel_row.get("信号分歧", False)
                st.info(f"**参考结论：{display_label}**  \n理由：{reason}")
                st.caption(f"标的：{name} · 信心区间：{confidence}")
                if conflicting:
                    st.warning("当前存在信号分歧，多因子方向不一致，请综合判断后再做决策。")

    with tab_radar:
        st.caption("实时行情：最新价、涨跌幅与均线/RSI 等具体数据（与决策看板不重复）")
        radar_cols = ["代码", "名称", "最新价", "涨跌幅", "MA5", "MA20", "MA60", "MA200", "RSI"]
        radar_cols = [c for c in radar_cols if c in df_display.columns]
        radar_df = df_display[radar_cols].copy()
        radar_styled = style_radar_rsi(radar_df)
        st.dataframe(
            radar_styled,
            width="stretch",
            column_config={
                "最新价": st.column_config.NumberColumn(format="%.2f"),
                "涨跌幅": st.column_config.NumberColumn(format="%.2f%%"),
                "MA5": st.column_config.NumberColumn(format="%.2f"),
                "MA20": st.column_config.NumberColumn(format="%.2f"),
                "MA60": st.column_config.NumberColumn(format="%.2f"),
                "MA200": st.column_config.NumberColumn(format="%.2f"),
                "RSI": st.column_config.NumberColumn(format="%.0f"),
            },
            hide_index=True,
        )

    with tab_deep:
        @st.fragment
        def _deep_fragment():
            st.caption("选择一只 ETF，查看带均线与布林带的 K 线图")
            options = [f"{row['名称']} ({row['代码']})" for _, row in df_display.iterrows()]
            display_to_code = {f"{row['名称']} ({row['代码']})": str(row["代码"]) for _, row in df_display.iterrows()}
            selected_display = st.selectbox("选择标的", options=options, key="deep_select")
            if selected_display and selected_display in display_to_code:
                code = display_to_code[selected_display]
                with st.spinner("拉取 K 线数据…"):
                    chart_df = get_etf_hist_for_chart(symbol=code, days=60, ma_short=int(ma_short), ma_long=int(ma_long))
                if chart_df is None or chart_df.empty:
                    st.warning("该标的 K 线数据获取失败。")
                else:
                    fig = make_subplots(
                        rows=2, cols=1,
                        shared_xaxes=True,
                        vertical_spacing=0.06,
                        row_heights=[0.75, 0.25],
                        subplot_titles=(selected_display, "成交量"),
                    )
                    if all(c in chart_df.columns for c in ["开盘", "最高", "最低", "收盘"]):
                        fig.add_trace(
                            go.Candlestick(
                                x=chart_df["日期"], open=chart_df["开盘"], high=chart_df["最高"],
                                low=chart_df["最低"], close=chart_df["收盘"], name="K线",
                            ),
                            row=1, col=1,
                        )
                    else:
                        fig.add_trace(
                            go.Scatter(x=chart_df["日期"], y=chart_df["收盘"], mode="lines", name="收盘", line=dict(color="blue", width=2)),
                            row=1, col=1,
                        )
                    for col, label in [("MA_short", f"MA{ma_short}"), ("MA_long", f"MA{ma_long}")]:
                        if col in chart_df.columns:
                            fig.add_trace(
                                go.Scatter(x=chart_df["日期"], y=chart_df[col], mode="lines", name=label, line=dict(width=1.5)),
                                row=1, col=1,
                            )
                    for col, label in [("BB_upper", "布林上轨"), ("BB_lower", "布林下轨")]:
                        if col in chart_df.columns:
                            fig.add_trace(
                                go.Scatter(x=chart_df["日期"], y=chart_df[col], mode="lines", name=label, line=dict(width=1, dash="dot")),
                                row=1, col=1,
                            )
                    if "成交量" in chart_df.columns and chart_df["成交量"].notna().any():
                        fig.add_trace(
                            go.Bar(x=chart_df["日期"], y=chart_df["成交量"], name="成交量", marker_color="lightblue", showlegend=False),
                            row=2, col=1,
                        )
                    fig.update_layout(xaxis_rangeslider_visible=False, height=560, template="plotly_white")
                    fig.update_xaxes(title_text="日期", row=2, col=1)
                    st.plotly_chart(fig, width="stretch")
        _deep_fragment()

    with tab_accuracy:
        st.subheader("过去 30 天信号准确率")
        st.markdown("""
        - **锚定实战价格**：基于**场内收盘价 (Close)**，不使用 IOPV/净值。
        - **有效信号**：仅统计偏多/偏空方向出现时的样本，**观望不计入准确率分母**。
        - **准确定义**：偏多信号后 5 日内价格上涨，或偏空信号后 5 日内价格下跌，则视为该次信号准确。
        - 准确率为历史统计，不代表未来表现；结论存在不确定性。
        """)
        acc_cols = ["代码", "名称", "明日建议", "建议操作频率", "信号准确率显示"]
        acc_cols = [c for c in acc_cols if c in df_display.columns]
        if acc_cols:
            acc_df = df_display[acc_cols].copy().replace([np.inf, -np.inf], np.nan).fillna("-")
            st.dataframe(
                acc_df,
                width="stretch",
                column_config={
                    "信号准确率显示": st.column_config.TextColumn("准确率30d"),
                },
                hide_index=True,
            )
            st.caption("准确率基于偏多/偏空方向的历史胜率，观望不计入分母；仅供参考，不保证未来结果。")

    st.divider()
    st.caption(f"ETF 列表：{ETF_LIST_PATH}")

    with st.expander("📖 每日操作建议算法说明", expanded=False):
        st.markdown(ALGORITHM_MARKDOWN)
