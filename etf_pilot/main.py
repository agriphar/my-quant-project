# -*- coding: utf-8 -*-
"""A 股跨境 ETF 监控工具 - Streamlit 入口（架构升级版）。"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

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

st.set_page_config(page_title="跨境 ETF 监控", page_icon="📈", layout="wide")
st.title("📈 A 股跨境 ETF 监控")

ensure_data_dir()
etf_list_full = load_etf_list()
if etf_list_full.empty:
    st.warning("未找到有效的 ETF 列表，请检查 data/ETF汇总.xlsx 是否包含「代码」「名称」列。")
    st.stop()

# ---------- Sidebar ----------
with st.sidebar:
    st.subheader("筛选与参数")
    # 类别过滤
    category_options = [CATEGORY_ALL] + list(CATEGORY_KEYWORDS.keys())
    selected_category = st.selectbox(
        "ETF 类别",
        options=category_options,
        index=0,
        help="按指数/主题筛选 ETF",
    )
    # MA 参数
    ma_short = st.number_input(
        "MA 短期",
        min_value=3,
        max_value=60,
        value=MA_SHORT_DEFAULT,
        step=1,
        help="短期均线周期",
    )
    ma_long = st.number_input(
        "MA 长期",
        min_value=5,
        max_value=120,
        value=MA_LONG_DEFAULT,
        step=1,
        help="长期均线周期",
    )
    if ma_short >= ma_long:
        st.warning("建议短期 < 长期")
    days = 180
    st.caption(f"数据：最近 {days} 个交易日 · 缓存 {CACHE_TTL}s")

# ---------- 缓存：按全量列表拉取，再按类别过滤显示 ----------
@st.cache_data(ttl=CACHE_TTL)
def _cached_fetch(symbol: str, days: int, ma_short: int, ma_long: int):
    """单只 ETF 日线+指标，避免重复请求 AkShare。"""
    return fetch_etf_daily(symbol, days=days, ma_short=ma_short, ma_long=ma_long)

def _cached_build(etf_df: pd.DataFrame, days: int, ma_short: int, ma_long: int) -> pd.DataFrame:
    def fetcher(sym: str, d: int, ms: int, ml: int):
        return _cached_fetch(sym, d, ms, ml)
    return build_monitor_table_advanced(etf_df, days=days, ma_short=ma_short, ma_long=ma_long, fetcher=fetcher)

@st.cache_data(ttl=CACHE_TTL)
def _cached_build_table(records: list[dict], days: int, ma_short: int, ma_long: int) -> pd.DataFrame:
    df_etf = pd.DataFrame(records)
    return _cached_build(df_etf, days=days, ma_short=ma_short, ma_long=ma_long)

with st.spinner("正在拉取日线并计算指标（RSI/布林带/多因子信号）…"):
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

# 按类别过滤
if selected_category != CATEGORY_ALL and selected_category in CATEGORY_KEYWORDS:
    keywords = CATEGORY_KEYWORDS[selected_category]
    mask = df_full["指数简称"].astype(str).str.contains(
        "|".join(keywords), case=False, na=False
    )
    df = df_full.loc[mask]
else:
    df = df_full

if df.empty:
    st.warning(f"类别「{selected_category}」下暂无 ETF，请切换类别或检查 data/ETF汇总.xlsx。")
    st.stop()

# 过滤掉仅因错误而存在的行（可选：在表格中保留并显示错误列）
df_display = df.copy()
# 信号列显示为 Emoji + 文字
df_display["信号"] = df_display["信号"].map({
    "买入": "🚀 买入",
    "持有": "🛡️ 持有",
    "减仓": "⚠️ 减仓",
}).fillna(df_display["信号"])

def _style_pct(df: pd.DataFrame, pct_col: str = "涨跌幅"):
    """对 DataFrame 的涨跌幅列加颜色热力图。"""
    if pct_col not in df.columns or df[pct_col].notna().sum() == 0:
        return df.style
    pct_min = df[pct_col].min()
    pct_max = df[pct_col].max()
    if pd.notna(pct_min) and pd.notna(pct_max) and pct_max > pct_min:
        return df.style.background_gradient(
            subset=[pct_col],
            cmap="RdYlGn",
            vmin=pct_min,
            vmax=pct_max,
        )
    return df.style

# ---------- Tabs ----------
tab_radar, tab_detail, tab_deep = st.tabs(["实时雷达", "策略详情", "个股深度分析"])

with tab_radar:
    st.caption("核心一览：最新价、涨跌幅、信号、建议仓位")
    show_cols = ["代码", "名称", "指数简称", "最新价", "涨跌幅", "信号", "建议仓位"]
    show_cols = [c for c in show_cols if c in df_display.columns]
    radar_df = df_display[show_cols]
    st.dataframe(
        _style_pct(radar_df),
        use_container_width=True,
        column_config={
            "最新价": st.column_config.NumberColumn(format="%.4f"),
            "涨跌幅": st.column_config.NumberColumn(format="%.2f%%"),
        },
        hide_index=True,
    )

with tab_detail:
    st.caption("多因子策略：MA、RSI、布林下轨、信号与建议仓位")
    detail_cols = ["代码", "名称", "指数简称", "最新价", "涨跌幅", "MA_short", "MA_long", "RSI", "BB_lower", "信号", "建议仓位"]
    detail_cols = [c for c in detail_cols if c in df_display.columns]
    detail_df = df_display[detail_cols]
    st.dataframe(
        _style_pct(detail_df),
        use_container_width=True,
        column_config={
            "最新价": st.column_config.NumberColumn(format="%.4f"),
            "涨跌幅": st.column_config.NumberColumn(format="%.2f%%"),
            "MA_short": st.column_config.NumberColumn(format="%.4f"),
            "MA_long": st.column_config.NumberColumn(format="%.4f"),
            "RSI": st.column_config.NumberColumn(format="%.1f"),
            "BB_lower": st.column_config.NumberColumn(format="%.4f"),
        },
        hide_index=True,
    )
    if "错误" in df.columns and df["错误"].notna().any():
        st.warning("部分标的获取失败，见下方错误信息。")
        err_df = df.loc[df["错误"].notna(), ["代码", "名称", "错误"]]
        st.dataframe(err_df, use_container_width=True, hide_index=True)

with tab_deep:
    st.caption("选择一只 ETF，查看带均线与布林带的交互式 K 线图")
    options = df_display["名称"].tolist()
    name_to_code = dict(zip(df_display["名称"], df_display["代码"]))
    selected_name = st.selectbox("选择标的", options=options, key="deep_select")
    if selected_name:
        code = name_to_code.get(selected_name)
        if code:
            with st.spinner("拉取 K 线数据…"):
                chart_df = get_etf_hist_for_chart(
                    symbol=code,
                    days=60,
                    ma_short=int(ma_short),
                    ma_long=int(ma_long),
                )
            if chart_df is None or chart_df.empty:
                st.warning("该标的 K 线数据获取失败，请稍后重试。")
            else:
                fig = make_subplots(
                    rows=2,
                    cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.06,
                    row_heights=[0.75, 0.25],
                    subplot_titles=(f"{selected_name} ({code})", "成交量"),
                )
                # K 线（需开盘、高、低、收）
                if all(c in chart_df.columns for c in ["开盘", "最高", "最低", "收盘"]):
                    fig.add_trace(
                        go.Candlestick(
                            x=chart_df["日期"],
                            open=chart_df["开盘"],
                            high=chart_df["最高"],
                            low=chart_df["最低"],
                            close=chart_df["收盘"],
                            name="K线",
                        ),
                        row=1,
                        col=1,
                    )
                else:
                    fig.add_trace(
                        go.Scatter(
                            x=chart_df["日期"],
                            y=chart_df["收盘"],
                            mode="lines",
                            name="收盘",
                            line=dict(color="blue", width=2),
                        ),
                        row=1,
                        col=1,
                    )
                if "MA_short" in chart_df.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=chart_df["日期"],
                            y=chart_df["MA_short"],
                            mode="lines",
                            name=f"MA{ma_short}",
                            line=dict(color="orange", width=1.5),
                        ),
                        row=1,
                        col=1,
                    )
                if "MA_long" in chart_df.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=chart_df["日期"],
                            y=chart_df["MA_long"],
                            mode="lines",
                            name=f"MA{ma_long}",
                            line=dict(color="green", width=1.5),
                        ),
                        row=1,
                        col=1,
                    )
                if "BB_upper" in chart_df.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=chart_df["日期"],
                            y=chart_df["BB_upper"],
                            mode="lines",
                            name="布林上轨",
                            line=dict(color="gray", width=1, dash="dot"),
                        ),
                        row=1,
                        col=1,
                    )
                if "BB_lower" in chart_df.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=chart_df["日期"],
                            y=chart_df["BB_lower"],
                            mode="lines",
                            name="布林下轨",
                            line=dict(color="gray", width=1, dash="dot"),
                        ),
                        row=1,
                        col=1,
                    )
                if "成交量" in chart_df.columns and chart_df["成交量"].notna().any():
                    fig.add_trace(
                        go.Bar(
                            x=chart_df["日期"],
                            y=chart_df["成交量"],
                            name="成交量",
                            marker_color="lightblue",
                            showlegend=False,
                        ),
                        row=2,
                        col=1,
                    )
                fig.update_layout(
                    xaxis_rangeslider_visible=False,
                    height=560,
                    template="plotly_white",
                )
                fig.update_xaxes(title_text="日期", row=2, col=1)
                st.plotly_chart(fig, use_container_width=True)

st.divider()
st.caption(f"ETF 列表配置：{ETF_LIST_PATH}")
st.markdown(
    "**信号说明**：🚀 买入 = 价格>MA20 且 RSI<70（看多）或触及布林下轨且缩量 · "
    "🛡️ 持有 · ⚠️ 减仓 = 跌破 MA20 或 RSI>80（超买）。"
    " **建议仓位**：按波动率计算，波动大仓位轻、平稳仓位重。"
)
