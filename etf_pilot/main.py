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
    get_rsr_panel,
    get_equal_weight_panel,
    ETF_LIST_PATH,
    ensure_data_dir,
)
from strategy.rsr_backtest import run_rsr_backtest
from strategy.equal_weight_backtest import run_equal_weight_backtest
from config.settings import (
    BACKTEST_YEARS,
    RSR_INITIAL_CASH,
    RSR_FEE_RATE,
    RSR_MIN_FEE,
    RSR_REBALANCE_FREQ,
    RSR_GLOBAL_MA20_THRESHOLD,
    EW_INITIAL_CASH,
    EW_FEE_RATE,
    EW_MIN_FEE,
    EW_DEVIATION_THRESHOLD,
    EW_REBALANCE_TRADING_DAYS,
)
from config.rsr_groups import get_code_to_group
from config.equal_weight_pool import get_pool_codes

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
    st.caption("核心一览：类型、最新价、涨跌幅、信号、建议仓位")
    show_cols = ["代码", "名称", "类型", "指数简称", "最新价", "涨跌幅", "信号", "建议仓位"]
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

with tab_backtest:
    st.caption("跨资产等权动态再平衡：5 只精选标的（纳指/标普/黄金/日经/红利）各 20%；每两周检查，任一权重偏离 20% 超过 ±3% 则再平衡；佣金万五、无最低。基准为 5 只简单平均不调仓。")
    if st.button("运行等权再平衡回测", key="ew_run"):
        pool_codes = get_pool_codes()
        with st.spinner("拉取 5 只标的日线并对齐日期…"):
            panel_ew = get_equal_weight_panel(pool_codes, years=BACKTEST_YEARS)
        if panel_ew is None or len(panel_ew) < 100:
            st.warning("5 只精选标的数据不足，无法回测。")
        else:
            daily_bt, metrics_bt, rebalance_dates = run_equal_weight_backtest(
                panel_ew,
                initial_cash=EW_INITIAL_CASH,
                fee_rate=EW_FEE_RATE,
                min_fee=EW_MIN_FEE,
                deviation_threshold=EW_DEVIATION_THRESHOLD,
                rebalance_interval_days=EW_REBALANCE_TRADING_DAYS,
            )
            if daily_bt.empty:
                st.warning("回测未产生有效结果。")
            else:
                fig_bt = go.Figure()
                fig_bt.add_trace(
                    go.Scatter(
                        x=daily_bt["日期"],
                        y=daily_bt["策略净值"],
                        mode="lines",
                        name="再平衡策略净值",
                        line=dict(color="rgb(33, 150, 243)", width=2),
                    )
                )
                fig_bt.add_trace(
                    go.Scatter(
                        x=daily_bt["日期"],
                        y=daily_bt["基准净值"],
                        mode="lines",
                        name="5只等权不调仓(基准)",
                        line=dict(color="rgb(158, 158, 158)", width=1.5, dash="dash"),
                    )
                )
                # 再平衡时刻标记点
                if rebalance_dates:
                    rb_pairs = [(d, float(daily_bt.loc[daily_bt["日期"] == d, "策略净值"].iloc[0])) for d in rebalance_dates if (daily_bt["日期"] == d).any()]
                    rb_dates = [p[0] for p in rb_pairs]
                    rb_nav = [p[1] for p in rb_pairs]
                    fig_bt.add_trace(
                        go.Scatter(
                            x=rb_dates,
                            y=rb_nav,
                            mode="markers",
                            name="再平衡",
                            marker=dict(symbol="triangle-up", size=10, color="red", line=dict(width=1, color="darkred")),
                        )
                    )
                fig_bt.update_layout(
                    title="等权再平衡策略 vs 5 只等权不调仓（红三角=再平衡时刻）",
                    xaxis_title="日期",
                    yaxis_title="净值",
                    height=420,
                    template="plotly_white",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                st.plotly_chart(fig_bt, use_container_width=True)

                st.subheader("收益对比")
                strat_ret = metrics_bt.get("累计收益率", 0) or 0
                bench_ret = metrics_bt.get("基准累计收益率", 0) or 0
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("策略累计收益率", f"{strat_ret * 100:.2f}%", f"{(strat_ret - bench_ret) * 100:+.2f}% vs 基准")
                with c2:
                    st.metric("策略最终净值", f"¥{metrics_bt.get('策略最终净值', 0):,.0f}", None)
                with c3:
                    st.metric("基准最终净值", f"¥{metrics_bt.get('基准最终净值', 0):,.0f}", None)

                st.subheader("性能指标")
                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    st.metric("年化收益率", f"{(metrics_bt.get('年化收益率') or 0) * 100:.2f}%", None)
                with m2:
                    st.metric("最大回撤", f"{(metrics_bt.get('最大回撤') or 0) * 100:.2f}%", None)
                with m3:
                    st.metric("夏普比率", f"{(metrics_bt.get('夏普比率') or 0):.2f}", None)
                with m4:
                    st.metric("再平衡次数", f"{metrics_bt.get('再平衡次数') or 0}", None)

                st.caption("红三角为触发再平衡的交易日（某标的权重偏离 20% 超过 ±3%）。")

st.divider()
st.caption(f"ETF 列表配置：{ETF_LIST_PATH}")

with st.expander("📖 点击查看深度策略与风控说明", expanded=False):
    st.markdown("""
**一、跨资产等权动态再平衡策略**

- **精选池**：5 只长期代表资产——513100 纳指、513500 标普、518880 黄金、513520 日经、510880 红利 ETF。
- **初始分配**：初始资金 50 万元，五只各 **20%** 仓位。
- **再平衡**：**每两周**（约 10 个交易日）检查一次；若某标的权重偏离 20% 超过 **±3%**（阈值可调），则触发再平衡：卖出超配、买入欠配，使五只重新回到 20%。
- **成本**：佣金 **0.0005**（万五），暂不设最低 5 元。
- **对比**：策略净值 vs **5 只简单平均、不调仓**的净值（买入持有等权）。图中**红三角**为每次再平衡发生的时刻。

---

**二、建议仓位说明**

> **为什么波动大的标的买得少、波动小的买得多？**

- 建议仓位根据**近 20 日收益率波动率**在全部标的中的相对水平计算：波动率越高，建议仓位越低；波动率越低，建议仓位越高。
- **逻辑**：同一笔资金，波动大的标的潜在回撤更大，用较小仓位控制单标的风险；波动小的标的更稳，可适当提高仓位，在风险可控前提下提高资金利用。
- 展示为 **高(60–80%) / 中(40–60%) / 低(20–40%)**，供参考，不构成具体买卖建议。
    """)
