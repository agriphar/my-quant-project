# -*- coding: utf-8 -*-
"""
⚠️ 已废弃：此模块已废弃，新代码应使用 decision_engine 的新架构。

兼容：加权评分与建议 re-export 自 decision_engine。
"""
import warnings

warnings.warn(
    "strategy.scoring is deprecated. Use decision_engine.make_decision() instead.",
    DeprecationWarning,
    stacklevel=2,
)

from decision_engine.compat import premium_deviation

# ⚠️ 以下函数已废弃，不再导出
# calculate_score, get_signal_from_score, PREMIUM_DEVIATION_HOT, 
# PREMIUM_DEVIATION_VETO, SCORE_STRONG_BUY, SCORE_HOLD

__all__ = [
    "premium_deviation",
]
