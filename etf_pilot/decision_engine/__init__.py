# -*- coding: utf-8 -*-
"""Decision Engine：组合信号状态 + 市场状态 + 风险 → 买卖建议。"""
from .scoring import (
    premium_deviation,
    calculate_score,
    state_to_score,
    get_advice,
    get_signal_from_score,
    PREMIUM_DEVIATION_VETO,
    SCORE_STRONG_BUY,
    SCORE_HOLD,
)
from .daily_action import (
    compute_daily_action,
    compute_action_frequency,
    compute_signal_accuracy_30d,
)

__all__ = [
    "premium_deviation",
    "calculate_score",
    "state_to_score",
    "get_advice",
    "get_signal_from_score",
    "PREMIUM_DEVIATION_VETO",
    "SCORE_STRONG_BUY",
    "SCORE_HOLD",
    "compute_daily_action",
    "compute_action_frequency",
    "compute_signal_accuracy_30d",
]
