# Risk Engine

## 概述

Risk Engine 是四层架构的第二层，负责**评估交易风险条件**，**仅基于 Signal Engine 的输出**。

## 核心原则

- ✅ **只能使用 Signal Engine 的输出**：所有风险评估都基于 Signal Engine 的状态
- ❌ **禁止使用价格指标**：不使用价格、收益率等原始数据
- ❌ **禁止使用技术指标**：不使用 RSI、MA、ATR 等原始指标
- ❌ **禁止重新计算信号**：不重新计算 Signal Engine 已计算的状态
- ❌ **禁止使用评分系统**：不进行任何评分计算

## 风险维度

Risk Engine 评估四个独立的风险维度：

### 1. Volatility Regime（波动率制度）

基于 Signal Engine 的 `volatility` 状态评估波动率风险。

- `LOW` - 低波动风险（volatility = "LOW"）
- `MEDIUM` - 中等波动风险（volatility = "NORMAL" 或 "UNKNOWN"）
- `HIGH` - 高波动风险（volatility = "HIGH"）

### 2. Trend Instability（趋势不稳定性）

基于 Signal Engine 的 `trend` 状态评估趋势稳定性。

- `LOW` - 趋势稳定（trend = "UP" 或 "DOWN"）
- `MEDIUM` - 趋势不稳定（trend = "SIDEWAYS"）
- `HIGH` - 趋势极不稳定（trend = "UNKNOWN"）

### 3. Signal Disagreement（信号分歧）

评估多个信号状态之间的一致性。

- `LOW` - 信号一致（3-4 个信号一致）
- `MEDIUM` - 信号部分分歧（2-2 或 1-3 分布）
- `HIGH` - 信号严重分歧（2-2 且方向相反）

### 4. Rapid State Transitions（快速状态转换）

评估信号状态的快速变化（需要历史状态序列）。

- `LOW` - 状态稳定（过去 N 天内变化次数 <= 1）
- `MEDIUM` - 状态不稳定（过去 N 天内变化次数 2-3）
- `HIGH` - 状态极不稳定（过去 N 天内变化次数 >= 4）

## 使用方法

### 基本用法

```python
from signal_engine import get_signal_states
from risk_engine import evaluate_risk

# 1. 首先获取 Signal Engine 的输出
signal_states = get_signal_states(
    last_row={"收盘": 1.5, "RSI": 45.0, "ATR": 0.02},
    r2=0.5,
    slope=0.001,
    premium_pctile_60=30.0,
    atr_pct=1.33
)

# 2. 使用 Signal Engine 的输出评估风险
risk_result = evaluate_risk(
    signal_states=signal_states,
    history=None,  # 可选：历史状态序列
    lookback_days=5  # 可选：历史窗口天数
)

# 输出示例：
# {
#     "risk_level": "MEDIUM",
#     "risk_flags": ["high_volatility"],
#     "components": {
#         "volatility_regime": "HIGH",
#         "trend_instability": "LOW",
#         "signal_disagreement": "LOW",
#         "rapid_transitions": "LOW"
#     }
# }
```

### 使用历史状态评估快速转换风险

```python
from signal_engine import get_signal_states
from risk_engine import evaluate_risk

# 准备历史状态序列（按时间顺序，最新的在最后）
history = [
    {"trend": "UP", "momentum": "NEUTRAL", "valuation": "FAIR", "volatility": "LOW"},
    {"trend": "UP", "momentum": "NEUTRAL", "valuation": "FAIR", "volatility": "NORMAL"},
    {"trend": "SIDEWAYS", "momentum": "WEAKENING", "valuation": "FAIR", "volatility": "HIGH"},
]

# 当前状态
current_states = get_signal_states(...)

# 评估风险（包含快速转换风险）
risk_result = evaluate_risk(
    signal_states=current_states,
    history=history,
    lookback_days=5
)
```

### 单独评估某个风险维度

```python
from risk_engine import (
    volatility_regime_risk,
    trend_instability_risk,
    signal_disagreement_risk,
    rapid_transitions_risk,
)

# 波动率制度风险
vol_risk = volatility_regime_risk(signal_states.get("volatility"))

# 趋势不稳定性风险
trend_risk = trend_instability_risk(signal_states.get("trend"))

# 信号分歧风险
disagreement_risk = signal_disagreement_risk(signal_states)

# 快速状态转换风险
transitions_risk = rapid_transitions_risk(
    current_states=signal_states,
    history=history
)
```

## 输出格式

Risk Engine 的统一输出格式：

```python
{
    "risk_level": "LOW" | "MEDIUM" | "HIGH",
    "risk_flags": [
        "high_volatility" | "trend_unknown" | 
        "signal_conflict" | "rapid_transitions"
    ],
    "components": {
        "volatility_regime": "LOW" | "MEDIUM" | "HIGH",
        "trend_instability": "LOW" | "MEDIUM" | "HIGH",
        "signal_disagreement": "LOW" | "MEDIUM" | "HIGH",
        "rapid_transitions": "LOW" | "MEDIUM" | "HIGH"
    }
}
```

## 风险等级聚合规则

将四个维度的风险等级聚合为单一风险等级：

1. **任一维度为 HIGH** → 整体风险为 `HIGH`
2. **两个或以上维度为 MEDIUM** → 整体风险为 `MEDIUM`
3. **所有维度均为 LOW** → 整体风险为 `LOW`
4. **其他情况** → 整体风险为 `MEDIUM`

## 风险标志

风险标志用于标识具体的风险来源：

- `"high_volatility"` - 高波动率风险（volatility_regime = HIGH）
- `"trend_unknown"` - 趋势无法判断（trend_instability = HIGH）
- `"signal_conflict"` - 信号严重分歧（signal_disagreement = HIGH）
- `"rapid_transitions"` - 状态快速转换（rapid_transitions = HIGH）

## 架构位置

Risk Engine 是四层架构的第二层：

```
原始数据
    ↓
Signal Engine
    ↓
Risk Engine ← 当前层
    ↓
Confidence Engine
    ↓
Decision Engine
```

## 关键约束

### 禁止使用原始数据

**错误示例：**
```python
# ❌ 在 Risk Engine 中使用原始数据
def evaluate_risk(atr_pct, rsi, ...):
    if atr_pct > 3.0:  # 错误！
        return "HIGH"
```

**正确示例：**
```python
# ✅ 使用 Signal Engine 的输出
def evaluate_risk(signal_states):
    volatility = signal_states.get("volatility")
    if volatility == "HIGH":  # 正确！
        return "HIGH"
```

### 禁止重新计算信号

**错误示例：**
```python
# ❌ 在 Risk Engine 中重新计算 RSI
def evaluate_risk(data):
    rsi = calculate_rsi(data)  # 错误！
    momentum = momentum_state(rsi)  # 错误！
```

**正确示例：**
```python
# ✅ 使用 Signal Engine 的输出
def evaluate_risk(signal_states):
    momentum = signal_states.get("momentum")  # 正确！
```

## 相关文档

- [风险定义详细说明](RISK_DEFINITIONS.md)
- [核心架构文档](../docs/CORE_ARCHITECTURE.md)
- [Signal Engine 文档](../signal_engine/README.md)
