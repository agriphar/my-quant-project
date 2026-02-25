# -*- coding: utf-8 -*-
"""每日操作建议、建议操作频率、信号准确率 30d。"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from market_regime.trend import linear_regression_r2_slope, REGRESSION_WINDOW
from signal_engine.states import get_signal_states
from risk_engine import evaluate_risk
from .compat import decision_to_legacy_format, compute_daily_action_compat

SIGNAL_LOOKBACK_DAYS = 30
SIGNAL_FWD_DAYS = 5
ACCURACY_LOOKBACK_DAYS = 60
PREMIUM_AVG_DAYS = 22
PREMIUM_PCTILE_DAYS = 60
MIN_ACCURACY_SAMPLE = 1


def _percentileofscore(arr, score: float) -> float:
    """0~100，表示 score 在 arr 中的百分位。"""
    if arr is None or len(arr) == 0:
        return np.nan
    arr = np.asarray(arr, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return np.nan
    return float(np.sum(arr <= score) / len(arr) * 100)


def _hist_daily_premium_merged(hist: pd.DataFrame, nav_hist: pd.DataFrame | None) -> pd.DataFrame | None:
    """
    将日线 hist 与净值 nav_hist 按日期合并，得到每日的场内价与溢价率。
    用于回溯时逐日使用「技术指标 + 溢价水位」重算建议。
    """
    if hist is None or hist.empty or "收盘" not in hist.columns:
        return None
    hist = hist.copy()
    hist["日期"] = pd.to_datetime(hist["日期"]).dt.normalize()
    if nav_hist is None or nav_hist.empty or "单位净值" not in nav_hist.columns:
        return hist.assign(溢价率=np.nan)
    nav = nav_hist.copy()
    nav["日期"] = pd.to_datetime(nav["日期"]).dt.normalize()
    merged = hist.merge(nav[["日期", "单位净值"]], on="日期", how="left")
    merged["单位净值"] = merged["单位净值"].replace(0, np.nan)
    merged["溢价率"] = np.nan
    valid = merged["单位净值"].notna() & (merged["单位净值"] > 0)
    merged.loc[valid, "溢价率"] = (
        (merged.loc[valid, "收盘"].astype(float) - merged.loc[valid, "单位净值"].astype(float))
        / merged.loc[valid, "单位净值"].astype(float) * 100
    )
    return merged


def compute_daily_action(
    last: pd.Series,
    premium_pct: float | None = None,
    avg_premium_22d: float | None = None,
    premium_std_22d: float | None = None,
    premium_pctile_60: float | None = None,
    r2: float | None = None,
    slope: float | None = None,
    atr_pct: float | None = None,
    market_regime: dict | None = None,
    pct_drawdown_from_high: float | None = None,
    weight_pct: float | None = None,
) -> tuple:
    """
    ⚠️ 已废弃：此函数使用旧的架构，新代码应使用 compute_daily_action_v2()。

    每日操作建议：Signal Engine 出状态 → Risk Engine 评估风险等级 → Decision Engine 组合状态+风险+regime → 建议。
    Decision Engine 依赖 Risk Engine：风险等级 HIGH 时提高强烈补仓/持有门槛。
    返回 (action, reason, display_label, confidence_band, conflicting_signals, total_score)。
    """
    import warnings
    warnings.warn(
        "compute_daily_action() is deprecated. "
        "Use compute_daily_action_v2() instead, which uses the new architecture.",
        DeprecationWarning,
        stacklevel=2,
    )
    if last.get("收盘") is None or pd.isna(last.get("收盘")):
        return "持有观望", "数据不足", "观望", "low", False, 0.0
    signal_states = get_signal_states(
        last,
        r2=r2,
        slope=slope,
        premium_pctile_60=premium_pctile_60,
        atr_pct=atr_pct,
    )
    # ⚠️ 旧接口：直接传递原始数据给 Risk Engine（违反架构原则）
    # 新代码应使用：risk_result = evaluate_risk(signal_states=signal_states, history=history)
    # 注意：旧的 evaluate_risk 可能接受这些参数，但新架构中不再接受
    try:
        # 尝试使用新接口（只传递 signal_states）
        risk_result = evaluate_risk(
            signal_states=signal_states,
            history=None,
            lookback_days=5,
        )
    except TypeError:
        # 如果新接口不可用，尝试旧接口（向后兼容）
        risk_result = evaluate_risk(
            atr_pct=atr_pct,  # ❌ 违反架构原则：传递原始数据
            pct_drawdown_from_high=pct_drawdown_from_high,
            signal_states=signal_states,
            weight_pct=weight_pct,
        )
    # ✅ 使用新架构（通过适配器保持向后兼容）
    decision = compute_daily_action_v2(
        last=last,
        premium_pctile_60=premium_pctile_60,
        r2=r2,
        slope=slope,
        atr_pct=atr_pct,
        market_regime=market_regime,
        history=None,
    )
    # 转换为旧格式
    return decision_to_legacy_format(decision)


def compute_daily_action_v2(
    last: pd.Series,
    premium_pctile_60: float | None = None,
    r2: float | None = None,
    slope: float | None = None,
    atr_pct: float | None = None,
    market_regime: dict | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    每日操作建议（新架构）：使用新的三层决策逻辑。

    参数:
    - last: 最后一行数据（Series 或 dict），用于提取 RSI 和 ATR
    - premium_pctile_60: 溢价率 60 日分位数（可选）
    - r2: 线性回归的 R² 值（可选）
    - slope: 线性回归的斜率（可选）
    - atr_pct: ATR 百分比（可选，如果未提供则从 last 计算）
    - market_regime: 市场制度字典（可选）
    - history: Signal Engine 的历史状态序列（可选，用于 Risk Engine 和 Confidence Engine）

    返回:
    {
        "action": "INCREASE" | "HOLD" | "REDUCE" | "WAIT",
        "aggressiveness": "LOW" | "MEDIUM" | "HIGH",
        "reason_tags": [...],
        "signal_states": {...},
        "risk_result": {...},
        "confidence_result": {...}
    }
    """
    from decision_engine.decision import make_decision
    from confidence_engine import calculate_confidence

    if last.get("收盘") is None or pd.isna(last.get("收盘")):
        return {
            "action": "WAIT",
            "aggressiveness": "LOW",
            "reason_tags": ["uncertain_signals"],
            "signal_states": {},
            "risk_result": {},
            "confidence_result": {},
        }

    # 1. Signal Engine
    signal_states = get_signal_states(
        last,
        r2=r2,
        slope=slope,
        premium_pctile_60=premium_pctile_60,
        atr_pct=atr_pct,
    )

    # 2. Risk Engine（只使用 Signal Engine 的输出）
    risk_result = evaluate_risk(
        signal_states=signal_states,
        history=history,
        lookback_days=5,
    )

    # 3. Confidence Engine（使用 Signal Engine 和 Risk Engine 的输出）
    confidence_result = calculate_confidence(
        signal_states=signal_states,
        risk_result=risk_result,
        market_regime=market_regime,
        history=history,
        lookback_days=5,
    )

    # 4. Decision Engine（使用所有前序层的输出）
    decision = make_decision(
        signal_states=signal_states,
        risk_result=risk_result,
        confidence_result=confidence_result,
    )

    return {
        **decision,
        "signal_states": signal_states,
        "risk_result": risk_result,
        "confidence_result": confidence_result,
    }


def compute_action_frequency(hist: pd.DataFrame, days: int = SIGNAL_LOOKBACK_DAYS) -> int:
    """过去 N 天内「强烈建议补仓」或「考虑套利/减仓」出现次数，用于排序（建议操作频率）。"""
    if hist is None or len(hist) < 2 or "收盘" not in hist.columns:
        return 0
    need = ["收盘", "MA60", "RSI", "BB_upper"]
    if not all(c in hist.columns for c in need):
        return 0
    tail = hist.tail(days)
    count = 0
    for _, row in tail.iterrows():
        # ✅ 使用新架构
        decision = compute_daily_action_v2(
            last=row,
            premium_pctile_60=None,  # 简化：不计算溢价分位
            r2=None,  # 简化：不计算趋势
            slope=None,
            atr_pct=None,
            market_regime=None,
            history=None,
        )
        act = decision.get("action", "HOLD")
        # 转换为旧格式的动作名称
        action_map = {
            "INCREASE": "强烈建议补仓",
            "REDUCE": "考虑套利/减仓",
            "HOLD": "持有观望",
            "WAIT": "等待",
        }
        act_cn = action_map.get(act, "持有观望")
        if act_cn in ("强烈建议补仓", "考虑套利/减仓"):
            count += 1
    return count


def compute_signal_accuracy_30d(
    hist: pd.DataFrame,
    nav_hist: pd.DataFrame | None = None,
) -> dict:
    """
    近期信号准确率（仅统计补仓/减仓，且信号须已跑满 5 日）：
    回溯窗口 ACCURACY_LOOKBACK_DAYS，按日计算 r2/slope 及 bias，再调用 compute_daily_action。
    返回 {"信号准确率30d": float|None, "实战建议次数": int, "信号准确率显示": str}。
    """
    out = {"信号准确率30d": None, "实战建议次数": 0, "信号准确率显示": "—"}
    min_bars = REGRESSION_WINDOW + SIGNAL_FWD_DAYS
    if hist is None or len(hist) < min_bars:
        return out
    need = ["收盘", "MA60", "RSI", "BB_upper"]
    if not all(c in hist.columns for c in need):
        return out
    merged = _hist_daily_premium_merged(hist, nav_hist)
    if merged is None:
        return out
    merged = merged.sort_values("日期").reset_index(drop=True)
    close = merged["收盘"].astype(float)
    end_i = len(merged) - SIGNAL_FWD_DAYS
    start_i = max(REGRESSION_WINDOW - 1, len(merged) - ACCURACY_LOOKBACK_DAYS)
    if start_i < 0 or start_i >= end_i:
        return out
    correct = 0
    total = 0
    for i in range(start_i, end_i):
        if i + SIGNAL_FWD_DAYS >= len(merged):
            break
        row_i = merged.iloc[i]
        p0 = close.iloc[i]
        p5 = close.iloc[i + SIGNAL_FWD_DAYS]
        if p0 is None or p0 <= 0 or pd.isna(p0) or pd.isna(p5):
            continue
        ret5 = (float(p5) - float(p0)) / float(p0)
        hist_slice = merged.iloc[: i + 1]
        if len(hist_slice) >= REGRESSION_WINDOW:
            r2_i, slope_i = linear_regression_r2_slope(hist_slice["收盘"], REGRESSION_WINDOW)
        else:
            r2_i, slope_i = None, None
        atr_pct_i = None
        if "ATR" in merged.columns and row_i.get("收盘") and row_i.get("ATR") is not None:
            try:
                c = float(row_i["收盘"])
                if c > 0:
                    atr_pct_i = float(row_i["ATR"]) / c * 100
            except (TypeError, ValueError):
                pass
        premium_i = row_i.get("溢价率")
        if pd.isna(premium_i) or premium_i is None:
            avg_22_i = None
            pct_60_i = None
            std_22_i = None
        else:
            sub = merged.loc[merged["日期"] <= row_i["日期"], "溢价率"].dropna().tail(PREMIUM_PCTILE_DAYS)
            if len(sub) < 5:
                avg_22_i = None
                pct_60_i = None
                std_22_i = None
            else:
                tail22 = sub.tail(PREMIUM_AVG_DAYS)
                avg_22_i = float(tail22.mean())
                std_22_i = float(tail22.std()) if len(tail22) > 1 and tail22.std() and not pd.isna(tail22.std()) else None
                pct_60_i = _percentileofscore(sub.values, float(premium_i))
        # ✅ 使用新架构
        decision = compute_daily_action_v2(
            last=row_i,
            premium_pctile_60=pct_60_i,
            r2=r2_i,
            slope=slope_i,
            atr_pct=atr_pct_i,
            market_regime=None,
            history=None,
        )
        action_new = decision.get("action", "HOLD")
        # 转换为旧格式的动作名称
        action_map = {
            "INCREASE": "强烈建议补仓",
            "REDUCE": "考虑套利/减仓",
            "HOLD": "持有观望",
            "WAIT": "等待",
        }
        action = action_map.get(action_new, "持有观望")
        if action in ("持有观望", "极度过热，禁买"):
            continue
        if action == "强烈建议补仓":
            total += 1
            if ret5 > 0:
                correct += 1
            continue
        if action == "考虑套利/减仓":
            total += 1
            if ret5 < 0:
                correct += 1
            continue
    out["实战建议次数"] = total
    if total == 0:
        out["信号准确率显示"] = "近期无动作"
        return out
    if total < MIN_ACCURACY_SAMPLE:
        out["信号准确率显示"] = f"样本不足({total})"
        return out
    pct = round(correct / total * 100, 1)
    out["信号准确率30d"] = pct
    out["信号准确率显示"] = f"{correct}/{total} ({pct}%)"
    return out
