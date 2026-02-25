# -*- coding: utf-8 -*-
"""
Confidence Layer UI — 防止系统「装确定」，独立于决策展示信号可信度。

回答：「当前信号有多值得信任？」
展示：置信度等级（与买卖方向无关）、一致 vs 冲突 可视化，无百分比精度。
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

# Confidence Engine 原因常量（与 confidence_engine/assessment.py 一致）
REASON_HIGH_SIGNAL_AGREEMENT = "high_signal_agreement"
REASON_LOW_SIGNAL_AGREEMENT = "low_signal_agreement"
REASON_STABLE_REGIME = "stable_regime"
REASON_UNSTABLE_REGIME = "unstable_regime"
REASON_PERSISTENT_SIGNALS = "persistent_signals"
REASON_VOLATILE_SIGNALS = "volatile_signals"
REASON_VALUATION_TREND_ALIGNED = "valuation_trend_aligned"
REASON_VALUATION_TREND_CONFLICT = "valuation_trend_conflict"

# -----------------------------------------------------------------------------
# 原因 → 展示文案（无百分比、无数值）
# -----------------------------------------------------------------------------

REASON_LABELS = {
    REASON_HIGH_SIGNAL_AGREEMENT: "信号一致",
    REASON_LOW_SIGNAL_AGREEMENT: "信号分歧",
    REASON_STABLE_REGIME: "制度稳定",
    REASON_UNSTABLE_REGIME: "制度不稳",
    REASON_PERSISTENT_SIGNALS: "信号持续",
    REASON_VOLATILE_SIGNALS: "信号波动",
    REASON_VALUATION_TREND_ALIGNED: "估值与趋势一致",
    REASON_VALUATION_TREND_CONFLICT: "估值与趋势冲突",
}

# 支持置信（agreement / 提升可信度）
REASONS_AGREEMENT = {
    REASON_HIGH_SIGNAL_AGREEMENT,
    REASON_STABLE_REGIME,
    REASON_PERSISTENT_SIGNALS,
    REASON_VALUATION_TREND_ALIGNED,
}

# 削弱置信（conflict / 降低可信度）
REASONS_CONFLICT = {
    REASON_LOW_SIGNAL_AGREEMENT,
    REASON_UNSTABLE_REGIME,
    REASON_VOLATILE_SIGNALS,
    REASON_VALUATION_TREND_CONFLICT,
}

CONFIDENCE_LEVEL_LABELS = {"LOW": "低", "MEDIUM": "中", "HIGH": "高"}
CONFIDENCE_STYLES = {
    "HIGH": ("#e8f5e9", "#2e7d32"),
    "MEDIUM": ("#fff8e1", "#f9a825"),
    "LOW": ("#ffebee", "#c62828"),
}
UNKNOWN_CONF_STYLE = ("#eceff1", "#78909c")


def _confidence_style(level: str | None) -> tuple[str, str]:
    if not level:
        return UNKNOWN_CONF_STYLE
    return CONFIDENCE_STYLES.get(str(level).upper(), UNKNOWN_CONF_STYLE)


def get_confidence_layer_display(confidence_result: dict[str, Any] | None) -> dict[str, Any]:
    """
    将 Confidence Engine 输出转为展示用（仅等级 + 一致/冲突标签，无百分比）。

    返回:
        {
            "confidence_level_cn": "中",
            "confidence_level_raw": "MEDIUM",
            "supporting": ["信号一致", "估值与趋势一致"],   # 支持置信
            "weakening": ["信号波动"],                     # 削弱置信
        }
    """
    if not confidence_result:
        return {
            "confidence_level_cn": "—",
            "confidence_level_raw": None,
            "supporting": [],
            "weakening": [],
        }
    level = confidence_result.get("confidence")
    reasons = confidence_result.get("confidence_reason") or []
    level_cn = CONFIDENCE_LEVEL_LABELS.get(str(level).upper() if level else "", "—")
    supporting = []
    weakening = []
    for r in reasons:
        label = REASON_LABELS.get(r, r)
        if r in REASONS_AGREEMENT:
            supporting.append(label)
        elif r in REASONS_CONFLICT:
            weakening.append(label)
    return {
        "confidence_level_cn": level_cn,
        "confidence_level_raw": level,
        "supporting": supporting,
        "weakening": weakening,
    }


def _badge_html(label: str, bg: str, fg: str) -> str:
    return (
        f'<span style="'
        f"display:inline-block;padding:0.2em 0.45em;border-radius:4px;"
        f"background-color:{bg};color:{fg};font-size:0.85em;font-weight:500;"
        f'">{label}</span>'
    )


def render_confidence_layer_cards(
    confidence_result: dict[str, Any] | None,
    title: str = "信号可信度",
) -> None:
    """
    在 Streamlit 中渲染 Confidence Layer：置信度等级 + 一致 vs 冲突。
    与决策/买卖方向无关；可存在「偏多但低置信」等组合。无百分比。
    """
    display = get_confidence_layer_display(confidence_result)
    if confidence_result is None or (isinstance(confidence_result, dict) and not confidence_result):
        st.caption("暂无置信度数据")
        return

    st.markdown(f"**{title}** · 当前信号有多值得信任？")
    level_cn = display["confidence_level_cn"]
    level_raw = display["confidence_level_raw"]
    supporting = display["supporting"]
    weakening = display["weakening"]

    bg, fg = _confidence_style(level_raw)
    st.markdown(
        f'<div style="margin-bottom:0.5em;"><small style="color:#757575;">置信度（与买卖方向无关）</small></div>'
        f'<div style="font-size:1.15em;">{_badge_html(level_cn, bg, fg)}</div>',
        unsafe_allow_html=True,
    )
    st.caption("可存在「偏多但低置信」或「偏空但高置信」，此处仅表示信号可靠性。")
    st.markdown("")

    # 一致 vs 冲突
    st.markdown("**一致 vs 冲突**")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("*支持置信*")
        if supporting:
            tags = [_badge_html(t, "#e8f5e9", "#2e7d32") for t in supporting]
            st.markdown('<div style="margin-top:0.2em;">' + " &nbsp; ".join(tags) + "</div>", unsafe_allow_html=True)
        else:
            st.caption("—")
    with col_b:
        st.markdown("*削弱置信*")
        if weakening:
            tags = [_badge_html(t, "#ffebee", "#c62828") for t in weakening]
            st.markdown('<div style="margin-top:0.2em;">' + " &nbsp; ".join(tags) + "</div>", unsafe_allow_html=True)
        else:
            st.caption("—")


def build_confidence_layer_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    从监控表构建 Confidence Layer 展示表。
    列：代码, 名称, 最新价, 涨跌幅, 置信度, 支持置信, 削弱置信
    """
    rows = []
    for _, row in df.iterrows():
        conf = row.get("confidence_result")
        if isinstance(conf, str):
            conf = {}
        display = get_confidence_layer_display(conf)
        support_text = "；".join(display["supporting"]) if display["supporting"] else "—"
        weaken_text = "；".join(display["weakening"]) if display["weakening"] else "—"
        rows.append({
            "代码": row.get("代码"),
            "名称": row.get("名称"),
            "最新价": row.get("最新价"),
            "涨跌幅": row.get("涨跌幅"),
            "置信度": display["confidence_level_cn"],
            "支持置信": support_text,
            "削弱置信": weaken_text,
            "_confidence_raw": display["confidence_level_raw"],
        })
    return pd.DataFrame(rows)


def style_confidence_layer_table(conf_df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """对置信度列按等级上色。"""
    if "置信度" not in conf_df.columns or "_confidence_raw" not in conf_df.columns:
        return conf_df.style

    def _level_style(series: pd.Series) -> list[str]:
        out = []
        for idx in series.index:
            raw = conf_df.loc[idx, "_confidence_raw"] if "_confidence_raw" in conf_df.columns else None
            bg, fg = _confidence_style(raw)
            out.append(f"background-color: {bg}; color: {fg}; font-weight: 600;")
        return out

    styled = conf_df.style.apply(_level_style, axis=0, subset=["置信度"])
    if "_confidence_raw" in styled.columns:
        styled = styled.hide(axis="columns", subset=["_confidence_raw"])
    return styled
