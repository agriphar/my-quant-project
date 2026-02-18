# -*- coding: utf-8 -*-
"""跨资产等权动态再平衡策略回测：5 只标的各 20%，偏离超阈值则再平衡。"""
import pandas as pd
import numpy as np
from typing import List, Tuple

from config.settings import (
    EW_INITIAL_CASH,
    EW_FEE_RATE,
    EW_MIN_FEE,
    EW_TARGET_WEIGHT,
    EW_DEVIATION_THRESHOLD,
    EW_REBALANCE_TRADING_DAYS,
)

TRADING_DAYS = 252
RISK_FREE_RATE = 0.02


def run_equal_weight_backtest(
    panel: pd.DataFrame,
    initial_cash: float = EW_INITIAL_CASH,
    fee_rate: float = EW_FEE_RATE,
    min_fee: float = EW_MIN_FEE,
    target_weight: float = EW_TARGET_WEIGHT,
    deviation_threshold: float = EW_DEVIATION_THRESHOLD,
    rebalance_interval_days: int = EW_REBALANCE_TRADING_DAYS,
) -> Tuple[pd.DataFrame, dict, List[pd.Timestamp]]:
    """
    五只标的等权：初始各 20%；每 rebalance_interval_days 个交易日检查一次，
    若任一只权重偏离 target_weight 超过 deviation_threshold（正负 3%），则再平衡至 20%。
    基准：五只简单平均、不调仓的净值（买入持有等权）。
    返回 (daily_df, metrics, rebalance_dates)。
    """
    if panel is None or panel.empty:
        return pd.DataFrame(), {}, []
    panel = panel.copy()
    panel["日期"] = pd.to_datetime(panel["日期"])
    codes = panel["代码"].unique().tolist()
    n_assets = len(codes)
    if n_assets == 0:
        return pd.DataFrame(), {}, []
    target_weight = 1.0 / n_assets if target_weight <= 0 else target_weight
    dates = sorted(panel["日期"].unique())
    if len(dates) < 2:
        return pd.DataFrame(), {}, []

    # 基准：买入持有等权（不调仓）
    closes_wide = panel.pivot_table(index="日期", columns="代码", values="收盘")
    first_date = dates[0]
    close_0 = closes_wide.loc[first_date]
    alloc_per = initial_cash * target_weight
    benchmark_nav = (closes_wide / close_0).sum(axis=1) * alloc_per
    benchmark_nav = benchmark_nav.reindex(dates).ffill().bfill()

    cash = float(initial_cash)
    positions = {c: 0.0 for c in codes}
    rebalance_dates: List[pd.Timestamp] = []
    rows = []
    last_rebalance_idx = -999

    for i, date in enumerate(dates):
        day_df = panel.loc[panel["日期"] == date]
        if day_df.empty or len(day_df) < n_assets:
            rows.append({"日期": date, "策略净值": cash, "基准净值": benchmark_nav.get(date, initial_cash)})
            continue

        # 首日：按 20% 建仓（用开盘价）
        if i == 0:
            for code in codes:
                row = day_df.loc[day_df["代码"] == code]
                if row.empty:
                    continue
                open_p = float(row["开盘"].iloc[0])
                if open_p <= 0:
                    continue
                invest = initial_cash * target_weight
                fee = max(min_fee, invest * fee_rate)
                positions[code] = (invest - fee) / open_p
                cash -= invest
            rebalance_dates.append(date)
            last_rebalance_idx = i
        else:
            # 检查是否到再平衡日
            days_since = i - last_rebalance_idx
            if days_since >= rebalance_interval_days:
                total_equity = cash
                close_today = {}
                for code in codes:
                    r = day_df.loc[day_df["代码"] == code]
                    if not r.empty:
                        c = float(r["收盘"].iloc[0])
                        close_today[code] = c
                        total_equity += positions[code] * c
                if total_equity <= 0:
                    rows.append({"日期": date, "策略净值": cash, "基准净值": benchmark_nav.get(date, initial_cash)})
                    continue
                # 当前权重
                weights = {}
                need_rebalance = False
                for code in codes:
                    if code not in close_today:
                        continue
                    w = (positions[code] * close_today[code]) / total_equity
                    weights[code] = w
                    if abs(w - target_weight) > deviation_threshold:
                        need_rebalance = True
                if need_rebalance:
                    # 再平衡：先卖超配、再买欠配，按收盘价调至目标权重
                    target_value_per = total_equity * target_weight
                    # 先卖
                    for code in codes:
                        if code not in close_today:
                            continue
                        close_p = close_today[code]
                        if close_p <= 0:
                            continue
                        current_value = positions[code] * close_p
                        if current_value <= target_value_per + 1:
                            continue
                        sell_value = current_value - target_value_per
                        if sell_value > 0 and positions[code] > 0:
                            sell_shares = min(sell_value / close_p, positions[code])
                            sell_value = sell_shares * close_p
                            fee = max(min_fee, sell_value * fee_rate)
                            cash += sell_value - fee
                            positions[code] -= sell_shares
                    # 再买
                    for code in codes:
                        if code not in close_today:
                            continue
                        close_p = close_today[code]
                        if close_p <= 0:
                            continue
                        current_value = positions[code] * close_p
                        if current_value >= target_value_per - 1:
                            continue
                        need_value = target_value_per - current_value
                        invest = min(cash, need_value)
                        if invest > 0:
                            fee = max(min_fee, invest * fee_rate)
                            positions[code] += (invest - fee) / close_p
                            cash -= invest
                    rebalance_dates.append(date)
                    last_rebalance_idx = i

        # 当日净值（收盘价计）
        nav = cash
        for code in codes:
            r = day_df.loc[day_df["代码"] == code]
            if not r.empty and positions.get(code, 0) > 0:
                nav += positions[code] * float(r["收盘"].iloc[0])
        bench_val = float(benchmark_nav.get(date, initial_cash))
        rows.append({"日期": date, "策略净值": round(nav, 2), "基准净值": round(bench_val, 2)})

    daily = pd.DataFrame(rows)
    if daily.empty:
        return daily, {}, rebalance_dates

    daily["策略收益率"] = daily["策略净值"].pct_change().fillna(0)
    cum_return = (daily["策略净值"].iloc[-1] - initial_cash) / initial_cash
    years = (daily["日期"].iloc[-1] - daily["日期"].iloc[0]).days / 365.0
    ann_return = (1 + cum_return) ** (1 / max(years, 0.01)) - 1 if years > 0 else 0
    peak = daily["策略净值"].cummax()
    dd = (daily["策略净值"] - peak) / peak
    max_dd = float(dd.min())
    ret_std = daily["策略收益率"].std()
    ann_vol = float(ret_std * np.sqrt(TRADING_DAYS)) if pd.notna(ret_std) and ret_std != 0 else 1e-8
    sharpe = (ann_return - RISK_FREE_RATE) / ann_vol if ann_vol else 0
    bench_cum = (daily["基准净值"].iloc[-1] - initial_cash) / initial_cash

    metrics = {
        "累计收益率": cum_return,
        "年化收益率": ann_return,
        "最大回撤": max_dd,
        "夏普比率": sharpe,
        "再平衡次数": len(rebalance_dates),
        "基准累计收益率": bench_cum,
        "策略最终净值": daily["策略净值"].iloc[-1],
        "基准最终净值": daily["基准净值"].iloc[-1],
        "回测年数": years,
    }
    return daily, metrics, rebalance_dates
