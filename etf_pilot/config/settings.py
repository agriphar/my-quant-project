# -*- coding: utf-8 -*-
"""ETF 监控工具运行参数与策略默认值。"""

# 均线周期（可在 Sidebar 中覆盖）
MA_SHORT_DEFAULT = 5
MA_LONG_DEFAULT = 20

# RSI 与布林带
RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD = 2.0

# 策略阈值
RSI_OVERBOUGHT = 80   # RSI > 80 提示超买
RSI_BULLISH_MAX = 70  # 看多条件：价格 > MA20 且 RSI < 70
VOL_SHRINK_RATIO = 0.8  # 缩量：当日量 < 近 N 日均量的此比例

# 缓存过期时间（秒），减少 AkShare 请求
CACHE_TTL = 300

# 自动资产分类（classify_etfs）
CLASSIFICATION_VOL_THRESHOLD = 0.25   # 年化波动率 < 25% 且宽基 -> Core
CLASSIFICATION_CACHE_DAYS = 7         # 分类结果缓存天数
CLASSIFICATION_LOOKBACK_YEARS = 3     # 使用过去 N 年日线计算波动率/回撤

# 回测默认参数
BACKTEST_INITIAL_CASH = 100_000
BACKTEST_FEE_RATE = 0.0012            # 单边 0.12%（佣金+滑点）
BACKTEST_MIN_FEE = 5.0                 # 单笔最低 5 元
BACKTEST_YEARS = 3

# 多因子分类轮动策略 (RSR) 参数
RSR_INITIAL_CASH = 500_000            # 50 万，降低最低佣金影响
RSR_FEE_RATE = 0.0005                 # 万五
RSR_MIN_FEE = 0.0                     # 暂设为 0
RSR_TOP_N = 3                         # 总持仓不超过 3 只，每组最多 1 只
RSR_SELL_BELOW_RANK = 8               # 排名跌破第 8 名则卖出换仓
RSR_ATR_MULT = 2.0                    # 吊灯止损：持仓期最高价 - ATR_MULT * ATR
RSR_ATR_PERIOD = 14
RSR_LOOKBACK = 20                     # 排名用 20 日涨幅/20日标准差（动量效率）
RSR_REBALANCE_FREQ = "weekly_friday"  # 每周五收盘前调仓
RSR_GLOBAL_MA20_THRESHOLD = 0.4      # 全市场 MA20 之上比例 < 40% 则强制空仓

# 跨资产等权动态再平衡策略
EW_INITIAL_CASH = 500_000             # 50 万，五只各 20%
EW_FEE_RATE = 0.0005                  # 佣金万五
EW_MIN_FEE = 0.0                      # 暂不设最低 5 元
EW_TARGET_WEIGHT = 0.2                # 目标权重 20%
EW_DEVIATION_THRESHOLD = 0.03         # 偏离正负 3% 触发再平衡
EW_REBALANCE_TRADING_DAYS = 10        # 每 10 个交易日检查一次（约两周一检）；可改为 21 近似每月
