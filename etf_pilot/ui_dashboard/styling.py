# -*- coding: utf-8 -*-
"""表格行样式、溢价/RSI/明日建议显示规则；类别筛选与排序（纯数据驱动，无业务逻辑）。"""
import pandas as pd


def filter_by_category(
    df_full: pd.DataFrame,
    selected_category: str,
    category_all: str,
    category_keywords: dict,
) -> pd.DataFrame:
    """按所选 ETF 类别筛选：用指数简称或名称含任一关键词即归入该类。"""
    if selected_category != category_all and selected_category in category_keywords:
        keywords = category_keywords[selected_category]
        pattern = "|".join(keywords)
        col_simple = df_full["指数简称"].astype(str)
        col_name = df_full["名称"].astype(str) if "名称" in df_full.columns else pd.Series("", index=df_full.index)
        mask = col_simple.str.contains(pattern, case=False, na=False) | col_name.str.contains(pattern, case=False, na=False)
        return df_full.loc[mask]
    return df_full


def sort_for_dashboard(df: pd.DataFrame) -> pd.DataFrame:
    """按「建议操作频率」降序排序，便于优先看到需要操作的标的。"""
    if "建议操作频率" not in df.columns:
        return df.copy()
    return df.sort_values("建议操作频率", ascending=False).reset_index(drop=True)


def add_明日建议_warning_prefix(table_df: pd.DataFrame, df_display: pd.DataFrame) -> pd.DataFrame:
    """溢价分位60d >= 90 时在明日建议前加 ⚠️。"""
    if "明日建议" not in table_df.columns or "溢价分位60d" not in df_display.columns:
        return table_df
    out = table_df.copy()
    out["明日建议"] = table_df.apply(
        lambda r: "⚠️ " + str(r["明日建议"]) if (df_display.loc[r.name, "溢价分位60d"] or 0) >= 90 else r["明日建议"],
        axis=1,
    )
    return out


def _row_style_simple(row: pd.Series, df_display: pd.DataFrame) -> list:
    """单行背景色：样本极少/数据不足/建议类型；信号分歧时加边框提示。"""
    if "样本极少" in df_display.columns:
        try:
            if df_display.loc[row.name, "样本极少"] is True:
                return ["background-color: rgba(255,235,59,0.22)"] * len(row)
        except (KeyError, TypeError):
            pass
    # 用内部「建议类型」判断行色，避免依赖展示文案
    advice_type = None
    if "建议类型" in df_display.columns:
        try:
            advice_type = df_display.loc[row.name, "建议类型"]
        except (KeyError, TypeError):
            pass
    display_val = row.get("明日建议") if "明日建议" in row.index else None
    if isinstance(display_val, str) and display_val.startswith("⚠️ "):
        display_val = display_val.replace("⚠️ ", "")
    if display_val and isinstance(display_val, str) and (
        "有效数据仅" in display_val or "缺少 IOPV" in display_val or "溢价数据不足" in display_val or "数据不足" in display_val
    ):
        return ["background-color: rgba(255,152,0,0.2)"] * len(row)
    if advice_type == "强烈建议补仓":
        return ["background-color: rgba(33,150,243,0.12)"] * len(row)
    if advice_type == "建议套利/减仓":
        return ["background-color: rgba(156,39,176,0.12)"] * len(row)
    if advice_type == "维持观望/持有":
        return ["background-color: rgba(255,193,7,0.12)"] * len(row)
    return [""] * len(row)


def _style_信号分歧(row_subset: pd.Series, df_display: pd.DataFrame) -> list:
    """信号分歧列或明日建议列：存在分歧时高亮，提示综合判断。"""
    idx = row_subset.name if hasattr(row_subset, "name") else None
    if idx is None or "信号分歧" not in df_display.columns:
        return [""]
    try:
        if df_display.loc[idx, "信号分歧"] is True:
            return ["background-color: rgba(255,193,7,0.25); font-weight: 500;"]
    except (KeyError, TypeError):
        pass
    return [""]


def _style_premium_display_row(row_subset: pd.Series, df_display: pd.DataFrame):
    """溢价率显示列背景：>1% 红，<-1% 绿，否则灰。"""
    idx = row_subset.name if hasattr(row_subset, "name") else None
    pct = df_display.loc[idx, "溢价率"] if idx is not None and idx in df_display.index else row_subset.get("溢价率")
    if pct is None or (hasattr(pct, "__float__") and pd.isna(pct)):
        return [""]
    try:
        x = float(pct)
        if x > 1:
            return ["background-color: rgba(244,67,54,0.28)"]
        if x < -1:
            return ["background-color: rgba(76,175,80,0.25)"]
        return ["background-color: rgba(158,158,158,0.2)"]
    except (TypeError, ValueError):
        return [""]


def _style_明日建议_high_premium(row: pd.Series, df_display: pd.DataFrame) -> list:
    """明日建议列：溢价分位60d >= 90 时红字加粗。"""
    idx = row.name
    pctile = df_display.loc[idx, "溢价分位60d"] if idx in df_display.index else 0
    return ["color: #c62828; font-weight: 600;" if (pctile or 0) >= 90 else ""]


def style_dashboard_table(table_df: pd.DataFrame, df_display: pd.DataFrame):
    """
    对决策看板表格应用行样式、溢价列样式、明日建议列样式、信号分歧高亮。
    返回 Styler，供 st.dataframe(styled, ...) 使用。
    """
    styled = table_df.style.apply(
        lambda r: _row_style_simple(r, df_display),
        axis=1,
    )
    if "溢价率显示" in table_df.columns and "溢价率" in df_display.columns:
        styled = styled.apply(
            lambda r: _style_premium_display_row(r, df_display),
            subset=["溢价率显示"],
            axis=1,
        )
    if "明日建议" in table_df.columns and "溢价分位60d" in df_display.columns:
        styled = styled.apply(
            lambda r: _style_明日建议_high_premium(r, df_display),
            subset=["明日建议"],
            axis=1,
        )
    if "信号分歧显示" in table_df.columns and "信号分歧" in df_display.columns:
        styled = styled.apply(
            lambda r: _style_信号分歧(r, df_display),
            subset=["信号分歧显示"],
            axis=1,
        )
    return styled


def radar_rsi_style(series: pd.Series) -> list:
    """RSI 列背景色：<45 青、≤70 绿、≤80 橙、>80 红。"""
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


def style_radar_rsi(radar_df: pd.DataFrame):
    """对实时雷达表应用 RSI 列样式。"""
    if "RSI" not in radar_df.columns:
        return radar_df.style
    return radar_df.style.apply(radar_rsi_style, subset=["RSI"], axis=0)
