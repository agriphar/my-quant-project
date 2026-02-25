# -*- coding: utf-8 -*-
"""
制度稳定性评估：基于市场制度信息评估制度稳定性。

只能使用外部输入的市场制度信息，禁止使用价格数据或技术指标。
"""
from __future__ import annotations

from typing import Any

CONFIDENCE_LOW = "LOW"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_HIGH = "HIGH"


def regime_stability_confidence(market_regime: dict[str, Any] | None = None) -> str:
    """
    基于市场制度信息评估制度稳定性置信度。

    参数:
    - market_regime: 市场制度字典（可选）
        - market_regime.get("confidence") - 制度置信度（"high" | "medium" | "low"）
        - market_regime.get("risk_regime") - 风险制度（"risk_on" | "risk_off"）

    返回:
    - "HIGH": 制度稳定（制度明确且稳定）
    - "MEDIUM": 制度中等稳定（制度部分明确）
    - "LOW": 制度不稳定（制度不明确或频繁变化）

    逻辑:
    - 如果 market_regime 包含 "confidence" 字段，直接使用
    - 如果 market_regime 包含 "risk_regime" 字段，评估其稳定性
    - 如果没有 market_regime 信息，视为中等稳定性
    """
    if not market_regime:
        # 没有市场制度信息，视为中等稳定性
        return CONFIDENCE_MEDIUM

    # 优先使用 confidence 字段
    confidence_str = market_regime.get("confidence")
    if confidence_str:
        confidence_str = str(confidence_str).lower()
        if confidence_str == "high":
            return CONFIDENCE_HIGH
        elif confidence_str == "medium":
            return CONFIDENCE_MEDIUM
        else:
            return CONFIDENCE_LOW

    # 如果没有 confidence 字段，使用 risk_regime 字段
    risk_regime = market_regime.get("risk_regime")
    if risk_regime:
        risk_regime = str(risk_regime).lower()
        # risk_on 和 risk_off 都视为中等稳定性（制度明确但可能变化）
        if risk_regime in ("risk_on", "risk_off"):
            return CONFIDENCE_MEDIUM

    # 没有可用的制度信息，视为中等稳定性
    return CONFIDENCE_MEDIUM
