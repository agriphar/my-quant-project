# -*- coding: utf-8 -*-
"""集中度风险：单一标的或前几大权重过高 → LOW/MEDIUM/HIGH。"""
from __future__ import annotations

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"

# 单一标的占组合权重阈值（%）
WEIGHT_PCT_MEDIUM = 15.0
WEIGHT_PCT_HIGH = 35.0


def concentration_risk_level(
    weight_pct: float | None = None,
    n_positions: int | None = None,
) -> str:
    """
    集中度风险：
    - weight_pct: 该标的占组合权重（%）。未提供时按 MEDIUM（未知假设单一或高集中）。
    - n_positions: 可选，组合持仓数；若仅 1 只则 concentration 至少 MEDIUM。
    - 权重 <= 15%: LOW；15% < 权重 <= 35%: MEDIUM；> 35%: HIGH。
    """
    if weight_pct is not None:
        try:
            w = float(weight_pct)
            if w <= WEIGHT_PCT_MEDIUM:
                return RISK_LOW
            if w <= WEIGHT_PCT_HIGH:
                return RISK_MEDIUM
            return RISK_HIGH
        except (TypeError, ValueError):
            pass
    if n_positions is not None and n_positions <= 1:
        return RISK_MEDIUM
    return RISK_MEDIUM
