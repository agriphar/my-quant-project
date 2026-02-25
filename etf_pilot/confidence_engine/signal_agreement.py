# -*- coding: utf-8 -*-
"""
信号一致性水平评估：基于 Risk Engine 的信号分歧输出评估信号一致性。

只能使用 Risk Engine 的输出，禁止重新计算信号分歧。
"""
from __future__ import annotations

CONFIDENCE_LOW = "LOW"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_HIGH = "HIGH"

# Risk Engine 的风险等级常量
RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"


def signal_agreement_confidence(signal_disagreement_risk: str | None) -> str:
    """
    基于 Risk Engine 的信号分歧风险评估信号一致性置信度。

    参数:
    - signal_disagreement_risk: Risk Engine 输出的信号分歧风险等级
        "LOW" | "MEDIUM" | "HIGH"

    返回:
    - "HIGH": 高一致性（信号分歧风险为 LOW，3-4 个信号一致）
    - "MEDIUM": 中等一致性（信号分歧风险为 MEDIUM，部分分歧）
    - "LOW": 低一致性（信号分歧风险为 HIGH，严重分歧）

    逻辑:
    - 低分歧（高一致性）→ 高置信度
    - 中等分歧 → 中等置信度
    - 高分歧（低一致性）→ 低置信度
    """
    if not signal_disagreement_risk:
        return CONFIDENCE_MEDIUM

    signal_disagreement_risk = signal_disagreement_risk.upper()

    if signal_disagreement_risk == RISK_LOW:
        # 低分歧，高一致性，高置信度
        return CONFIDENCE_HIGH
    elif signal_disagreement_risk == RISK_HIGH:
        # 高分歧，低一致性，低置信度
        return CONFIDENCE_LOW
    else:
        # 中等分歧，中等一致性，中等置信度
        return CONFIDENCE_MEDIUM
