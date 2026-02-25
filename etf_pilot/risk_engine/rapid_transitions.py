# -*- coding: utf-8 -*-
"""
快速状态转换风险：评估信号状态的快速变化。

只能使用 Signal Engine 的历史输出，禁止使用原始数据。
"""
from __future__ import annotations

from typing import Sequence

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"

# 默认历史窗口（天数）
DEFAULT_LOOKBACK_DAYS = 5

# 状态变化阈值
CHANGES_LOW_THRESHOLD = 1  # 变化次数 <= 1 视为低风险
CHANGES_MEDIUM_THRESHOLD = 3  # 变化次数 2-3 视为中等风险
# 变化次数 >= 4 视为高风险


def _count_state_changes(
    history: Sequence[dict[str, str]],
    factor: str,
) -> int:
    """
    统计某个信号因子在历史序列中的状态变化次数。

    参数:
    - history: Signal Engine 的历史输出序列（按时间顺序，最新的在最后）
    - factor: 信号因子名称（"trend", "momentum", "valuation", "volatility"）

    返回:
    - 状态变化次数（0 表示无变化）
    """
    if not history or len(history) < 2:
        return 0

    changes = 0
    prev_state = None

    for signal_states in history:
        if not signal_states:
            continue

        current_state = signal_states.get(factor)
        if current_state is None:
            continue

        if prev_state is not None and current_state != prev_state:
            changes += 1

        prev_state = current_state

    return changes


def rapid_transitions_risk(
    current_states: dict[str, str] | None,
    history: Sequence[dict[str, str]] | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> str:
    """
    快速状态转换风险：评估信号状态的快速变化。

    参数:
    - current_states: Signal Engine 的当前状态字典
    - history: Signal Engine 的历史状态序列（按时间顺序，最新的在最后）
        如果为 None，则无法评估，返回 MEDIUM
    - lookback_days: 历史窗口天数（默认 5 天）

    返回:
    - "LOW": 状态稳定（过去 N 天内任一信号变化次数 <= 1）
    - "MEDIUM": 状态不稳定（过去 N 天内任一信号变化次数 2-3）
    - "HIGH": 状态极不稳定（过去 N 天内任一信号变化次数 >= 4）

    逻辑:
    - 统计每个信号因子（trend, momentum, valuation, volatility）的状态变化次数
    - 取所有信号因子中变化次数的最大值
    - 如果任一信号状态频繁变化，风险升高
    """
    if not history or len(history) < 2:
        # 历史数据不足，无法评估，返回中等风险
        return RISK_MEDIUM

    # 限制历史窗口
    if len(history) > lookback_days:
        history = list(history[-lookback_days:])

    # 如果提供了当前状态，将其加入历史序列
    if current_states:
        history = list(history) + [current_states]

    # 统计每个信号因子的状态变化次数
    max_changes = 0
    for factor in ("trend", "momentum", "valuation", "volatility"):
        changes = _count_state_changes(history, factor)
        max_changes = max(max_changes, changes)

    # 根据最大变化次数评估风险
    if max_changes <= CHANGES_LOW_THRESHOLD:
        return RISK_LOW
    elif max_changes <= CHANGES_MEDIUM_THRESHOLD:
        return RISK_MEDIUM
    else:
        return RISK_HIGH
