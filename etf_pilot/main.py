# -*- coding: utf-8 -*-
"""跨境 ETF 决策辅助仪表盘：每日操作指导，不负责自动交易。"""
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
    drawdown_15pct_value,
)

st.set_page_config(page_title="跨境 ETF 决策辅助", page_icon="📊", layout="wide")
st.title("📊 跨境 ETF 决策辅助仪表盘")
st.caption("仅提供每日操作指导，不构成自动交易。")

ensure_data_dir()
etf_list_full = load_etf_list()
if etf_list_full.empty:
    st.warning("未找到有效的 ETF 列表，请检查 data/ETF汇总.xlsx 是否包含「代码」「名称」列。")
    st.stop()

# ---------- Sidebar ----------
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

# ---------- 缓存拉取与建表 ----------
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

if selected_category != CATEGORY_ALL and selected_category in CATEGORY_KEYWORDS:
    keywords = CATEGORY_KEYWORDS[selected_category]
    mask = df_full["指数简称"].astype(str).str.contains("|".join(keywords), case=False, na=False)
    df = df_full.loc[mask]
else:
    df = df_full

if df.empty:
    st.warning(f"类别「{selected_category}」下暂无 ETF。")
    st.stop()

# 按「建议操作频率」降序排序，便于优先看到需要操作的标的
df_display = df.copy()
if "建议操作频率" in df_display.columns:
    df_display = df_display.sort_values("建议操作频率", ascending=False).reset_index(drop=True)

# ---------- Tabs ----------
tab_dashboard, tab_radar, tab_deep, tab_accuracy = st.tabs(["决策看板", "实时雷达", "个股深度分析", "信号准确率"])

def _style_premium_column(series):
    """溢价率列配色：>1% 红，<-1% 绿，[-1%,1%] 灰。"""
    def cell(v):
        if v is None or (hasattr(v, "__float__") and pd.isna(v)):
            return ""
        try:
            x = float(v)
            if x > 1:
                return "background-color: rgba(244,67,54,0.28)"
            if x < -1:
                return "background-color: rgba(76,175,80,0.25)"
            return "background-color: rgba(158,158,158,0.2)"
        except (TypeError, ValueError):
            return ""
    return [cell(x) for x in series]

def _style_rsi_row(row_subset):
    """RSI 状态灯列配色：<45 青，45-70 绿，>70 橙，>80 红。按行传入 subset 的一行。"""
    rsi = row_subset.get("RSI") if hasattr(row_subset, "get") else None
    if rsi is None or pd.isna(rsi):
        return ["", ""]
    try:
        r = float(rsi)
        if r < 45:
            c = "rgba(0,188,212,0.35)"
        elif r <= 70:
            c = "rgba(76,175,80,0.25)"
        elif r <= 80:
            c = "rgba(255,152,0,0.35)"
        else:
            c = "rgba(244,67,54,0.35)"
        return [f"background-color: {c}", ""]
    except (TypeError, ValueError):
        return ["", ""]

with tab_dashboard:
    st.subheader("行情透视 · 偏离度 · 明日建议（按建议操作频率排序）")
    show_cols = [
        "代码", "名称", "最新价", "涨跌幅",
        "距一年高%", "距一年低%",
        "Bias_MA20", "Bias_MA60", "Bias_MA200",
        "明日建议", "建议操作频率", "溢价率显示", "RSI状态", "RSI", "信号准确率30d",
    ]
    show_cols = [c for c in show_cols if c in df_display.columns]
    table_df = df_display[show_cols].copy()

    def _row_style_simple(row):
        action = row.get("明日建议") if "明日建议" in row.index else None
        if action == "分批吸纳":
            return ["background-color: rgba(33,150,243,0.12)"] * len(row)
        if action == "套利离场":
            return ["background-color: rgba(156,39,176,0.12)"] * len(row)
        if action in ("观望/严禁追高", "溢价极高，建议减仓或观望"):
            return ["background-color: rgba(244,67,54,0.12)"] * len(row)
        return [""] * len(row)

    styled = table_df.style.apply(_row_style_simple, axis=1)
    if "溢价率显示" in table_df.columns and "溢价率" in df_display.columns:
        def _style_premium_display_row(row_subset):
            idx = row_subset.name if hasattr(row_subset, "name") else None
            pct = df_display.loc[idx, "溢价率"] if idx is not None and idx in df_display.index else row_subset.get("溢价率")
            if pct is None or (hasattr(pct, "__float__") and pd.isna(pct)):
                return [""]
            try:
                x = float(pct)
                if x > 1:
                    c = "background-color: rgba(244,67,54,0.28)"
                elif x < -1:
                    c = "background-color: rgba(76,175,80,0.25)"
                else:
                    c = "background-color: rgba(158,158,158,0.2)"
                return [c]
            except (TypeError, ValueError):
                return [""]
        styled = styled.apply(_style_premium_display_row, subset=["溢价率显示"], axis=1)
    if "RSI状态" in table_df.columns and "RSI" in table_df.columns:
        styled = styled.apply(_style_rsi_row, subset=["RSI状态", "RSI"], axis=1)
    st.dataframe(
        styled,
        use_container_width=True,
        column_config={
            "最新价": st.column_config.NumberColumn(format="%.4f"),
            "涨跌幅": st.column_config.NumberColumn(format="%.2f%%"),
            "距一年高%": st.column_config.NumberColumn(format="%.2f%%"),
            "距一年低%": st.column_config.NumberColumn(format="%.2f%%"),
            "Bias_MA20": st.column_config.NumberColumn(format="%.2f%%"),
            "Bias_MA60": st.column_config.NumberColumn(format="%.2f%%"),
            "Bias_MA200": st.column_config.NumberColumn(format="%.2f%%"),
            "溢价率显示": st.column_config.TextColumn("溢价率"),
            "RSI": st.column_config.NumberColumn(format="%.1f"),
            "信号准确率30d": st.column_config.NumberColumn(format="%.1f%%"),
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
            action = sel_row.get("明日建议", "持有观望")
            reason = sel_row.get("建议理由", "")
            name = sel_row.get("名称", "")
            st.info(f"**明天建议：{action}**  \n理由：{reason}")
            st.caption(f"标的：{name}")

with tab_radar:
    st.caption("实时行情：最新价、涨跌幅与均线/RSI 等具体数据（与决策看板不重复）")
    radar_cols = ["代码", "名称", "最新价", "涨跌幅", "MA5", "MA20", "MA60", "MA200", "RSI"]
    radar_cols = [c for c in radar_cols if c in df_display.columns]
    radar_df = df_display[radar_cols].copy()
    # RSI 列背景色：超跌青、安全绿、超买橙、危险红
    def _radar_rsi_style(series):
        def cell(v):
            if v is None or (hasattr(v, "__float__") and pd.isna(v)):
                return ""
            try:
                r = float(v)
                if r < 45:
                    return "background-color: rgba(0,188,212,0.2)"
                if r <= 70:
                    return "background-color: rgba(76,175,80,0.15)"
                if r <= 80:
                    return "background-color: rgba(255,152,0,0.2)"
                return "background-color: rgba(244,67,54,0.2)"
            except (TypeError, ValueError):
                return ""
        return [cell(x) for x in series]
    radar_styled = radar_df.style.apply(_radar_rsi_style, subset=["RSI"], axis=0) if "RSI" in radar_df.columns else radar_df.style
    st.dataframe(
        radar_styled,
        use_container_width=True,
        column_config={
            "最新价": st.column_config.NumberColumn(format="%.4f"),
            "涨跌幅": st.column_config.NumberColumn(format="%.2f%%"),
            "MA5": st.column_config.NumberColumn(format="%.4f"),
            "MA20": st.column_config.NumberColumn(format="%.4f"),
            "MA60": st.column_config.NumberColumn(format="%.4f"),
            "MA200": st.column_config.NumberColumn(format="%.4f"),
            "RSI": st.column_config.NumberColumn(format="%.1f"),
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
                st.plotly_chart(fig, use_container_width=True)
    _deep_fragment()

with tab_accuracy:
    st.subheader("过去 30 天信号准确率")
    st.markdown("""
    若按当日「明日建议」操作（分批吸纳视为买入、套利离场视为卖出），统计 **3 日后收益** 是否与建议一致：
    - 建议**分批吸纳**且 3 日后**上涨** → 计为正确
    - 建议**套利离场**且 3 日后**下跌** → 计为正确  
    仅统计有明确买卖建议的交易日，「持有观望」不参与。准确率 = 正确次数 / 总次数。
    """)
    acc_cols = ["代码", "名称", "明日建议", "建议操作频率", "信号准确率30d"]
    acc_cols = [c for c in acc_cols if c in df_display.columns]
    if acc_cols:
        st.dataframe(
            df_display[acc_cols],
            use_container_width=True,
            column_config={"信号准确率30d": st.column_config.NumberColumn(format="%.1f%%")},
            hide_index=True,
        )

st.divider()
st.caption(f"ETF 列表：{ETF_LIST_PATH}")

with st.expander("📖 每日操作建议算法说明", expanded=False):
    st.markdown("""
**操作逻辑（Action Logic）**

- **[买入补仓] 分批吸纳**  
  当价格回落至 **MA60 附近**（上下约 2%）且 **RSI < 45** 时，标记为「分批吸纳」，适合逢低加仓。

- **[持有观望]**  
  当价格在均线之上平稳运行，且没有触及 MA60 吸纳区或布林上轨时，标记为「持有观望」。

- **[套利卖出] 套利离场**  
  当价格**触及布林带上轨**时，标记为「套利离场」，可考虑兑现部分利润。（若网格利润覆盖 5 倍手续费时更佳，本仪表盘以触及上轨为主要条件。）

**行情透视与偏离度**

- **距一年高% / 距一年低%**：当前价相对过去约 250 个交易日最高价、最低价的位置，用于判断价格所处空间。
- **Bias_MA20 / MA60 / MA200**：价格相对三条均线的乖离率（百分比），偏离过大时需警惕回调或反弹。
- **溢价率**：由 IOPV 与历史净值计算；(市价 - IOPV) / IOPV × 100%。数字后为**百分位进度条**（满格=近期最贵）。>1% 标红、<-1% 标绿、[-1%,1%] 灰色。**动态信号**：当前溢价 < 平均溢价+1% 时按技术面给建议；当前溢价 > 平均溢价×1.5 且分位>90% 时强制「溢价极高，建议减仓或观望」。
- **RSI 状态灯**：<45 青色超跌准备买、45–70 绿色安全、>70 橙色警惕超买、>80 红色危险准备卖。
- **自动刷新**：数据与溢价率随页面缓存（TTL）更新，开盘期间或收盘后刷新页面即可获取最新 IOPV。
- **极端风险模拟**：侧栏可输入当前账户/持仓市值，查看若发生 15% 回撤后的金额，仅供压力测试参考。
    """)
