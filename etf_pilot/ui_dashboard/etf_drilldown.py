# -*- coding: utf-8 -*-
"""
ETF Drill-down — 单只标的详情页，与四层引擎对齐，仅展示该 ETF 的差异化信息。

不包含全局仪表盘逻辑（数据加载、筛选、列表）；由调用方传入已选中的 sel_row。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .signal_layer_ui import render_signal_layer_cards
from .risk_layer_ui import render_risk_layer_cards
from .confidence_layer_ui import render_confidence_layer_cards
from .decision_layer_ui import render_decision_layer_cards

# 四层区块样式：左框色、背景色、层名，用于区分层次
_LAYER_STYLES = [
    {"border": "#1565c0", "bg": "rgba(33, 150, 243, 0.08)", "label": "Signal Layer"},
    {"border": "#e65100", "bg": "rgba(255, 152, 0, 0.08)", "label": "Risk Layer"},
    {"border": "#6a1b9a", "bg": "rgba(156, 39, 176, 0.08)", "label": "Confidence Layer"},
    {"border": "#2e7d32", "bg": "rgba(76, 175, 80, 0.08)", "label": "Decision Layer"},
]


def _section_header(num: int, title: str, style: dict) -> str:
    """生成带层次感的区块标题 HTML。"""
    border = style["border"]
    bg = style["bg"]
    label = style["label"]
    return (
        f"<div style="
        f"border-left: 4px solid {border}; "
        f"background: {bg}; "
        f"padding: 0.6rem 1rem; "
        f"margin: 1.2rem 0 0.8rem 0; "
        f"border-radius: 0 6px 6px 0; "
        f"font-family: inherit;"
        f">"
        f"<span style='color: #78909c; font-size: 0.85em;'>#{num}</span> "
        f"<strong style='color: #37474f;'>{title}</strong>"
        f"<br>"
        f"<span style='color: {border}; font-size: 0.9em;'>{label}</span>"
        f"</div>"
    )


def _section_spacer() -> str:
    """区块之间的留白。"""
    return "<div style='height: 1.5rem;'></div>"


def _safe_get(row: pd.Series, key: str, default: str = "—"):
    v = row.get(key)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    if isinstance(v, float):
        return f"{v:.3f}" if key == "最新价" else f"{v:.2f}%" if key == "涨跌幅" else str(v)
    return str(v)


def render_etf_drilldown(sel_row: pd.Series, display_name: str) -> None:
    """
    渲染 ETF 详情页：仅展示该标的的四层结果，不重复全局仪表盘逻辑。

    参数:
    - sel_row: 该 ETF 在监控表中的一行（含 signal_states, risk_result, confidence_result, decision）
    - display_name: 展示用名称，如 "纳指ETF (513100)"
    """
    # ETF 身份：仅该标的的标识与行情
    name = _safe_get(sel_row, "名称", "—")
    code = _safe_get(sel_row, "代码", "—")
    price = sel_row.get("最新价")
    pct = sel_row.get("涨跌幅")
    price_str = f"{float(price):.3f}" if price is not None and not pd.isna(price) else "—"
    pct_str = f"{float(pct):.2f}%" if pct is not None and not pd.isna(pct) else "—"

    with st.container():
        st.markdown("### ETF Drill-down")
        st.markdown(
            f"**{name}** `{code}` · 最新价 **{price_str}** · 涨跌幅 **{pct_str}**"
        )
        st.markdown(_section_spacer(), unsafe_allow_html=True)

    # 1. GLOBAL MARKET STATE — Signal Layer
    st.markdown(
        _section_header(1, "GLOBAL MARKET STATE", _LAYER_STYLES[0]),
        unsafe_allow_html=True,
    )
    signal_states = sel_row.get("signal_states")
    if isinstance(signal_states, str):
        signal_states = {}
    state_stability = sel_row.get("state_stability")
    render_signal_layer_cards(signal_states, state_stability, title=display_name)
    st.markdown(_section_spacer(), unsafe_allow_html=True)

    # 2. RISK ENVIRONMENT — Risk Layer
    st.markdown(
        _section_header(2, "RISK ENVIRONMENT", _LAYER_STYLES[1]),
        unsafe_allow_html=True,
    )
    risk_result = sel_row.get("risk_result")
    if not isinstance(risk_result, dict):
        risk_result = {}
    render_risk_layer_cards(risk_result, title=display_name)
    st.markdown(_section_spacer(), unsafe_allow_html=True)

    # 3. SYSTEM CONFIDENCE — Confidence Layer
    st.markdown(
        _section_header(3, "SYSTEM CONFIDENCE", _LAYER_STYLES[2]),
        unsafe_allow_html=True,
    )
    confidence_result = sel_row.get("confidence_result")
    if not isinstance(confidence_result, dict):
        confidence_result = {}
    render_confidence_layer_cards(confidence_result, title=display_name)
    st.markdown(_section_spacer(), unsafe_allow_html=True)

    # 4. PORTFOLIO ACTION — Decision Layer
    st.markdown(
        _section_header(4, "PORTFOLIO ACTION", _LAYER_STYLES[3]),
        unsafe_allow_html=True,
    )
    decision = sel_row.get("decision")
    if not isinstance(decision, dict):
        decision = {}
    render_decision_layer_cards(decision, title=display_name)
