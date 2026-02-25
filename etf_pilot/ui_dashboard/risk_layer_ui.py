# -*- coding: utf-8 -*-
"""
Risk Layer UI — 机构 Risk First，一眼看到环境是否危险。

回答：「当前环境是否适合配置？」
展示：整体风险等级（突出）、风险来源因素、突出不稳定性与信号分歧。无概率数字。
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

# Risk Engine 常量（与 risk_engine/assessment.py 一致）
RISK_FLAG_HIGH_VOLATILITY = "high_volatility"
RISK_FLAG_TREND_UNKNOWN = "trend_unknown"
RISK_FLAG_SIGNAL_CONFLICT = "signal_conflict"
RISK_FLAG_RAPID_TRANSITIONS = "rapid_transitions"

# -----------------------------------------------------------------------------
# 风险等级 → 中文 + 语义
# -----------------------------------------------------------------------------

RISK_LEVEL_LABELS = {
    "LOW": "低",
    "MEDIUM": "中",
    "HIGH": "高",
}

# 风险标志 → 展示文案（无数字、无概率）
RISK_FLAG_LABELS = {
    RISK_FLAG_HIGH_VOLATILITY: "高波动",
    RISK_FLAG_TREND_UNKNOWN: "趋势不明",
    RISK_FLAG_SIGNAL_CONFLICT: "信号分歧",
    RISK_FLAG_RAPID_TRANSITIONS: "状态快速切换",
}

# 需要特别突出的标志（不稳定性、信号冲突）
HIGHLIGHT_FLAGS = {RISK_FLAG_SIGNAL_CONFLICT, RISK_FLAG_RAPID_TRANSITIONS}

# 风险等级 → 徽章样式 (bg, fg)
RISK_LEVEL_STYLES = {
    "LOW": ("#e8f5e9", "#2e7d32"),      # 绿
    "MEDIUM": ("#fff8e1", "#f9a825"),    # 黄/琥珀
    "HIGH": ("#ffebee", "#c62828"),     # 红
}
UNKNOWN_RISK_STYLE = ("#eceff1", "#78909c")


def _risk_level_style(level: str | None) -> tuple[str, str]:
    if not level:
        return UNKNOWN_RISK_STYLE
    return RISK_LEVEL_STYLES.get(str(level).upper(), UNKNOWN_RISK_STYLE)


def get_risk_layer_display(risk_result: dict[str, Any] | None) -> dict[str, Any]:
    """
    将 Risk Engine 输出转为展示用（仅等级 + 因素标签，无概率）。

    返回:
        {
            "risk_level_cn": "高",
            "risk_factors": ["信号分歧", "状态快速切换"],
            "risk_level_raw": "HIGH",
            "is_highlight": True,  # 是否存在需突出的因素
        }
    """
    if not risk_result:
        return {
            "risk_level_cn": "—",
            "risk_factors": [],
            "risk_level_raw": None,
            "is_highlight": False,
        }
    level = risk_result.get("risk_level")
    flags = risk_result.get("risk_flags") or []
    level_cn = RISK_LEVEL_LABELS.get(str(level).upper() if level else "", "—")
    factors = [RISK_FLAG_LABELS.get(f, f) for f in flags if f in RISK_FLAG_LABELS]
    if not factors and flags:
        factors = list(flags)
    is_highlight = any(f in HIGHLIGHT_FLAGS for f in flags)
    return {
        "risk_level_cn": level_cn,
        "risk_factors": factors,
        "risk_level_raw": level,
        "is_highlight": is_highlight,
    }


def _badge_html(label: str, bg: str, fg: str, highlight: bool = False) -> str:
    border = "border: 1px solid #c62828;" if highlight else ""
    return (
        f'<span style="'
        f"display:inline-block;padding:0.25em 0.5em;border-radius:4px;"
        f"background-color:{bg};color:{fg};font-size:0.85em;font-weight:500;"
        f"{border}"
        f'">{label}</span>'
    )


def render_risk_layer_cards(
    risk_result: dict[str, Any] | None,
    title: str = "风险环境",
) -> None:
    """
    在 Streamlit 中渲染 Risk Layer：突出整体风险等级 + 风险来源因素。
    不展示任何概率或数字。
    """
    display = get_risk_layer_display(risk_result)
    if risk_result is None or (isinstance(risk_result, dict) and not risk_result):
        st.caption("暂无风险数据")
        return

    st.markdown(f"**{title}** · 当前环境是否危险？")
    risk_level_cn = display["risk_level_cn"]
    risk_level_raw = display["risk_level_raw"]
    factors = display["risk_factors"]
    is_highlight = display["is_highlight"]

    bg, fg = _risk_level_style(risk_level_raw)
    # 整体风险等级：大号突出
    st.markdown(
        f'<div style="margin-bottom:0.5em;"><small style="color:#757575;">整体风险</small></div>'
        f'<div style="font-size:1.2em;">{_badge_html(risk_level_cn, bg, fg, highlight=(risk_level_raw == "HIGH"))}</div>',
        unsafe_allow_html=True,
    )
    st.markdown("")
    # 风险来源因素
    if factors:
        st.markdown("**风险来源**")
        comps = []
        for f in factors:
            is_hl = f in ("信号分歧", "状态快速切换")
            if is_hl:
                comps.append(_badge_html(f, "#ffebee", "#c62828", highlight=True))
            else:
                comps.append(_badge_html(f, "#fff3e0", "#e65100", highlight=False))
        st.markdown(
            '<div style="margin-top:0.3em;">' + " &nbsp; ".join(comps) + "</div>",
            unsafe_allow_html=True,
        )
        if is_highlight:
            st.caption("⚠️ 存在信号分歧或状态快速切换，请谨慎评估。")
    else:
        st.caption("无额外风险因素。")


def build_risk_layer_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    从监控表构建 Risk Layer 展示表。
    列：代码, 名称, 最新价, 涨跌幅, 风险等级, 风险来源（合并为一段文案）
    """
    rows = []
    for _, row in df.iterrows():
        risk_result = row.get("risk_result")
        if isinstance(risk_result, str):
            risk_result = {}
        display = get_risk_layer_display(risk_result)
        factors_text = "；".join(display["risk_factors"]) if display["risk_factors"] else "—"
        rows.append({
            "代码": row.get("代码"),
            "名称": row.get("名称"),
            "最新价": row.get("最新价"),
            "涨跌幅": row.get("涨跌幅"),
            "风险等级": display["risk_level_cn"],
            "风险来源": factors_text,
            "_risk_level_raw": display["risk_level_raw"],
            "_is_highlight": display["is_highlight"],
        })
    return pd.DataFrame(rows)


def style_risk_layer_table(risk_df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """对风险等级列按等级上色；存在突出因素时整行或该行风险来源高亮。"""
    if "风险等级" not in risk_df.columns or "_risk_level_raw" not in risk_df.columns:
        return risk_df.style

    def _level_style(series: pd.Series) -> list[str]:
        out = []
        for idx in series.index:
            raw = risk_df.loc[idx, "_risk_level_raw"] if "_risk_level_raw" in risk_df.columns else None
            bg, fg = _risk_level_style(raw)
            out.append(f"background-color: {bg}; color: {fg}; font-weight: 600;")
        return out

    styled = risk_df.style.apply(
        _level_style,
        axis=0,
        subset=["风险等级"],
    )

    # 风险来源列：若有 _is_highlight 可加淡红底
    if "_is_highlight" in risk_df.columns and "风险来源" in risk_df.columns:
        def _source_style(series: pd.Series) -> list[str]:
            out = []
            for idx in series.index:
                hl = risk_df.loc[idx, "_is_highlight"] if "_is_highlight" in risk_df.columns else False
                if hl:
                    out.append("background-color: rgba(255,235,59,0.25); font-weight: 500;")
                else:
                    out.append("")
            return out
        styled = styled.apply(_source_style, axis=0, subset=["风险来源"])

    to_hide = [c for c in ["_risk_level_raw", "_is_highlight"] if c in styled.columns]
    if to_hide:
        styled = styled.hide(axis="columns", subset=to_hide)
    return styled
