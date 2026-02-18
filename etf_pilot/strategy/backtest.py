# -*- coding: utf-8 -*-
"""策略回测引擎：ATR 吊灯止损 + 相对强度排名买卖 + Core 右侧加仓。"""
import pandas as pd
import numpy as np

from .asset_type import ASSET_TYPE_CORE

TRADING_DAYS = 252
RISK_FREE_RATE = 0.02
DEFAULT_INITIAL_CASH = 100_000
DEFAULT_FEE_RATE = 0.0012
DEFAULT_MIN_FEE = 5.0
MAX_ADDON_BATCHES = 3
ATR_PERIOD = 14
CHANDELIER_ATR_MULT = 2.5
RANK_TOP_PCT = 0.75   # 前 25% 才允许买入
RANK_SWITCH_BELOW = 0.5  # 跌出前 50% 换仓
HIGH_20_WINDOW = 20
HIGH_5_WINDOW = 5
PAYOFF_RATIO_WARN = 2.0  # 盈亏比低于此提示容错率过低


def _execute_price(hist: pd.DataFrame, i: int) -> float:
    """当日执行价：优先开盘价，缺失时用昨日收盘（避免前瞻）。"""
    row = hist.iloc[i]
    open_p = row.get("开盘")
    if pd.notna(open_p) and open_p and open_p > 0:
        return float(open_p)
    if i > 0:
        return float(hist["收盘"].iloc[i - 1])
    return float(row["收盘"])


def _ensure_atr_and_highs(hist: pd.DataFrame) -> pd.DataFrame:
    """为 hist 增加 ATR、近 20 日最高价、近 5 日最高价（用于吊灯止损与右侧加仓）。"""
    high = hist["最高"] if "最高" in hist.columns else hist["收盘"]
    low = hist["最低"] if "最低" in hist.columns else hist["收盘"]
    close = hist["收盘"]
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    hist = hist.copy()
    hist["ATR"] = tr.rolling(ATR_PERIOD, min_periods=1).mean()
    hist["high_20"] = high.rolling(HIGH_20_WINDOW, min_periods=1).max()
    hist["high_5"] = high.rolling(HIGH_5_WINDOW, min_periods=1).max()
    return hist


def run_backtest(
    hist: pd.DataFrame,
    asset_type: str,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    fee_rate: float = DEFAULT_FEE_RATE,
    min_fee: float = DEFAULT_MIN_FEE,
    rank_by_date: pd.Series | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    新范式：ATR 吊灯止损 + 相对强度买卖 + Core 右侧加仓。
    - 卖出：当前价 < 近 20 日最高价 - 2.5*ATR（吊灯止损）；或持有标的跌出前 50% 换仓。
    - 买入：仅当排名在前 25% 且价格在 MA20 之上。
    - Core 加仓：价格回升并重新站上近 5 日最高价时加仓 0.5 倍仓位（最多 3 批）。
    - 无前瞻：用昨日数据出信号、今日开盘执行。
    rank_by_date：index=日期，value=rank_pct（1=最强）。若为 None 则无法按排名买卖，仅用吊灯与 MA20。
    """
    if hist is None or len(hist) < 200:
        return pd.DataFrame(), {}
    hist = hist.copy()
    hist = hist.sort_values("日期").reset_index(drop=True)
    hist = _ensure_atr_and_highs(hist)
    if "MA20" not in hist.columns:
        hist["MA20"] = hist["收盘"].rolling(20, min_periods=1).mean()

    # 将 rank 对齐到 hist 的日期（用于按前一日取排名）
    rank_aligned: np.ndarray | None = None
    if rank_by_date is not None and len(rank_by_date) > 0:
        try:
            s = rank_by_date.reindex(pd.to_datetime(hist["日期"]))
            rank_aligned = s.values
        except Exception:
            rank_aligned = None

    cash = float(initial_cash)
    position = 0.0
    cost_basis = 0.0
    trades_pnl: list[float] = []
    addon_count = 0

    rows = []
    close_0 = float(hist["收盘"].iloc[0])
    for i in range(len(hist)):
        row = hist.iloc[i]
        date = row["日期"]
        close = float(row["收盘"])
        exec_price = _execute_price(hist, i)
        # 前一日数据（用于信号判断，次日执行）
        prev_row = hist.iloc[i - 1] if i > 0 else row
        close_prev = float(prev_row["收盘"])
        high_20_prev = prev_row.get("high_20")
        atr_prev = prev_row.get("ATR")
        ma20_prev = prev_row.get("MA20")
        # 前一日对应的「近 5 日最高价」
        high_5_prev = float(prev_row["high_5"]) if i > 0 else close

        rank_prev = None
        if rank_aligned is not None and i > 0 and i - 1 < len(rank_aligned):
            v = rank_aligned[i - 1]
            if pd.notna(v):
                rank_prev = float(v)

        sig_display = "持有"
        # 1) 吊灯止损：昨日 high_20 - 2.5*ATR，今日开盘跌破则卖
        chandelier = None
        if high_20_prev is not None and atr_prev is not None and pd.notna(high_20_prev) and pd.notna(atr_prev) and atr_prev > 0:
            chandelier = float(high_20_prev) - CHANDELIER_ATR_MULT * float(atr_prev)
        if position > 0 and chandelier is not None and exec_price < chandelier:
            value = position * exec_price
            fee = max(min_fee, value * fee_rate)
            cash = value - fee
            trades_pnl.append((value - fee) - cost_basis)
            position = 0
            cost_basis = 0
            addon_count = 0
            sig_display = "减仓(吊灯止损)"
        # 2) 换仓：跌出前 50%
        elif position > 0 and rank_prev is not None and rank_prev < RANK_SWITCH_BELOW:
            value = position * exec_price
            fee = max(min_fee, value * fee_rate)
            cash = value - fee
            trades_pnl.append((value - fee) - cost_basis)
            position = 0
            cost_basis = 0
            addon_count = 0
            sig_display = "减仓(跌出前50%)"
        # 3) 买入：前 25% 且 价格 > MA20（用昨日数据）
        elif position == 0 and cash > 0 and exec_price > 0:
            can_buy = ma20_prev is not None and pd.notna(ma20_prev) and close_prev > float(ma20_prev)
            if rank_by_date is not None:
                can_buy = can_buy and (rank_prev is not None and rank_prev >= RANK_TOP_PCT)
            if can_buy:
                fee = max(min_fee, cash * fee_rate)
                invest = cash - fee
                position = invest / exec_price
                cost_basis = invest
                cash = 0
                addon_count = 0
                sig_display = "买入"
        # 4) Core 右侧加仓：站上近 5 日最高价
        elif (
            asset_type == ASSET_TYPE_CORE
            and position > 0
            and cash > 0
            and addon_count < MAX_ADDON_BATCHES
            and exec_price > 0
        ):
            # 昨日收盘 < 昨日 5 日高，今日开盘 >= 昨日 5 日高 → 突破加仓
            if close_prev < high_5_prev and exec_price >= high_5_prev:
                position_value = position * exec_price
                addon_target = 0.5 * position_value
                addon_amount = min(cash, addon_target)
                if addon_amount > 0:
                    fee = max(min_fee, addon_amount * fee_rate)
                    invest = addon_amount - fee
                    position += invest / exec_price
                    cost_basis += invest
                    cash -= addon_amount
                    addon_count += 1
                    sig_display = "加仓(站上5日高)"

        nav = cash + position * close
        benchmark = initial_cash * (close / close_0)
        rows.append({
            "日期": date,
            "收盘": close,
            "信号": sig_display,
            "策略净值": round(nav, 2),
            "基准净值": round(benchmark, 2),
            "持仓股数": position,
            "现金": round(cash, 2),
        })

    daily = pd.DataFrame(rows)
    # 指标
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
    n_trades = len(trades_pnl)
    win_rate = (sum(1 for x in trades_pnl if x > 0) / n_trades * 100) if n_trades > 0 else 0

    wins = [x for x in trades_pnl if x > 0]
    losses = [x for x in trades_pnl if x <= 0]
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = abs(float(np.mean(losses))) if losses else 0.0
    payoff_ratio = (avg_win / avg_loss) if avg_loss > 0 else (float("inf") if avg_win > 0 else 0.0)

    bench_cum = (daily["基准净值"].iloc[-1] - initial_cash) / initial_cash
    bench_peak = daily["基准净值"].cummax()
    bench_dd = (daily["基准净值"] - bench_peak) / bench_peak
    bench_max_dd = float(bench_dd.min())

    metrics = {
        "累计收益率": cum_return,
        "年化收益率": ann_return,
        "最大回撤": max_dd,
        "胜率": win_rate,
        "夏普比率": sharpe,
        "交易次数": n_trades,
        "基准累计收益率": bench_cum,
        "基准最大回撤": bench_max_dd,
        "策略最终净值": daily["策略净值"].iloc[-1],
        "基准最终净值": daily["基准净值"].iloc[-1],
        "回测年数": years,
        "盈利交易平均盈利": avg_win,
        "亏损交易平均亏损": avg_loss,
        "盈亏比": payoff_ratio,
    }
    return daily, metrics


def format_summary(name: str, metrics: dict) -> str:
    """生成一段话总结：策略相对无脑持有的优化/弱化、回撤变化及盈亏比提示。"""
    if not metrics:
        return "回测数据不足，无法生成总结。"
    cum = metrics.get("累计收益率", 0) or 0
    bench = metrics.get("基准累计收益率", 0) or 0
    max_dd = metrics.get("最大回撤", 0) or 0
    bench_dd = metrics.get("基准最大回撤", 0) or 0
    payoff = metrics.get("盈亏比") or 0
    diff_pct = (cum - bench) * 100
    dd_improve = (max_dd - bench_dd) * 100 if bench_dd != 0 else 0
    if diff_pct > 0:
        ret_word = f"优化了 {diff_pct:.1f} 个百分点"
    else:
        ret_word = f"弱化了 {abs(diff_pct):.1f} 个百分点"
    if dd_improve > 0:
        dd_word = f"最大回撤降低了约 {dd_improve:.1f} 个百分点。"
    elif dd_improve < 0:
        dd_word = f"最大回撤扩大了约 {abs(dd_improve):.1f} 个百分点。"
    else:
        dd_word = "最大回撤与基准接近。"
    base = f"该策略在 **{name}** 上相比无脑持有 {ret_word}；{dd_word}"
    if payoff < PAYOFF_RATIO_WARN and payoff > 0:
        base += " **策略容错率过低（盈亏比 < 2），建议谨慎。**"
    return base
