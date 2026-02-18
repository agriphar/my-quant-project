# -*- coding: utf-8 -*-
"""策略用常数（偏离度、补仓步长等）。"""
# 偏离度超过此比例视为“涨太多”，提示不建议追高（与 RSI 无关）
DEVIATION_CHASE_HIGH_PCT = 10.0
# Core 资产在 MA200 之上时，每跌此比例可加仓一次（增加 0.5 倍仓位）
ADDON_DROP_PCT = 5.0
# Core 买入：RSI 低于此值视为“回撤至可买”条件之一
CORE_RSI_PULLBACK = 45
# Core 卖出：价格相对 MA200 乖离率超过此比例（过高）时减仓
CORE_MA200_DEVIATION_SELL_PCT = 15.0
