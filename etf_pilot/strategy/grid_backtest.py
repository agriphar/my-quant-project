# -*- coding: utf-8 -*-
"""步进式网格做T：ATR 自适应步长、盈利门槛、High/Low 触发、last_op_price 步进、手续费/利润比与活跃度。"""
import pandas as pd
import numpy as np
from typing import Tuple, List

from config.settings import (
    GRID_STEP_PCT,
    GRID_UNIT_PCT,
    GRID_INITIAL_CASH,
    GRID_FEE_RATE,
    GRID_MIN_FEE,
)

ATR_PERIOD = 14
FIXED_FEE = 5.0
MIN_PROFIT_THRESHOLD = 5.0 * 3  # 预期利润至少覆盖 3 倍最低手续费才触发
COMMISSION_RATE = 0.0012
FEE_WARN_PCT = 0.20
INITIAL_POSITION_PCT = 0.5
GRID_LEVEL_PCT = 0.05
DEBUG_TRADE_TOP_N = 20
UI_TRADE_TOP_N = 10
STEP_PCT_MIN = 0.005
STEP_PCT_MAX = 0.05
# 趋势型/震荡型：底仓与是否允许网格卖出
TREND_POSITION_PCT = 0.8   # 趋势型 80% 底仓，禁止网格卖底仓；仅回撤补仓+波段收割
OSCILLATING_POSITION_PCT = 0.4  # 震荡型 40% 底仓，标准双向网格
ASSET_TREND = "Trend (趋势型)"
TREND_ADD_DROP_PCT = 0.02   # 趋势型：每下跌 2% 补仓
TREND_ADD_UNIT_PCT = 0.05   # 趋势型：每次补入 5% 资金
TREND_HARVEST_RISE_PCT = 0.03  # 趋势型：回升 3% 后卖出该笔补仓位（波段收割）


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = ATR_PERIOD) -> pd.Series:
    """ATR = SMA(TR, period), TR = max(H-L, |H-prev_C|, |L-prev_C|)。"""
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    return tr.rolling(period, min_periods=1).mean()


def _fee_and_warn(amount: float, fee_rate: float, min_fee: float, debug: bool, side: str, date, apply_min_fee: bool = True) -> float:
    """手续费：网格交易用 max(最低5元, 比例)；初始底仓仅用比例，不设最低（不影响建仓）。"""
    fee = (max(min_fee, amount * fee_rate) if apply_min_fee else (amount * fee_rate))
    if debug and amount > 0 and fee / amount > FEE_WARN_PCT:
        print(f"[网格回测] 警告: {date} {side} 金额=¥{amount:.2f} 手续费=¥{fee:.2f} 占比={fee/amount*100:.1f}%>20%")
    return fee


def run_grid_backtest(
    series: pd.DataFrame,
    initial_cash: float = GRID_INITIAL_CASH,
    fee_rate: float = GRID_FEE_RATE,
    min_fee: float = GRID_MIN_FEE,
    step_pct: float = GRID_STEP_PCT,
    unit_pct: float = GRID_UNIT_PCT,
    lookback: int = 30,
    buy_pyramid: float = 0.10,
    sell_accel: float = 0.15,
    debug: bool = True,
    asset_personality: str | None = None,
) -> Tuple[pd.DataFrame, dict, List[dict]]:
    """
    步进式网格；按资产性格匹配策略：
    - Trend (趋势型)：80% 底仓，只允许买入、严禁网格卖出（仅跌破长期趋势线 MA60 时减仓）。
    - Oscillating (震荡型)：30% 底仓，标准双向网格。
    """
    if series is None or series.empty or "收盘" not in series.columns or "日期" not in series.columns:
        return pd.DataFrame(), {}, []

    df = series.sort_values("日期").reset_index(drop=True)
    df["日期"] = pd.to_datetime(df["日期"])
    dates = df["日期"].tolist()
    closes = df["收盘"].values
    opens = df["开盘"].values if "开盘" in df.columns else closes
    highs = df["最高"].values if "最高" in df.columns else closes
    lows = df["最低"].values if "最低" in df.columns else closes
    # MA60：趋势型跌破时允许卖出
    if "MA60" in df.columns:
        ma60 = df["MA60"].values
    else:
        ma60 = pd.Series(closes).rolling(60, min_periods=1).mean().values

    if len(dates) < ATR_PERIOD + 1:
        if debug:
            print(f"[网格回测] 数据不足，至少需要 {ATR_PERIOD + 1} 日以计算 ATR。")
        return pd.DataFrame(), {}, []

    close_0 = closes[0]
    if close_0 <= 0:
        return pd.DataFrame(), {}, []

    is_trend = asset_personality == ASSET_TREND
    initial_position_pct_use = TREND_POSITION_PCT if is_trend else (OSCILLATING_POSITION_PCT if asset_personality else INITIAL_POSITION_PCT)
    allow_grid_sell = not is_trend  # 趋势型严禁网格卖出，仅回撤补仓+波段收割

    # ATR 自适应步长：仅震荡型用于网格步长
    high_s = pd.Series(highs)
    low_s = pd.Series(lows)
    close_s = pd.Series(closes)
    atr_s = _atr(high_s, low_s, close_s, ATR_PERIOD)
    step_daily = (atr_s.shift(1) / close_s.shift(1)).fillna(step_pct)
    step_daily = step_daily.clip(lower=STEP_PCT_MIN, upper=STEP_PCT_MAX).values

    hold_nav = initial_cash * (closes / close_0)

    # 底仓：趋势型 80%、震荡型 40%；初始建仓不适用最低 5 元（只对网格交易收最低手续费）
    cash = float(initial_cash) * (1 - initial_position_pct_use)
    invest_0 = float(initial_cash) * initial_position_pct_use
    fee_0 = _fee_and_warn(invest_0, fee_rate, min_fee, debug, "初始底仓", dates[0], apply_min_fee=False)
    buy_shares_0 = (invest_0 - fee_0) / close_0 if close_0 > 0 else 0
    cash = float(initial_cash) - invest_0 - fee_0  # 实际剩余现金（已扣建仓手续费）
    total_fee_paid = fee_0

    # 趋势型：核心底仓永不卖；补仓批次用于「回撤 2% 补 5%，回升 3% 只卖该批」
    core_shares = buy_shares_0 if is_trend else 0.0
    add_lots: List[dict] = []  # [{"entry_price": float, "shares": float}, ...]
    ref_for_drawdown = float(close_0)  # 用于「下跌 2%」的参考价
    shares = buy_shares_0
    unit_cost = close_0 if shares > 0 else 0.0
    last_op_price = float(close_0)

    trades: List[dict] = []
    rows = []
    # 记录初始底仓为一笔“买入”（便于足迹完整）
    nav_0 = cash + shares * close_0
    trades.append({
        "日期": dates[0],
        "方向": "买入",
        "成交价": round(close_0, 4),
        "数量": round(shares, 4),
        "金额": round(invest_0, 2),
        "手续费": round(fee_0, 2),
        "净利润": None,
        "净值": round(nav_0, 2),
        "剩余现金": round(cash, 2),
    })

    grid_trade_count = 0  # 不含初始底仓的网格成交笔数
    no_trade_debug: List[dict] = []  # 无成交时记录每日偏差

    for i in range(len(dates)):
        d = dates[i]
        c = closes[i]
        o = opens[i] if i < len(opens) else c
        h = highs[i] if i < len(highs) else c
        lo = lows[i] if i < len(lows) else c
        step_i = step_daily[i] if i < len(step_daily) else step_pct

        total_shares = (core_shares + sum(l["shares"] for l in add_lots)) if is_trend else shares
        total_equity = cash + total_shares * c
        if total_equity <= 0:
            total_equity = initial_cash

        did_buy = False
        did_sell = False

        if is_trend:
            # 趋势型：参考价为自上次补仓以来最高价，回撤 2% 补 5% 资金；回升 3% 只卖该笔补仓位（波段收割）
            ref_for_drawdown = max(ref_for_drawdown, float(c))
            if c <= ref_for_drawdown * (1 - TREND_ADD_DROP_PCT) and cash > 0:
                invest = min(initial_cash * TREND_ADD_UNIT_PCT, cash)
                if invest > 0:
                    fee = _fee_and_warn(invest, fee_rate, min_fee, debug, "补仓", d, apply_min_fee=True)
                    buy_shares_add = (invest - fee) / c if c > 0 else 0
                    if buy_shares_add > 0:
                        add_lots.append({"entry_price": float(c), "shares": buy_shares_add})
                        cash -= invest
                        ref_for_drawdown = float(c)
                        total_fee_paid += fee
                        grid_trade_count += 1
                        did_buy = True
                        nav_after = cash + core_shares * c + sum(l["shares"] for l in add_lots) * c
                        trades.append({
                            "日期": d, "方向": "补仓", "成交价": round(c, 4), "数量": round(buy_shares_add, 4),
                            "金额": round(invest, 2), "手续费": round(fee, 2), "净利润": None,
                            "净值": round(nav_after, 2), "剩余现金": round(cash, 2),
                        })
            # 波段收割：补仓位回升 3% 则卖出该批
            harvest_remove = []
            for j, lot in enumerate(add_lots):
                if c >= lot["entry_price"] * (1 + TREND_HARVEST_RISE_PCT):
                    harvest_remove.append(j)
            for j in sorted(harvest_remove, reverse=True):
                lot = add_lots.pop(j)
                sell_value = lot["shares"] * c
                fee = _fee_and_warn(sell_value, fee_rate, min_fee, debug, "波段收割", d, apply_min_fee=True)
                cash += sell_value - fee
                realized = (c - lot["entry_price"]) * lot["shares"]
                total_fee_paid += fee
                grid_trade_count += 1
                did_sell = True
                nav_after = cash + core_shares * c + sum(l["shares"] for l in add_lots) * c
                trades.append({
                    "日期": d, "方向": "波段收割", "成交价": round(c, 4), "数量": round(lot["shares"], 4),
                    "金额": round(sell_value, 2), "手续费": round(fee, 2), "净利润": round(realized - fee, 2),
                    "净值": round(nav_after, 2), "剩余现金": round(cash, 2),
                })
            # 趋势型不参与下方网格买卖
        else:
            buy_trigger = last_op_price * (1 - step_i)
            sell_trigger = last_op_price * (1 + step_i)

            # 1) 买入：当日 Low 触及买入档，且现金有余，且预期利润≥3倍最低手续费
            if lo <= buy_trigger and cash > 0:
                invest = total_equity * unit_pct
                invest = min(invest, cash)
                expected_profit = invest * step_i
                if invest > 0 and expected_profit >= MIN_PROFIT_THRESHOLD:
                    fee = _fee_and_warn(invest, fee_rate, min_fee, debug, "买入", d, apply_min_fee=True)
                    exec_price = buy_trigger
                    buy_shares = (invest - fee) / exec_price if exec_price > 0 else 0
                    if buy_shares > 0:
                        cash -= invest
                        if shares <= 0:
                            unit_cost = exec_price
                        else:
                            unit_cost = (unit_cost * shares + exec_price * buy_shares) / (shares + buy_shares)
                        shares += buy_shares
                        last_op_price = exec_price
                        did_buy = True
                        grid_trade_count += 1
                        total_fee_paid += fee
                        nav_after = cash + shares * c
                        trades.append({
                            "日期": d,
                            "方向": "买入",
                            "成交价": round(exec_price, 4),
                            "数量": round(buy_shares, 4),
                            "金额": round(invest, 2),
                            "手续费": round(fee, 2),
                            "净利润": None,
                            "净值": round(nav_after, 2),
                            "剩余现金": round(cash, 2),
                        })
                        total_equity = cash + shares * c

            # 2) 卖出：震荡型 High 触及卖出档且预期利润≥门槛（趋势型已在上方仅做波段收割，此处不卖）
            ma60_i = ma60[i] if i < len(ma60) and pd.notna(ma60[i]) and ma60[i] > 0 else None
            trend_break_sell = False  # 趋势型不再按 MA60 减仓，仅波段收割
            grid_sell_trigger = allow_grid_sell and h >= sell_trigger and shares > 0

            if trend_break_sell:
                sell_pct = 0.5
                sell_shares = max(0, (shares * sell_pct))
                if sell_shares > 0:
                    exec_price = c
                    sell_value = sell_shares * exec_price
                    fee = _fee_and_warn(sell_value, fee_rate, min_fee, debug, "卖出(破趋势)", d, apply_min_fee=True)
                    cash += sell_value - fee
                    realized = (exec_price - unit_cost) * sell_shares
                    shares -= sell_shares
                    if shares > 0:
                        unit_cost = unit_cost - realized / shares
                    else:
                        unit_cost = 0.0
                    last_op_price = exec_price
                    did_sell = True
                    grid_trade_count += 1
                    total_fee_paid += fee
                    nav_after = cash + shares * c
                    trades.append({
                        "日期": d, "方向": "卖出(破趋势)", "成交价": round(exec_price, 4), "数量": round(sell_shares, 4),
                        "金额": round(sell_value, 2), "手续费": round(fee, 2), "净利润": round(realized - fee, 2),
                        "净值": round(nav_after, 2), "剩余现金": round(cash, 2),
                    })
            elif grid_sell_trigger:
                sell_value_target = total_equity * unit_pct
                exec_price = sell_trigger
                sell_shares = min(sell_value_target / exec_price, shares) if exec_price > 0 else 0
                expected_profit_sell = (sell_shares * exec_price) * step_i if sell_shares > 0 else 0
                if sell_shares > 0 and expected_profit_sell >= MIN_PROFIT_THRESHOLD:
                    sell_value = sell_shares * exec_price
                    fee = _fee_and_warn(sell_value, fee_rate, min_fee, debug, "卖出", d, apply_min_fee=True)
                    cash += sell_value - fee
                    realized = (exec_price - unit_cost) * sell_shares
                    shares -= sell_shares
                    if shares > 0:
                        unit_cost = unit_cost - realized / shares
                    else:
                        unit_cost = 0.0
                    last_op_price = exec_price
                    did_sell = True
                    grid_trade_count += 1
                    total_fee_paid += fee
                    net_profit = realized - fee
                    nav_after = cash + shares * c
                    trades.append({
                        "日期": d, "方向": "卖出", "成交价": round(exec_price, 4), "数量": round(sell_shares, 4),
                        "金额": round(sell_value, 2), "手续费": round(fee, 2), "净利润": round(net_profit, 2),
                        "净值": round(nav_after, 2), "剩余现金": round(cash, 2),
                    })

        # 当日净值与持仓成本（趋势型 = core + add_lots 加权成本）
        if is_trend:
            total_shares = core_shares + sum(l["shares"] for l in add_lots)
            nav = cash + total_shares * c
            unit_cost_day = (core_shares * close_0 + sum(l["shares"] * l["entry_price"] for l in add_lots)) / total_shares if total_shares > 0 else (float(close_0) if core_shares > 0 else 0.0)
        else:
            nav = cash + shares * c
            unit_cost_day = unit_cost
        rows.append({
            "日期": d,
            "持有净值": round(hold_nav[i], 2),
            "网格净值": round(nav, 2),
            "当前成本价": round(unit_cost_day, 4) if unit_cost_day > 0 else None,
            "现价": round(c, 4),
        })

        # 无成交时记录当日价格相对买卖档位的偏差（供 Debug，仅震荡型有网格档位）
        if debug and not is_trend and not did_buy and not did_sell:
            buy_trigger = last_op_price * (1 - step_i)
            sell_trigger = last_op_price * (1 + step_i)
            pct_to_buy = (lo - buy_trigger) / buy_trigger * 100 if buy_trigger > 0 else np.nan
            pct_to_sell = (sell_trigger - h) / sell_trigger * 100 if sell_trigger > 0 else np.nan
            no_trade_debug.append({
                "日期": d,
                "收盘": round(c, 4),
                "最低": round(lo, 4),
                "最高": round(h, 4),
                "买入档价": round(buy_trigger, 4),
                "卖出档价": round(sell_trigger, 4),
                "最低距买入档%": round(pct_to_buy, 4) if not np.isnan(pct_to_buy) else None,
                "最高距卖出档%": round(pct_to_sell, 4) if not np.isnan(pct_to_sell) else None,
            })

    daily = pd.DataFrame(rows)
    if daily.empty:
        return daily, {}, trades

    final_nav = daily["网格净值"].iloc[-1]
    grid_profit = final_nav - initial_cash
    hold_ret = (hold_nav[-1] - initial_cash) / initial_cash
    grid_ret = (final_nav - initial_cash) / initial_cash
    extra_t_pct = (grid_ret - hold_ret) * 100
    years = (daily["日期"].iloc[-1] - daily["日期"].iloc[0]).days / 365.0
    grid_ann = (1 + grid_ret) ** (1 / max(years, 0.01)) - 1 if years > 0 else 0
    peak = daily["网格净值"].cummax()
    dd = (daily["网格净值"] - peak) / peak.replace(0, np.nan)
    max_dd = float(dd.min()) if dd.notna().any() else 0.0
    fee_pct_of_profit = (total_fee_paid / grid_profit * 100) if grid_profit > 0 else (100.0 if total_fee_paid > 0 else 0)
    weeks = years * 52 if years > 0 else max((daily["日期"].iloc[-1] - daily["日期"].iloc[0]).days / 7.0, 0.01)
    trades_per_week = grid_trade_count / weeks if weeks > 0 else 0

    # 自动建议：回测效果不佳时分析原因
    suggestions: List[str] = []
    if grid_trade_count == 0 or grid_profit <= 0:
        vol_20 = float(pd.Series(closes).pct_change().dropna().tail(20).std() * 100) if len(closes) >= 20 else 0
        if vol_20 < 0.5:
            suggestions.append("原因是波动率太低，价格很少触及网格档位。")
        if fee_pct_of_profit >= 80 or (grid_profit <= 0 and total_fee_paid > 0):
            suggestions.append("手续费占比太高，建议单笔投入从 2k 提到 1w，或选波动更大的标的。")
    if not suggestions and fee_pct_of_profit >= 50:
        suggestions.append("手续费占利润比例偏高，可考虑提高单笔投入（如 1 万以上）以降低费率侵蚀。")

    # 跑输基准时标注原因：卖飞了 vs 补仓太早被套了
    underperform_reason = None
    if grid_ret < hold_ret and len(trades) > 1:
        # 仅统计网格交易（排除初始底仓）
        grid_only = [t for t in trades[1:] if t.get("方向") in ("卖出", "波段收割", "卖出(破趋势)")]
        add_only = [t for t in trades[1:] if t.get("方向") in ("买入", "补仓")]
        fwd_days = min(20, len(dates) // 4)
        date_to_idx = {d: i for i, d in enumerate(dates)}
        sell_fly_score = 0.0
        add_stuck_score = 0.0
        for t in grid_only:
            idx = date_to_idx.get(t["日期"])
            if idx is not None and idx + fwd_days < len(closes) and closes[idx] > 0:
                fwd_ret = (closes[idx + fwd_days] - closes[idx]) / closes[idx]
                sell_fly_score += fwd_ret
        for t in add_only:
            idx = date_to_idx.get(t["日期"])
            if idx is not None and idx + fwd_days < len(closes) and closes[idx] > 0:
                fwd_ret = (closes[idx + fwd_days] - closes[idx]) / closes[idx]
                add_stuck_score -= fwd_ret
        if sell_fly_score > add_stuck_score and sell_fly_score > 0.02:
            underperform_reason = "卖飞了"
        elif add_stuck_score > 0.02:
            underperform_reason = "补仓太早被套了"

    last_row = daily.iloc[-1]
    metrics = {
        "累计收益率": grid_ret,
        "年化收益率": grid_ann,
        "最大回撤": max_dd,
        "持有累计收益率": hold_ret,
        "做T额外收益pct": extra_t_pct,
        "策略最终净值": final_nav,
        "持有最终净值": float(hold_nav[-1]),
        "当前成本价": last_row.get("当前成本价"),
        "现价": last_row.get("现价"),
        "回测年数": years,
        "网格成交笔数": len(trades),
        "累计网格利润": grid_profit,
        "总手续费": total_fee_paid,
        "手续费占利润比pct": fee_pct_of_profit,
        "手续费利润比": fee_pct_of_profit / 100.0 if fee_pct_of_profit is not None else None,
        "网格活跃度_每周成交次数": round(trades_per_week, 2),
        "自动建议": " ".join(suggestions) if suggestions else None,
        "资产性格": asset_personality,
        "底仓比例": initial_position_pct_use,
        "策略说明": "趋势型：80%底仓+回撤2%补5%、回升3%波段收割" if is_trend else "震荡型：40%底仓双向网格",
        "跑输原因": underperform_reason,
    }

    # 成交足迹 DataFrame（日期、价格、类型、剩余现金）
    trades_df = pd.DataFrame([
        {"日期": t["日期"], "价格": t["成交价"], "类型": t["方向"], "剩余现金": t["剩余现金"], "净值": t["净值"]}
        for t in trades
    ])
    metrics["成交足迹_df"] = trades_df

    if debug:
        if suggestions:
            print("[网格回测] 自动建议：", " ".join(suggestions))
        if grid_trade_count == 0:
            print("[网格回测] 除初始底仓外无网格成交。每日价格相对买卖档位偏差（前 20 日）：")
            debug_df = pd.DataFrame(no_trade_debug)
            if not debug_df.empty:
                for _, row in debug_df.head(20).iterrows():
                    print(f"  {row['日期'].strftime('%Y-%m-%d')} 收盘={row['收盘']} 最低={row['最低']} 最高={row['最高']} "
                          f"买入档={row['买入档价']} 卖出档={row['卖出档价']} "
                          f"最低距买入档%={row['最低距买入档%']} 最高距卖出档%={row['最高距卖出档%']}")
            else:
                print("  (无偏差记录)")
        else:
            print(f"[网格回测] 共 {len(trades)} 笔成交（含初始底仓），最近 {min(UI_TRADE_TOP_N, len(trades))} 笔：")
            for k, t in enumerate(trades[-UI_TRADE_TOP_N:]):
                profit_str = f", 净利润=¥{t['净利润']}" if t.get("净利润") is not None else ""
                print(f"  {t['日期'].strftime('%Y-%m-%d')} {t['方向']} 价={t['成交价']} 手续费=¥{t['手续费']}{profit_str}")

    return daily, metrics, trades
