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

# 策略用（如 signals 网格档位）
GRID_STEP_PCT = 0.012                 # 每 1.2% 一档

# 数据源：em=东方财富（默认），sina=新浪（可避免东方财富网络/代理问题）
DATA_SOURCE = "sina"


def to_sina_symbol(code: str) -> str:
    """将 6 位 ETF 代码转为新浪格式：上交所 sh（51/52/56/58 等），深交所 sz（15/16/159 等）。"""
    c = str(code).strip()
    if len(c) > 6 and c.upper().startswith(("SH", "SZ")):
        return ("sh" if c.upper().startswith("SH") else "sz") + c[-6:]
    if len(c) >= 6 and c[:2] in ("51", "52", "56", "58"):
        return "sh" + c[:6]
    return "sz" + c[:6]

# 东方财富接口易因短时大量请求断开连接，请求间隔（秒）与重试次数
REQUEST_DELAY_SECONDS = 0.6
REQUEST_RETRIES = 3
REQUEST_RETRY_DELAY_SECONDS = 1.5
