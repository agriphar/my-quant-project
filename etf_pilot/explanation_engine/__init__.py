# -*- coding: utf-8 -*-
"""说明与理由：根据决策结果生成展示文案（含结构化理由，无分数描述）。"""
from .reasons import get_reason_for_signal
from .structured_reasoning import (
    explain_decision,
    format_reasoning_readable,
    generate_reasoning,
)

__all__ = [
    "get_reason_for_signal",
    "generate_reasoning",
    "format_reasoning_readable",
    "explain_decision",
]
