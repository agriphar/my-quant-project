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
    fetch_etf_hist_for_backtest,
    ETF_LIST_PATH,
    ensure_data_dir,
)
from strategy.grid_backtest import run_grid_backtest
from config.settings import BACKTEST_YEARS, GRID_SYMBOL_DEFAULT

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
tab_radar, tab_detail, tab_deep, tab_backtest = st.tabs(["实时雷达", "策略详情", "个股深度分析", "策略回测"])

with tab_radar:
    st.caption("清爽一览：代码、名称、现价、今日波动率、信号（步进式网格逻辑）")
    show_cols = ["代码", "名称", "最新价", "今日波动率", "信号"]
    show_cols = [c for c in show_cols if c in df_display.columns]
    radar_df = df_display[show_cols].copy()
    if "最新价" in radar_df.columns:
        radar_df = radar_df.rename(columns={"最新价": "现价"})
    st.dataframe(
        radar_df,
        use_container_width=True,
        column_config={
            "现价": st.column_config.NumberColumn(format="%.4f"),
            "今日波动率": st.column_config.NumberColumn(format="%.2f%%"),
        },
        hide_index=True,
    )

with tab_detail:
    st.caption("资产分级策略：类型、MA/RSI/布林、偏离度、追高提示、补仓建议、信号与建议仓位")
    detail_cols = ["代码", "名称", "类型", "指数简称", "最新价", "涨跌幅", "偏离度", "追高提示", "MA_short", "MA_long", "RSI", "BB_lower", "信号", "建议仓位", "补仓建议"]
    detail_cols = [c for c in detail_cols if c in df_display.columns]
    detail_df = df_display[detail_cols]
    st.dataframe(
        _style_pct(detail_df),
        use_container_width=True,
        column_config={
            "最新价": st.column_config.NumberColumn(format="%.4f"),
            "涨跌幅": st.column_config.NumberColumn(format="%.2f%%"),
            "偏离度": st.column_config.NumberColumn(format="%.2f"),
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
    @st.fragment
    def _deep_fragment():
        st.caption("选择一只 ETF，查看带均线与布林带的交互式 K 线图")
        options = [f"{row['名称']} ({row['代码']})" for _, row in df_display.iterrows()]
        display_to_code = {f"{row['名称']} ({row['代码']})": str(row["代码"]) for _, row in df_display.iterrows()}
        selected_display = st.selectbox("选择标的", options=options, key="deep_select")
        if selected_display:
            code = display_to_code.get(selected_display)
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
                        subplot_titles=(selected_display, "成交量"),
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

    _deep_fragment()

with tab_backtest:
    @st.fragment
    def _backtest_fragment():
        st.caption("步进式网格做T：初始 50 万、50% 底仓、5% 一格；High/Low 触发，last_op_price 步进；成本 max(成交额×0.0012, 5) 元。")
        full_codes = sorted(etf_list_full["代码"].astype(str).unique().tolist())
        name_by_code = dict(zip(etf_list_full["代码"].astype(str), etf_list_full["名称"]))
        grid_symbol = st.selectbox(
            "网格标的",
            options=full_codes if full_codes else [""],
            index=full_codes.index(GRID_SYMBOL_DEFAULT) if full_codes and GRID_SYMBOL_DEFAULT in full_codes else 0,
            format_func=lambda c: f"{name_by_code.get(c, c)} ({c})" if c else "请先加载 ETF 列表",
            key="grid_symbol_select",
        )
        if st.button("运行网格回测", key="grid_run"):
            if not (grid_symbol and str(grid_symbol).strip()):
                st.warning("请选择网格标的。")
            else:
                grid_name = name_by_code.get(grid_symbol, grid_symbol)
                with st.spinner(f"拉取 {grid_name}({grid_symbol}) 日线…"):
                    series_grid = fetch_etf_hist_for_backtest(grid_symbol, years=BACKTEST_YEARS)
                if series_grid is None or len(series_grid) < 50:
                    st.warning(f"标的 {grid_name}({grid_symbol}) 日线数据不足。")
                else:
                    daily_grid, metrics_grid, grid_trades = run_grid_backtest(series_grid, debug=True)
                    if daily_grid.empty:
                        st.warning("回测未产生有效结果。")
                    else:
                        # 两条线：1. 策略净值  2. 标的收盘价（基准，归一化到 100）
                        close_series = series_grid.set_index("日期").reindex(daily_grid["日期"]).ffill().bfill()["收盘"]
                        base_norm = (close_series / close_series.iloc[0] * 100).values if close_series.iloc[0] and close_series.iloc[0] > 0 else None
                        nav_norm = (daily_grid["网格净值"].values / 500_000 * 100)
                        fig_bt = go.Figure()
                        fig_bt.add_trace(
                            go.Scatter(
                                x=daily_grid["日期"],
                                y=nav_norm,
                                mode="lines",
                                name="策略净值(×100/50万)",
                                line=dict(color="rgb(76, 175, 80)", width=2),
                            )
                        )
                        if base_norm is not None:
                            fig_bt.add_trace(
                                go.Scatter(
                                    x=daily_grid["日期"],
                                    y=base_norm,
                                    mode="lines",
                                    name="标的收盘价(基准, 归一化100)",
                                    line=dict(color="rgb(158, 158, 158)", width=1.5, dash="dash"),
                                )
                            )
                        buy_trades = [t for t in grid_trades if t.get("方向") == "买入"]
                        sell_trades = [t for t in grid_trades if t.get("方向") == "卖出"]
                        nav_by_date = daily_grid.set_index("日期")["网格净值"]
                        if buy_trades:
                            valid_b = [(t["日期"], nav_by_date.loc[t["日期"]] / 500_000 * 100) for t in buy_trades if t["日期"] in nav_by_date.index]
                            if valid_b:
                                fig_bt.add_trace(go.Scatter(x=[p[0] for p in valid_b], y=[p[1] for p in valid_b], mode="markers", name="买入", marker=dict(symbol="circle", size=6, color="green")))
                        if sell_trades:
                            valid_s = [(t["日期"], nav_by_date.loc[t["日期"]] / 500_000 * 100) for t in sell_trades if t["日期"] in nav_by_date.index]
                            if valid_s:
                                fig_bt.add_trace(go.Scatter(x=[p[0] for p in valid_s], y=[p[1] for p in valid_s], mode="markers", name="卖出", marker=dict(symbol="circle", size=6, color="red")))
                        fig_bt.update_layout(
                            title=f"网格回测：{grid_name} {grid_symbol}",
                            xaxis_title="日期",
                            yaxis_title="净值/基准(归一化)",
                            height=420,
                            template="plotly_white",
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        )
                        st.plotly_chart(fig_bt, use_container_width=True)

                        # 清爽表格：代码、名称、现价、今日波动率、累计网格利润（一行）
                        vol_20 = None
                        if "收盘" in series_grid.columns and len(series_grid) >= 20:
                            ret = series_grid["收盘"].pct_change().dropna().tail(20)
                            vol_20 = float(ret.std() * 100) if len(ret) > 0 else None
                        summary = pd.DataFrame([{
                            "代码": grid_symbol,
                            "名称": grid_name,
                            "现价": metrics_grid.get("现价"),
                            "今日波动率%": round(vol_20, 2) if vol_20 is not None else None,
                            "累计网格利润": round(metrics_grid.get("累计网格利润", 0), 2),
                        }])
                        st.subheader("回测结果一览")
                        st.dataframe(summary, use_container_width=True, hide_index=True,
                                     column_config={"现价": st.column_config.NumberColumn(format="%.4f")})

                        # 手续费统计
                        total_fee = metrics_grid.get("总手续费") or 0
                        fee_pct = metrics_grid.get("手续费占利润比pct") or 0
                        st.metric("总手续费", f"¥{total_fee:,.2f}", f"占利润 {fee_pct:.1f}%")

                        # 操作日志：最近 10 次网格成交
                        st.subheader("最近 10 次网格成交")
                        last_10 = grid_trades[-10:] if len(grid_trades) >= 10 else grid_trades
                        if last_10:
                            log_df = pd.DataFrame([
                                {"时间": t["日期"].strftime("%Y-%m-%d"), "方向": t["方向"], "价格": t["成交价"], "手续费": t["手续费"]}
                                for t in last_10
                            ])
                            st.dataframe(log_df, use_container_width=True, hide_index=True)
                        else:
                            st.caption("无网格成交记录（仅初始底仓）。")
    _backtest_fragment()

st.divider()
st.caption(f"ETF 列表配置：{ETF_LIST_PATH}")

with st.expander("📖 步进式网格做T 说明", expanded=False):
    st.markdown("""
**步进式网格 (Stepping Grid)**

- **资金**：初始 50 万元，**50% 底仓**（首日收盘价买入），**50% 现金**用于网格做 T；每格为总资产的 **5%**。
- **last_op_price**：初始为回测第一天收盘价。每次成交后更新为本次成交价。
- **买入**：当日 **Low** 触及 `last_op_price × (1 - 1.2%)` 则买入一格，并更新 last_op_price。
- **卖出**：当日 **High** 触及 `last_op_price × (1 + 1.2%)` 且有多仓则卖出一格，并更新 last_op_price。
- **同一天**可先买后卖（波动大时同时触发）。
- **成本**：每笔 `max(成交额 × 0.0012, 5)` 元（万一二，最低 5 元）。回测输出总手续费及占利润百分比。
- **信号**：实时雷达中，默认网格标的（513110）按「现价 vs 近 30 日均价」±1.2% 给出 买入/卖出/持有，与步进逻辑一致。
    """)
