# -*- coding: utf-8 -*-
"""
Decision Layer UI — 机构仪表盘风格，决策作为前序各层的结果呈现。

不模仿交易软件；与置信度分开展示；展示操作倾向、激进程度与推理标签；避免紧迫性话术。
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

# -----------------------------------------------------------------------------
# 动作 → 机构用语（无「买/卖/补仓/减仓/立即/赶紧」）
# -----------------------------------------------------------------------------

ACTION_LABELS = {
    "INCREASE": "增配倾向",
    "HOLD": "持有",
    "REDUCE": "减配倾向",
    "WAIT": "观望",
}

AGGRESSIVENESS_LABELS = {
    "LOW": "低",
    "MEDIUM": "中",
    "HIGH": "高",
}

# reason_tag → 简短说明（机构化、非紧迫）
REASON_TAG_EXPLANATIONS = {
    "bullish_signals": "信号偏多",
    "bearish_signals": "信号偏空",
    "neutral_signals": "信号中性",
    "uncertain_signals": "信号不确定",
    "high_risk_constraint": "高风险约束",
    "medium_risk_constraint": "中等风险约束",
    "high_confidence": "置信度较高",
    "low_confidence": "置信度较低",
}

ACTION_STYLES = {
    "INCREASE": ("#e8f5e9", "#2e7d32"),
    "HOLD": ("#f5f5f5", "#616161"),
    "REDUCE": ("#ffebee", "#c62828"),
    "WAIT": ("#fff8e1", "#f9a825"),
}
AGGRESSIVENESS_STYLES = {
    "LOW": ("#e8f5e9", "#2e7d32"),
    "MEDIUM": ("#fff8e1", "#f9a825"),
    "HIGH": ("#ffebee", "#c62828"),
}
UNKNOWN_STYLE = ("#eceff1", "#78909c")


def _action_style(action: str | None) -> tuple[str, str]:
    if not action:
        return UNKNOWN_STYLE
    return ACTION_STYLES.get(str(action).upper(), UNKNOWN_STYLE)


def _aggressiveness_style(agg: str | None) -> tuple[str, str]:
    if not agg:
        return UNKNOWN_STYLE
    return AGGRESSIVENESS_STYLES.get(str(agg).upper(), UNKNOWN_STYLE)


def get_decision_layer_display(decision: dict[str, Any] | None) -> dict[str, Any]:
    """
    将 Decision Engine 输出转为展示用（仅操作、激进程度、推理标签说明，与置信度分离）。

    返回:
        {
            "action_cn": "增配倾向",
            "aggressiveness_cn": "中",
            "action_raw": "INCREASE",
            "aggressiveness_raw": "MEDIUM",
            "reason_explanations": ["信号偏多", "置信度较高"],
        }
    """
    if not decision:
        return {
            "action_cn": "—",
            "aggressiveness_cn": "—",
            "action_raw": None,
            "aggressiveness_raw": None,
            "reason_explanations": [],
        }
    action = decision.get("action")
    aggressiveness = decision.get("aggressiveness")
    tags = decision.get("reason_tags") or []
    action_cn = ACTION_LABELS.get(str(action).upper() if action else "", "—")
    agg_cn = AGGRESSIVENESS_LABELS.get(str(aggressiveness).upper() if aggressiveness else "", "—")
    explanations = [REASON_TAG_EXPLANATIONS.get(t, t) for t in tags]
    return {
        "action_cn": action_cn,
        "aggressiveness_cn": agg_cn,
        "action_raw": action,
        "aggressiveness_raw": aggressiveness,
        "reason_explanations": explanations,
    }


def _badge_html(label: str, bg: str, fg: str) -> str:
    return (
        f'<span style="'
        f"display:inline-block;padding:0.2em 0.45em;border-radius:4px;"
        f"background-color:{bg};color:{fg};font-size:0.85em;font-weight:500;"
        f'">{label}</span>'
    )


def render_decision_layer_cards(
    decision: dict[str, Any] | None,
    title: str = "组合操作",
) -> None:
    """
    在 Streamlit 中渲染 Decision Layer：操作倾向 + 激进程度 + 推理标签说明。
    与置信度分开；决策呈现为前序各层（信号、风险、置信度）的综合结果。无紧迫性话术。
    """
    display = get_decision_layer_display(decision)
    if decision is None or (isinstance(decision, dict) and not decision):
        st.caption("暂无决策数据")
        return

    st.markdown(f"**{title}** · 建议操作（由信号 → 风险 → 置信度 综合得出）")
    action_cn = display["action_cn"]
    agg_cn = display["aggressiveness_cn"]
    action_raw = display["action_raw"]
    agg_raw = display["aggressiveness_raw"]
    explanations = display["reason_explanations"]

    # 操作倾向（与置信度分开展示）
    bg_a, fg_a = _action_style(action_raw)
    st.markdown(
        f'<div style="margin-bottom:0.5em;"><small style="color:#757575;">操作倾向</small></div>'
        f'<div style="font-size:1.15em;">{_badge_html(action_cn, bg_a, fg_a)}</div>',
        unsafe_allow_html=True,
    )
    st.markdown("")
    # 激进程度
    st.markdown("**激进程度**")
    bg_agg, fg_agg = _aggressiveness_style(agg_raw)
    st.markdown(
        f'<div style="margin-top:0.2em;">{_badge_html(agg_cn, bg_agg, fg_agg)}</div>',
        unsafe_allow_html=True,
    )
    st.markdown("")
    # 推理标签说明
    st.markdown("**推理依据**")
    if explanations:
        tags_html = " &nbsp; ".join(
            _badge_html(e, "#e3f2fd", "#1565c0") for e in explanations
        )
        st.markdown(f'<div style="margin-top:0.2em;">{tags_html}</div>', unsafe_allow_html=True)
    else:
        st.caption("—")


def build_decision_layer_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    从监控表构建 Decision Layer 展示表。
    列：代码, 名称, 最新价, 涨跌幅, 操作倾向, 激进程度, 推理依据（合并为一段）
    """
    rows = []
    for _, row in df.iterrows():
        dec = row.get("decision")
        if isinstance(dec, str):
            dec = {}
        display = get_decision_layer_display(dec)
        reason_text = "；".join(display["reason_explanations"]) if display["reason_explanations"] else "—"
        rows.append({
            "代码": row.get("代码"),
            "名称": row.get("名称"),
            "最新价": row.get("最新价"),
            "涨跌幅": row.get("涨跌幅"),
            "操作倾向": display["action_cn"],
            "激进程度": display["aggressiveness_cn"],
            "推理依据": reason_text,
            "_action_raw": display["action_raw"],
            "_aggressiveness_raw": display["aggressiveness_raw"],
        })
    return pd.DataFrame(rows)


def style_decision_layer_table(dec_df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """对操作倾向、激进程度列按语义上色。"""
    styled = dec_df.style
    if "操作倾向" in dec_df.columns and "_action_raw" in dec_df.columns:
        def _action_style_col(series: pd.Series) -> list[str]:
            out = []
            for idx in series.index:
                raw = dec_df.loc[idx, "_action_raw"] if "_action_raw" in dec_df.columns else None
                bg, fg = _action_style(raw)
                out.append(f"background-color: {bg}; color: {fg}; font-weight: 600;")
            return out
        styled = styled.apply(_action_style_col, axis=0, subset=["操作倾向"])
    if "激进程度" in dec_df.columns and "_aggressiveness_raw" in dec_df.columns:
        def _agg_style_col(series: pd.Series) -> list[str]:
            out = []
            for idx in series.index:
                raw = dec_df.loc[idx, "_aggressiveness_raw"] if "_aggressiveness_raw" in dec_df.columns else None
                bg, fg = _aggressiveness_style(raw)
                out.append(f"background-color: {bg}; color: {fg}; font-weight: 500;")
            return out
        styled = styled.apply(_agg_style_col, axis=0, subset=["激进程度"])
    to_hide = [c for c in ["_action_raw", "_aggressiveness_raw"] if c in styled.columns]
    if to_hide:
        styled = styled.hide(axis="columns", subset=to_hide)
    return styled
