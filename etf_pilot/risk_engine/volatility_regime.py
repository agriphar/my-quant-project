# -*- coding: utf-8 -*-
"""波动率状态风险：基于 ATR% 或实现波动率，输出 LOW/MEDIUM/HIGH。"""
from __future__ import annotations

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"

# ATR% 阈值：高于上限为高波动状态
ATR_PCT_MEDIUM = 1.5
ATR_PCT_HIGH = 3.0


def volatility_risk_level(atr_pct: float | None) -> str:
    """
    波动率状态风险：ATR% 越高，风险越高。
    - ATR% <= 1.5: LOW
    - 1.5 < ATR% <= 3: MEDIUM
    - ATR% > 3: HIGH
    """
    if atr_pct is None:
        return RISK_MEDIUM
    try:
        a = float(atr_pct)
        if a <= ATR_PCT_MEDIUM:
            return RISK_LOW
        if a <= ATR_PCT_HIGH:
            return RISK_MEDIUM
        return RISK_HIGH
    except (TypeError, ValueError):
        return RISK_MEDIUM
