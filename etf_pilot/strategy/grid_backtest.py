# -*- coding: utf-8 -*-
"""步进式网格做T回测：High/Low 触发、last_op_price 步进、50%底仓、5%一格、真实成本(万一二/最低5元)。"""
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

FIXED_FEE = 5.0
COMMISSION_RATE = 0.0012
FEE_WARN_PCT = 0.20
INITIAL_POSITION_PCT = 0.5
GRID_LEVEL_PCT = 0.05
DEBUG_TRADE_TOP_N = 20
UI_TRADE_TOP_N = 10


def _fee_and_warn(amount: float, fee_rate: float, min_fee: float, debug: bool, side: str, date) -> float:
    fee = max(min_fee, amount * fee_rate)
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
) -> Tuple[pd.DataFrame, dict, List[dict]]:
    """
    步进式网格(Stepping Grid)：
    - last_op_price 初始为回测第一天收盘价；50% 底仓，50% 现金做网格，每格 5%。
    - 买入：当日 Low 触及 last_op_price*(1-grid_step) 则买入一格，并更新 last_op_price=成交价。
    - 卖出：当日 High 触及 last_op_price*(1+grid_step) 则卖出一格，并更新 last_op_price=成交价。
    - 同一天可先买后卖（波动大时同时触发）。
    - 成本 = max(成交额*0.0012, 5)。输出总手续费及占利润百分比。
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

    if len(dates) < 2:
        if debug:
            print("[网格回测] 数据不足，至少需要 2 日。")
        return pd.DataFrame(), {}, []

    close_0 = closes[0]
    if close_0 <= 0:
        return pd.DataFrame(), {}, []

    # 买入持有净值
    hold_nav = initial_cash * (closes / close_0)

    # 初始 50% 底仓：第一天收盘价买入 50% 资金
    cash = float(initial_cash) * (1 - INITIAL_POSITION_PCT)
    invest_0 = float(initial_cash) * INITIAL_POSITION_PCT
    fee_0 = _fee_and_warn(invest_0, fee_rate, min_fee, debug, "初始底仓", dates[0])
    buy_shares_0 = (invest_0 - fee_0) / close_0 if close_0 > 0 else 0
    cash = float(initial_cash) - invest_0  # 实际剩余现金
    shares = buy_shares_0
    unit_cost = close_0 if shares > 0 else 0.0
    last_op_price = float(close_0)
    total_fee_paid = fee_0

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

        total_equity = cash + shares * c
        if total_equity <= 0:
            total_equity = initial_cash

        buy_trigger = last_op_price * (1 - step_pct)
        sell_trigger = last_op_price * (1 + step_pct)

        did_buy = False
        did_sell = False

        # 1) 买入：当日 Low 触及 last_op_price * (1 - grid_step)
        if lo <= buy_trigger:
            invest = total_equity * unit_pct
            invest = min(invest, cash)
            if invest > 0:
                fee = _fee_and_warn(invest, fee_rate, min_fee, debug, "买入", d)
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

        # 2) 卖出：当日 High 触及 last_op_price * (1 + grid_step) 且 有持仓
        if h >= sell_trigger and shares > 0:
            sell_value_target = total_equity * unit_pct
            exec_price = sell_trigger
            sell_shares = min(sell_value_target / exec_price, shares) if exec_price > 0 else 0
            if sell_shares > 0:
                sell_value = sell_shares * exec_price
                fee = _fee_and_warn(sell_value, fee_rate, min_fee, debug, "卖出", d)
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
                    "日期": d,
                    "方向": "卖出",
                    "成交价": round(exec_price, 4),
                    "数量": round(sell_shares, 4),
                    "金额": round(sell_value, 2),
                    "手续费": round(fee, 2),
                    "净利润": round(net_profit, 2),
                    "净值": round(nav_after, 2),
                    "剩余现金": round(cash, 2),
                })

        nav = cash + shares * c
        rows.append({
            "日期": d,
            "持有净值": round(hold_nav[i], 2),
            "网格净值": round(nav, 2),
            "当前成本价": round(unit_cost, 4) if unit_cost > 0 else None,
            "现价": round(c, 4),
        })

        # 无成交时记录当日价格相对买卖档位的偏差（供 Debug）
        if debug and not did_buy and not did_sell:
            # 距买入档：low 需要再跌多少% 才触及 buy_trigger
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
    }

    # 成交足迹 DataFrame（日期、价格、类型、剩余现金）
    trades_df = pd.DataFrame([
        {"日期": t["日期"], "价格": t["成交价"], "类型": t["方向"], "剩余现金": t["剩余现金"], "净值": t["净值"]}
        for t in trades
    ])
    metrics["成交足迹_df"] = trades_df

    if debug:
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
