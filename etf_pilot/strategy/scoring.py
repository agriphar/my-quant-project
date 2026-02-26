# -*- coding: utf-8 -*-
"""兼容：加权评分与建议 re-export 自 decision_engine。"""
from decision_engine.scoring import (
    premium_deviation,
    calculate_score,
    get_signal_from_score,
    PREMIUM_DEVIATION_HOT,
    PREMIUM_DEVIATION_EXTREME,
    PREMIUM_DEVIATION_VETO,  # 向后兼容别名
    SCORE_STRONG_BUY,
    SCORE_HOLD,
)

__all__ = [
    "premium_deviation",
    "calculate_score",
    "get_signal_from_score",
    "PREMIUM_DEVIATION_HOT",
    "PREMIUM_DEVIATION_EXTREME",
    "PREMIUM_DEVIATION_VETO",  # 向后兼容别名
    "SCORE_STRONG_BUY",
    "SCORE_HOLD",
]
