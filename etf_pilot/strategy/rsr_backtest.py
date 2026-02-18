# -*- coding: utf-8 -*-
"""多因子分类轮动策略回测：分组约束、全局 MA20 空仓过滤、动量效率排名、每周五调仓。"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple

from config.settings import (
    RSR_INITIAL_CASH,
    RSR_FEE_RATE,
    RSR_MIN_FEE,
    RSR_TOP_N,
    RSR_SELL_BELOW_RANK,
    RSR_ATR_MULT,
    RSR_ATR_PERIOD,
    RSR_REBALANCE_FREQ,
    RSR_GLOBAL_MA20_THRESHOLD,
)

TRADING_DAYS = 252
RISK_FREE_RATE = 0.02


def _select_top3_by_group(prev_df: pd.DataFrame, code_to_group: Dict[str, str], top_n: int = 3) -> List[str]:
    """按 momentum_eff 排名选前 top_n，且每个分组最多 1 只。"""
    if prev_df.empty or "rank" not in prev_df.columns or not code_to_group:
        return prev_df.nsmallest(top_n, "rank")["代码"].tolist() if "rank" in prev_df.columns else []
    sorted_df = prev_df.sort_values("rank")
    result = []
    used_groups = set()
    for _, row in sorted_df.iterrows():
        if len(result) >= top_n:
            break
        sym = row["代码"]
        g = code_to_group.get(sym)
        if g is None:
            g = "Other"
        if g not in used_groups:
            result.append(sym)
            used_groups.add(g)
    return result


def run_rsr_backtest(
    panel: pd.DataFrame,
    code_to_group: Dict[str, str],
    initial_cash: float = RSR_INITIAL_CASH,
    fee_rate: float = RSR_FEE_RATE,
    min_fee: float = RSR_MIN_FEE,
    top_n: int = RSR_TOP_N,
    sell_below_rank: int = RSR_SELL_BELOW_RANK,
    atr_mult: float = RSR_ATR_MULT,
    rebalance_freq: str = RSR_REBALANCE_FREQ,
    global_threshold: float = RSR_GLOBAL_MA20_THRESHOLD,
) -> Tuple[pd.DataFrame, dict, List[dict], List[Tuple[pd.Timestamp, pd.Timestamp]]]:
    """
    多因子分类轮动：总持仓不超过 top_n，每组最多 1 只；全市场 MA20 之上比例 < global_threshold 时强制空仓；
    按 momentum_eff（20日涨幅/20日标准差）排名；仅每周五调仓。
    返回 (daily_df, metrics, trades, empty_periods)。empty_periods 为全局空仓区间 [(start, end), ...]。
    """
    if panel is None or panel.empty:
        return pd.DataFrame(), {}, [], []
    panel = panel.copy()
    panel["日期"] = pd.to_datetime(panel["日期"])
    dates = sorted(panel["日期"].unique())
    if len(dates) < 50:
        return pd.DataFrame(), {}, [], []

    def benchmark_nav_series() -> pd.Series:
        closes = panel.pivot_table(index="日期", columns="代码", values="收盘")
        ret = closes.pct_change()
        daily_avg_ret = ret.mean(axis=1).fillna(0)
        nav = (1 + daily_avg_ret).cumprod() * initial_cash
        nav = nav.reindex(dates).ffill().bfill()
        return nav

    bench_nav = benchmark_nav_series()
    cash = float(initial_cash)
    positions: Dict[str, dict] = {}
    trades: List[dict] = []
    rows = []
    empty_periods: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    empty_start: pd.Timestamp | None = None

    for i, date in enumerate(dates):
        day_df = panel.loc[panel["日期"] == date]
        if day_df.empty:
            rows.append({"日期": date, "策略净值": cash, "基准净值": bench_nav.get(date, initial_cash)})
            continue

        prev_date = dates[i - 1] if i > 0 else date
        prev_df = panel.loc[panel["日期"] == prev_date]
        # 全局信号：前一日处于 MA20 之上的标的比例
        if "MA20" in prev_df.columns and "收盘" in prev_df.columns:
            pct_above = (prev_df["收盘"] > prev_df["MA20"]).mean()
        else:
            pct_above = 1.0
        force_empty = pct_above < global_threshold

        # 是否本周五调仓
        do_rebalance = False
        if rebalance_freq == "weekly_friday":
            do_rebalance = pd.Timestamp(date).weekday() == 4
        elif rebalance_freq == "daily":
            do_rebalance = True
        else:
            wk = pd.Timestamp(date).isocalendar()[1]
            do_rebalance = (i == 0) or (wk != pd.Timestamp(dates[i - 1]).isocalendar()[1])

        top3 = _select_top3_by_group(prev_df, code_to_group, top_n) if not prev_df.empty else []

        # 1) 全局空仓：强制平仓
        if force_empty and positions:
            for sym in list(positions.keys()):
                sym_row = day_df.loc[day_df["代码"] == sym]
                if not sym_row.empty:
                    open_p = float(sym_row["开盘"].iloc[0])
                    value = positions[sym]["shares"] * open_p
                    fee = max(min_fee, value * fee_rate)
                    cash += value - fee
                    pnl = value - fee - positions[sym]["cost_basis"]
                    trades.append({"date": date, "symbol": sym, "action": "sell", "reason": "全局空仓", "pnl": pnl, "fee": fee})
            positions.clear()
            if empty_start is None:
                empty_start = date

        if not force_empty and empty_start is not None:
            empty_periods.append((empty_start, date))
            empty_start = None

        # 2) 吊灯止损与跌出前 8 卖出
        to_sell = []
        for sym in list(positions.keys()):
            sym_row = day_df.loc[day_df["代码"] == sym]
            sym_prev = prev_df.loc[prev_df["代码"] == sym]
            if sym_row.empty or sym_prev.empty:
                continue
            open_p = float(sym_row["开盘"].iloc[0])
            atr_prev = float(sym_prev["ATR"].iloc[0]) if pd.notna(sym_prev["ATR"].iloc[0]) else 0
            rank_prev = int(sym_prev["rank"].iloc[0]) if "rank" in sym_prev.columns and pd.notna(sym_prev["rank"].iloc[0]) else 999
            pos = positions[sym]
            holding_high = pos["holding_high"]
            if open_p <= 0:
                continue
            value = pos["shares"] * open_p
            fee = max(min_fee, value * fee_rate)
            if holding_high > 0 and atr_prev > 0 and open_p < holding_high - atr_prev * atr_mult:
                cash += value - fee
                trades.append({"date": date, "symbol": sym, "action": "sell", "reason": "吊灯止损", "pnl": value - fee - pos["cost_basis"], "fee": fee})
                to_sell.append(sym)
                continue
            if rank_prev > sell_below_rank:
                cash += value - fee
                trades.append({"date": date, "symbol": sym, "action": "sell", "reason": "跌出前8换仓", "pnl": value - fee - pos["cost_basis"], "fee": fee})
                to_sell.append(sym)
        for sym in to_sell:
            del positions[sym]

        # 3) 调仓：等权持有 top3（每组最多 1 只），且非强制空仓日
        if do_rebalance and top3 and not force_empty:
            for s in list(positions.keys()):
                if s not in top3:
                    sym_row = day_df.loc[day_df["代码"] == s]
                    if not sym_row.empty:
                        open_p = float(sym_row["开盘"].iloc[0])
                        value = positions[s]["shares"] * open_p
                        fee = max(min_fee, value * fee_rate)
                        cash += value - fee
                        pnl = value - fee - positions[s]["cost_basis"]
                        trades.append({"date": date, "symbol": s, "action": "sell", "reason": "调出前3", "pnl": pnl, "fee": fee})
                        del positions[s]
            total_equity = cash + sum(
                positions[s]["shares"] * float(day_df.loc[day_df["代码"] == s, "开盘"].iloc[0])
                for s in positions
                if s in day_df["代码"].values
            )
            target_per = total_equity / top_n if top_n else 0
            for sym in top3:
                sym_row = day_df.loc[day_df["代码"] == sym]
                if sym_row.empty:
                    continue
                open_p = float(sym_row["开盘"].iloc[0])
                high_p = float(sym_row["最高"].iloc[0])
                if open_p <= 0:
                    continue
                current_value = positions[sym]["shares"] * open_p if sym in positions else 0
                need = target_per - current_value
                if need > 10:
                    invest = min(cash, need)
                    if invest > 0:
                        fee = max(min_fee, invest * fee_rate)
                        shares_buy = (invest - fee) / open_p
                        cash -= invest
                        if sym in positions:
                            positions[sym]["shares"] += shares_buy
                            positions[sym]["cost_basis"] += invest - fee
                            positions[sym]["holding_high"] = max(positions[sym]["holding_high"], high_p)
                        else:
                            positions[sym] = {"shares": shares_buy, "cost_basis": invest - fee, "holding_high": high_p}
                        trades.append({"date": date, "symbol": sym, "action": "buy", "reason": "调入前3", "pnl": None, "fee": fee})
                elif need < -10 and sym in positions:
                    sell_value = min(positions[sym]["shares"] * open_p, -need)
                    sell_shares = sell_value / open_p
                    if sell_shares >= positions[sym]["shares"] * 0.999:
                        value = positions[sym]["shares"] * open_p
                        fee = max(min_fee, value * fee_rate)
                        cash += value - fee
                        pnl = value - fee - positions[sym]["cost_basis"]
                        trades.append({"date": date, "symbol": sym, "action": "sell", "reason": "调仓减仓", "pnl": pnl, "fee": fee})
                        del positions[sym]
                    else:
                        value = sell_shares * open_p
                        fee = max(min_fee, value * fee_rate)
                        cash += value - fee
                        cost_ratio = sell_shares / positions[sym]["shares"]
                        cost_sold = positions[sym]["cost_basis"] * cost_ratio
                        pnl = value - fee - cost_sold
                        positions[sym]["shares"] -= sell_shares
                        positions[sym]["cost_basis"] -= cost_sold
                        trades.append({"date": date, "symbol": sym, "action": "sell", "reason": "调仓减仓", "pnl": pnl, "fee": fee})

        for sym in positions:
            sym_row = day_df.loc[day_df["代码"] == sym]
            if not sym_row.empty:
                high_p = float(sym_row["最高"].iloc[0])
                positions[sym]["holding_high"] = max(positions[sym]["holding_high"], high_p)

        nav = cash
        for sym in positions:
            sym_row = day_df.loc[day_df["代码"] == sym]
            if not sym_row.empty:
                nav += positions[sym]["shares"] * float(sym_row["收盘"].iloc[0])
        bench_val = float(bench_nav.get(date, initial_cash))
        rows.append({"日期": date, "策略净值": round(nav, 2), "基准净值": round(bench_val, 2)})

    if empty_start is not None and dates:
        empty_periods.append((empty_start, dates[-1]))

    daily = pd.DataFrame(rows)
    if daily.empty:
        return daily, {}, trades, empty_periods

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
        "交易次数": len([t for t in trades if t["action"] == "sell"]),
        "基准累计收益率": bench_cum,
        "策略最终净值": daily["策略净值"].iloc[-1],
        "基准最终净值": daily["基准净值"].iloc[-1],
        "回测年数": years,
    }
    return daily, metrics, trades, empty_periods
