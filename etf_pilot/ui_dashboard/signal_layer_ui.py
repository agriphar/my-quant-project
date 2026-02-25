# -*- coding: utf-8 -*-
"""
Signal Layer UI — 仅展示 Signal Engine 的市场状态，无指标、无分数。

回答：「当前市场在做什么？」
展示：趋势、动量、估值、波动（状态标签 + 状态稳定性），使用徽章/颜色/图标。
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

# -----------------------------------------------------------------------------
# 状态 → 中文标签（仅标签，无数值）
# -----------------------------------------------------------------------------

TREND_LABELS = {
    "UP": "上行",
    "DOWN": "下行",
    "SIDEWAYS": "横盘",
    "UNKNOWN": "未知",
}

MOMENTUM_LABELS = {
    "ACCELERATING": "增强",
    "WEAKENING": "减弱",
    "NEUTRAL": "中性",
    "UNKNOWN": "未知",
}

VALUATION_LABELS = {
    "CHEAP": "便宜",
    "FAIR": "合理",
    "EXPENSIVE": "偏贵",
    "UNKNOWN": "未知",
}

VOLATILITY_LABELS = {
    "LOW": "低",
    "NORMAL": "正常",
    "HIGH": "高",
    "UNKNOWN": "未知",
}

STABILITY_LABELS = {
    "LOW": "稳定",
    "MEDIUM": "一般",
    "HIGH": "波动",
}

# -----------------------------------------------------------------------------
# 状态 → 徽章样式（背景色 + 文字色，语义化）
# -----------------------------------------------------------------------------

BADGE_STYLES = {
    # 趋势
    "UP": ("#e8f5e9", "#2e7d32"),           # 浅绿 / 深绿
    "DOWN": ("#ffebee", "#c62828"),          # 浅红 / 深红
    "SIDEWAYS": ("#f5f5f5", "#616161"),      # 浅灰 / 深灰
    # 动量
    "ACCELERATING": ("#e8f5e9", "#2e7d32"),
    "WEAKENING": ("#fff3e0", "#e65100"),     # 浅橙 / 深橙
    "NEUTRAL": ("#f5f5f5", "#616161"),
    # 估值
    "CHEAP": ("#e8f5e9", "#2e7d32"),
    "FAIR": ("#f5f5f5", "#616161"),
    "EXPENSIVE": ("#ffebee", "#c62828"),
    # 波动
    "LOW": ("#e8f5e9", "#2e7d32"),
    "NORMAL": ("#f5f5f5", "#616161"),
    "HIGH": ("#fff3e0", "#e65100"),
    # 稳定性（rapid_transitions 反义：LOW 风险 = 稳定）
    "STABILITY_LOW": ("#e8f5e9", "#2e7d32"),    # 稳定
    "STABILITY_MEDIUM": ("#fff8e1", "#f9a825"), # 一般
    "STABILITY_HIGH": ("#ffebee", "#c62828"),   # 波动
}
# 未知统一样式
UNKNOWN_STYLE = ("#eceff1", "#78909c")


def _state_label(state: str | None, labels: dict[str, str]) -> str:
    if not state:
        return "—"
    return labels.get(str(state).upper(), "—")


def _state_style(state: str | None, style_key: str | None = None) -> tuple[str, str]:
    """返回 (bg_color, text_color)。"""
    if not state:
        return UNKNOWN_STYLE
    key = str(state).upper()
    if key == "UNKNOWN":
        return UNKNOWN_STYLE
    if style_key == "stability":
        return BADGE_STYLES.get(f"STABILITY_{key}", UNKNOWN_STYLE)
    return BADGE_STYLES.get(key, UNKNOWN_STYLE)


def get_signal_layer_display(
    signal_states: dict[str, str] | None,
    state_stability: str | None,
) -> dict[str, str]:
    """
    将 Signal Engine 输出转为展示用中文标签（无任何数值）。

    返回:
        {"趋势": "上行", "动量": "中性", "估值": "合理", "波动": "正常", "状态稳定性": "稳定"}
    """
    if not signal_states:
        return {
            "趋势": "—",
            "动量": "—",
            "估值": "—",
            "波动": "—",
            "状态稳定性": "—",
        }
    trend = signal_states.get("trend")
    momentum = signal_states.get("momentum")
    valuation = signal_states.get("valuation")
    volatility = signal_states.get("volatility")
    return {
        "趋势": _state_label(trend, TREND_LABELS),
        "动量": _state_label(momentum, MOMENTUM_LABELS),
        "估值": _state_label(valuation, VALUATION_LABELS),
        "波动": _state_label(volatility, VOLATILITY_LABELS),
        "状态稳定性": _state_label(state_stability, STABILITY_LABELS) if state_stability else "—",
    }


def _badge_html(label: str, bg: str, fg: str, title: str = "") -> str:
    title_attr = f' title="{title}"' if title else ""
    return (
        f'<span style="'
        f"display:inline-block;padding:0.2em 0.5em;border-radius:4px;"
        f"background-color:{bg};color:{fg};font-size:0.9em;font-weight:500;"
        f'"{title_attr}>{label}</span>'
    )


def render_signal_layer_cards(
    signal_states: dict[str, str] | None,
    state_stability: str | None,
    title: str = "市场状态",
) -> None:
    """
    在 Streamlit 中渲染 Signal Layer：四个状态 + 稳定性，使用视觉徽章。
    不展示任何数值指标。
    """
    display = get_signal_layer_display(signal_states, state_stability)
    if not signal_states:
        st.caption("暂无状态数据")
        return

    st.markdown(f"**{title}** · 当前市场在做什么？")
    cols = st.columns(5)
    factors = [
        ("趋势", "trend", display["趋势"]),
        ("动量", "momentum", display["动量"]),
        ("估值", "valuation", display["估值"]),
        ("波动", "volatility", display["波动"]),
        ("状态稳定性", "stability", display["状态稳定性"]),
    ]
    for i, (name, key, label) in enumerate(factors):
        with cols[i]:
            if key == "stability":
                raw = state_stability
                bg, fg = _state_style(raw, "stability")
            else:
                raw = (signal_states or {}).get(key)
                bg, fg = _state_style(raw)
            st.markdown(
                f'<div style="margin-bottom:0.3em;"><small style="color:#757575;">{name}</small></div>'
                f'{_badge_html(label or "—", bg, fg, raw or "")}',
                unsafe_allow_html=True,
            )


def build_signal_layer_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    从监控表构建仅含 Signal Layer 展示列的 DataFrame（无 RSI/MA/分数）。
    列：代码, 名称, 最新价, 涨跌幅, 趋势, 动量, 估值, 波动, 状态稳定性
    """
    rows = []
    for _, row in df.iterrows():
        signal_states = row.get("signal_states")
        if isinstance(signal_states, str):
            signal_states = {}
        state_stability = row.get("state_stability")
        display = get_signal_layer_display(signal_states, state_stability)
        rows.append({
            "代码": row.get("代码"),
            "名称": row.get("名称"),
            "最新价": row.get("最新价"),
            "涨跌幅": row.get("涨跌幅"),
            "趋势": display["趋势"],
            "动量": display["动量"],
            "估值": display["估值"],
            "波动": display["波动"],
            "状态稳定性": display["状态稳定性"],
            "_trend_raw": (signal_states or {}).get("trend"),
            "_momentum_raw": (signal_states or {}).get("momentum"),
            "_valuation_raw": (signal_states or {}).get("valuation"),
            "_volatility_raw": (signal_states or {}).get("volatility"),
            "_stability_raw": state_stability,
        })
    out = pd.DataFrame(rows)
    return out


def style_signal_layer_table(signal_df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """
    对 Signal Layer 表格的状态列应用背景色（按状态语义）。
    """
    state_cols = ["趋势", "动量", "估值", "波动", "状态稳定性"]
    raw_cols = ["_trend_raw", "_momentum_raw", "_valuation_raw", "_volatility_raw", "_stability_raw"]

    def _cell_style(series: pd.Series, raw_col: str, is_stability: bool) -> list[str]:
        styles = []
        for idx in series.index:
            raw = signal_df.loc[idx, raw_col] if raw_col in signal_df.columns else None
            if pd.isna(raw) or raw is None or str(raw).upper() == "UNKNOWN":
                styles.append("background-color: #eceff1; color: #78909c;")
            else:
                key = str(raw).upper()
                if is_stability:
                    bg, fg = _state_style(key, "stability")
                else:
                    bg, fg = _state_style(key)
                styles.append(f"background-color: {bg}; color: {fg}; font-weight: 500;")
        return styles

    styled = signal_df.style
    for col, raw_col in zip(state_cols, raw_cols):
        if col not in signal_df.columns or raw_col not in signal_df.columns:
            continue
        styled = styled.apply(
            lambda s, rc=raw_col, st=(col == "状态稳定性"): _cell_style(s, rc, st),
            axis=0,
            subset=[col],
        )
    # 隐藏原始状态列（仅供样式使用）
    to_hide = [c for c in raw_cols if c in styled.columns]
    if to_hide:
        styled = styled.hide(axis="columns", subset=to_hide)
    return styled
