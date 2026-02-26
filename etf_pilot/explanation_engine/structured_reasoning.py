# -*- coding: utf-8 -*-
"""
Explanation Engine — 根据 regime、signals、risk level、final decision 生成结构化理由。

仅用自然语言描述「为什么」，不涉及分数或加权计算。
"""
from __future__ import annotations

from typing import Any

# 信号状态 → 中文描述（仅状态含义，非建议）
MOMENTUM_LABELS = {
    "oversold": "动量偏超卖，价格近期回调较多",
    "neutral": "动量中性，未明显超买或超卖",
    "overbought": "动量偏超买，短期涨幅较大",
}

TREND_LABELS = {
    "strong_up": "趋势明确向上，走势连贯",
    "weak_up": "趋势偏多但力度一般",
    "down": "趋势偏弱或向下",
    "unknown": "趋势方向不明确",
}

VALUATION_LABELS = {
    "cheap": "溢价处于近期偏低水平",
    "fair_low": "溢价处于近期中偏低",
    "fair_high": "溢价处于近期中偏高",
    "expensive": "溢价处于近期偏高",
    "unknown": "溢价水平难以判断",
}

VOLATILITY_LABELS = {
    "low": "波动较低，走势相对平稳",
    "medium": "波动适中",
    "high": "波动较大，不确定性高",
    "unknown": "波动情况不明",
}

RISK_LABELS = {
    "LOW": "综合风险较低",
    "MEDIUM": "综合风险中等",
    "HIGH": "综合风险较高",
}

REGIME_RISK_LABELS = {
    "risk_on": "市场风险偏好偏积极",
    "risk_off": "市场风险偏好偏谨慎",
    "unknown": "",
}

REGIME_LIQUIDITY_LABELS = {
    "tightening": "流动性偏紧",
    "easing": "流动性偏松",
    "neutral": "",
    "unknown": "",
}

REGIME_USD_LABELS = {
    "strength": "美元偏强",
    "weakness": "美元偏弱",
    "neutral": "",
    "unknown": "",
}


def _describe_signal_states(signal_states: dict[str, str] | None) -> list[str]:
    """将信号状态转为可读短句，不涉及分数。"""
    if not signal_states:
        return ["暂无信号解读"]
    lines = []
    m = signal_states.get("momentum")
    if m and m in MOMENTUM_LABELS:
        lines.append("· " + MOMENTUM_LABELS[m])
    t = signal_states.get("trend")
    if t and t in TREND_LABELS:
        lines.append("· " + TREND_LABELS[t])
    v = signal_states.get("valuation")
    if v and v in VALUATION_LABELS:
        lines.append("· " + VALUATION_LABELS[v])
    vol = signal_states.get("volatility")
    if vol and vol in VOLATILITY_LABELS:
        lines.append("· " + VOLATILITY_LABELS[vol])
    return lines if lines else ["· 信号信息不足"]


def _describe_regime(regime: dict[str, str] | None) -> list[str]:
    """将市场状态转为可读短句。"""
    if not regime:
        return []
    lines = []
    r = regime.get("risk_regime")
    if r and r in REGIME_RISK_LABELS and REGIME_RISK_LABELS[r]:
        lines.append("· " + REGIME_RISK_LABELS[r])
    liq = regime.get("liquidity")
    if liq and liq in REGIME_LIQUIDITY_LABELS and REGIME_LIQUIDITY_LABELS[liq]:
        lines.append("· " + REGIME_LIQUIDITY_LABELS[liq])
    usd = regime.get("usd_trend")
    if usd and usd in REGIME_USD_LABELS and REGIME_USD_LABELS[usd]:
        lines.append("· " + REGIME_USD_LABELS[usd])
    return lines


def _describe_risk(risk_level: str | None) -> str:
    """风险等级的可读描述。"""
    if not risk_level:
        return "风险等级未评估"
    return RISK_LABELS.get(risk_level, risk_level)


def _why_this_decision(
    decision: str,
    premium_deviation_val: float | None = None,
    total_score: float | None = None,
    score_result: dict[str, float] | None = None,
) -> str:
    """用自然语言说明「为什么是这个结论」，不写分数。"""
    # 检查溢价偏离警告
    premium_warning = ""
    if premium_deviation_val is not None:
        z_score = float(premium_deviation_val)
        if z_score > 2.5:
            premium_warning = f"触发溢价极端过热警告 (z-score: {z_score:.2f})，"
        elif z_score > 1.5:
            premium_warning = f"触发溢价偏离警告 (z-score: {z_score:.2f})，"
    
    if decision == "强烈建议补仓":
        if premium_warning:
            return f"{premium_warning}但技术指标走强，综合判断适合逢低补仓。"
        return "动量、趋势、溢价与波动多方面偏有利，风险可控，综合判断适合逢低补仓。"
    if decision == "维持观望/持有":
        if premium_warning:
            return f"{premium_warning}当前处于震荡区间，建议维持现状、观望为主。"
        return "信号与风险组合未形成明确加仓或减仓条件，建议维持现状、观望为主。"
    if decision == "建议套利/减仓":
        if premium_warning:
            if score_result and score_result.get("valuation", 0) < -2:
                return f"{premium_warning}因溢价极端过热导致总分降至{total_score:.1f}，建议立即执行套利操作。"
            return f"{premium_warning}总分降至{total_score:.1f}，建议考虑兑现部分仓位或等待更好机会。"
        if score_result and score_result.get("valuation", 0) < -2:
            return f"因溢价极端过热（{score_result.get('valuation', 0):.1f}分惩罚），总分降至{total_score:.1f}，建议立即执行套利操作。"
        return "趋势或溢价偏不利，或风险等级较高，建议考虑兑现部分仓位或等待更好机会。"
    return ""


def generate_reasoning(
    regime: dict[str, str] | None,
    signal_states: dict[str, str] | None,
    risk_level: str | None,
    decision: str,
    premium_deviation_val: float | None = None,
    total_score: float | None = None,
    score_result: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    根据 regime、signals、risk level、final decision 生成结构化理由。

    返回结构：
    - summary: 一句话结论（为何是这个建议）
    - signals: 信号解读列表（可读短句）
    - risk_and_regime: 风险与市场状态描述
    - conclusion: 综合原因（为何得出该决策）
    """
    signals = _describe_signal_states(signal_states)
    regime_lines = _describe_regime(regime)
    risk_desc = _describe_risk(risk_level)
    conclusion = _why_this_decision(decision, premium_deviation_val, total_score, score_result)

    risk_and_regime = [risk_desc]
    risk_and_regime.extend(regime_lines)
    risk_and_regime = [x for x in risk_and_regime if x]

    return {
        "summary": conclusion,
        "signals": signals,
        "risk_and_regime": risk_and_regime,
        "conclusion": conclusion,
    }


def format_reasoning_readable(reasoning: dict[str, Any]) -> str:
    """
    将 generate_reasoning 的返回转为一段可读文字（适合界面展示）。
    不包含任何分数或加权说明。
    """
    parts = []
    if reasoning.get("conclusion"):
        parts.append(reasoning["conclusion"])
    signals = reasoning.get("signals") or []
    if signals:
        parts.append("信号方面：" + "；".join(s.replace("· ", "") for s in signals) + "。")
    risk_regime = reasoning.get("risk_and_regime") or []
    if risk_regime:
        parts.append("风险与环境：" + "；".join(risk_regime) + "。")
    return " ".join(parts) if parts else ""


def explain_decision(
    regime: dict[str, str] | None,
    signal_states: dict[str, str] | None,
    risk_level: str | None,
    decision: str,
    premium_deviation_val: float | None = None,
    total_score: float | None = None,
    score_result: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    统一入口：生成结构化理由，并附带可直接展示的短句与长文。

    返回：
    - one_liner: 简短一句（用于表格「建议理由」列）
    - structured: generate_reasoning 的完整结构
    - readable: 一段可读说明（用于详情/展开）
    """
    structured = generate_reasoning(
        regime=regime,
        signal_states=signal_states,
        risk_level=risk_level,
        decision=decision,
        premium_deviation_val=premium_deviation_val,
        total_score=total_score,
        score_result=score_result,
    )
    one_liner = structured["conclusion"] or "—"
    readable = format_reasoning_readable(structured)
    return {
        "one_liner": one_liner,
        "structured": structured,
        "readable": readable or one_liner,
    }
