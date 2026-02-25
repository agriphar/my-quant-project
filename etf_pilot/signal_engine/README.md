# Signal Engine

## 概述

Signal Engine 是四层架构的第一层，负责**描述市场正在做什么**，而非**投资者应该做什么**。

## 核心原则

- ✅ **仅输出市场状态**：描述趋势、动量、估值、波动率的状态
- ❌ **不输出买卖建议**：不提供任何投资决策
- ❌ **不计算评分**：不进行任何聚合评分
- ❌ **不评估风险**：不包含任何风险评估逻辑
- ❌ **不计算置信度**：不包含任何置信度评估

## 信号类别

Signal Engine 输出四个独立的市场状态：

### 1. Trend State（趋势状态）

描述价格的中长期方向性运动。

**状态值：**
- `UP` - 上升趋势
- `DOWN` - 下降趋势
- `SIDEWAYS` - 横盘震荡
- `UNKNOWN` - 数据不足

**计算方法：**
- 基于线性回归的 R² 和斜率
- R² >= 0.4 且 slope > 0 → `UP`
- R² >= 0.4 且 slope < 0 → `DOWN`
- 其他情况 → `SIDEWAYS`

### 2. Momentum State（动量状态）

描述价格短期动能的强弱和方向。

**状态值：**
- `ACCELERATING` - 加速（超卖或超买，可能加速）
- `WEAKENING` - 减弱（动能疲弱）
- `NEUTRAL` - 中性（正常范围）
- `UNKNOWN` - 数据不足

**计算方法：**
- 基于 RSI（相对强弱指标）
- RSI < 30 或 RSI > 70 → `ACCELERATING`
- 30 <= RSI <= 45 或 55 <= RSI <= 70 → `WEAKENING`
- 45 < RSI < 55 → `NEUTRAL`

### 3. Valuation State（估值状态）

描述当前价格相对于历史水平的估值位置。

**状态值：**
- `CHEAP` - 便宜（分位数 <= 25）
- `FAIR` - 合理（25 < 分位数 <= 75）
- `EXPENSIVE` - 昂贵（分位数 > 75）
- `UNKNOWN` - 数据不足

**计算方法：**
- 基于溢价率的 60 日分位数

### 4. Volatility State（波动率状态）

描述价格波动的剧烈程度。

**状态值：**
- `LOW` - 低波动（ATR% <= 1.0）
- `NORMAL` - 正常波动（1.0 < ATR% < 3.0）
- `HIGH` - 高波动（ATR% >= 3.0）
- `UNKNOWN` - 数据不足

**计算方法：**
- 基于 ATR%（平均真实波幅占收盘价的百分比）

## 使用方法

### 基本用法

```python
from signal_engine import get_signal_states

# 准备数据
last_row = {
    "收盘": 1.5,
    "RSI": 45.0,
    "ATR": 0.02
}

# 计算信号状态
signal_states = get_signal_states(
    last_row=last_row,
    r2=0.5,  # 线性回归 R²
    slope=0.001,  # 线性回归斜率
    premium_pctile_60=30.0,  # 溢价率 60 日分位数
    atr_pct=1.33  # ATR 百分比（可选，会自动计算）
)

# 输出示例：
# {
#     "trend": "UP",
#     "momentum": "NEUTRAL",
#     "valuation": "FAIR",
#     "volatility": "NORMAL"
# }
```

### 单独计算某个状态

```python
from signal_engine import trend_state, momentum_state, valuation_state, volatility_state

# 计算趋势状态
trend = trend_state(r2=0.5, slope=0.001)  # 返回 "UP"

# 计算动量状态
momentum = momentum_state(rsi=45.0)  # 返回 "NEUTRAL"

# 计算估值状态
valuation = valuation_state(premium_pctile_60=30.0)  # 返回 "FAIR"

# 计算波动率状态
volatility = volatility_state(atr_pct=1.33)  # 返回 "NORMAL"
```

## 输出格式

Signal Engine 的统一输出格式：

```python
{
    "trend": "UP" | "DOWN" | "SIDEWAYS" | "UNKNOWN",
    "momentum": "ACCELERATING" | "WEAKENING" | "NEUTRAL" | "UNKNOWN",
    "valuation": "CHEAP" | "FAIR" | "EXPENSIVE" | "UNKNOWN",
    "volatility": "LOW" | "NORMAL" | "HIGH" | "UNKNOWN"
}
```

## 状态常量

可以使用状态常量进行比较：

```python
from signal_engine import (
    TREND_UP,
    MOMENTUM_ACCELERATING,
    VALUATION_CHEAP,
    VOLATILITY_LOW,
)

if signal_states["trend"] == TREND_UP:
    print("上升趋势")
```

## 向后兼容

为了保持向后兼容，Signal Engine 仍然导出旧的状态常量（如 `MOMENTUM_OVERSOLD`、`TREND_STRONG_UP` 等），但新代码应使用新的状态值。

## 架构位置

Signal Engine 是四层架构的第一层：

```
原始数据
    ↓
Signal Engine ← 当前层
    ↓
Risk Engine
    ↓
Confidence Engine
    ↓
Decision Engine
```

## 相关文档

- [信号定义详细说明](SIGNAL_DEFINITIONS.md)
- [核心架构文档](../docs/CORE_ARCHITECTURE.md)
