# Confidence Engine

## 概述

Confidence Engine 是四层架构的第三层，负责**评估当前信号的可靠性**，**仅基于 Signal Engine 和 Risk Engine 的输出**。

## 核心原则

- ✅ **只能使用 Signal Engine 的输出**：所有置信度评估都基于 Signal Engine 的状态
- ✅ **只能使用 Risk Engine 的输出**：使用 Risk Engine 的风险评估结果
- ❌ **禁止使用价格数据**：不使用价格、收益率等原始数据
- ❌ **禁止使用技术指标**：不使用 RSI、MA、ATR 等原始指标
- ❌ **禁止重用评分系统**：不进行任何评分计算
- ❌ **禁止包含决策逻辑**：不提供任何买卖建议

**重要：置信度不能直接与信号方向相关。** 置信度评估的是信号的可靠性，而不是信号的方向（看多或看空）。

## 置信度维度

Confidence Engine 评估四个独立的置信度维度：

### 1. Signal Agreement Level（信号一致性水平）

基于 Risk Engine 的信号分歧风险评估信号一致性。

- `HIGH` - 高一致性（信号分歧风险为 LOW，3-4 个信号一致）
- `MEDIUM` - 中等一致性（信号分歧风险为 MEDIUM，部分分歧）
- `LOW` - 低一致性（信号分歧风险为 HIGH，严重分歧）

### 2. Regime Stability（制度稳定性）

基于市场制度信息评估制度稳定性。

- `HIGH` - 制度稳定（制度明确且稳定）
- `MEDIUM` - 制度中等稳定（制度部分明确）
- `LOW` - 制度不稳定（制度不明确或频繁变化）

### 3. Persistence of Signal States（信号状态的持续性）

评估信号状态的持续性，**使用 Risk Engine 的 rapid_transitions 输出**。

- `HIGH` - 状态持续（Risk Engine: rapid_transitions = LOW）
- `MEDIUM` - 状态中等持续（Risk Engine: rapid_transitions = MEDIUM）
- `LOW` - 状态不持续（Risk Engine: rapid_transitions = HIGH）

**重要：** 此维度现在使用 Risk Engine 的输出，不再重新计算，符合架构原则。

### 4. Conflict Between Valuation and Trend（估值与趋势的冲突）

评估估值状态和趋势状态之间的冲突。

- `HIGH` - 无冲突（估值和趋势方向一致）
- `MEDIUM` - 部分冲突（估值和趋势方向部分一致或不确定）
- `LOW` - 严重冲突（估值和趋势方向相反）

## 使用方法

### 基本用法

```python
from signal_engine import get_signal_states
from risk_engine import evaluate_risk
from confidence_engine import calculate_confidence

# 1. 获取 Signal Engine 的输出
signal_states = get_signal_states(
    last_row={"收盘": 1.5, "RSI": 45.0, "ATR": 0.02},
    r2=0.5,
    slope=0.001,
    premium_pctile_60=30.0,
    atr_pct=1.33
)

# 2. 获取 Risk Engine 的输出
risk_result = evaluate_risk(
    signal_states=signal_states,
    history=None,
    lookback_days=5
)

# 3. 计算置信度（使用 Signal Engine 和 Risk Engine 的输出）
confidence_result = calculate_confidence(
    signal_states=signal_states,  # 来自 Signal Engine
    risk_result=risk_result,  # 来自 Risk Engine（必需，用于获取 signal_disagreement 和 rapid_transitions）
    market_regime={"confidence": "high"},  # 可选：市场制度信息
)

# 输出示例：
# {
#     "confidence": "HIGH",
#     "confidence_reason": [
#         "high_signal_agreement",
#         "stable_regime",
#         "persistent_signals",
#         "valuation_trend_aligned"
#     ]
# }
```

### 使用历史状态评估持续性

```python
from signal_engine import get_signal_states
from risk_engine import evaluate_risk
from confidence_engine import calculate_confidence

# 准备历史状态序列（按时间顺序，最新的在最后）
history = [
    {"trend": "UP", "momentum": "NEUTRAL", "valuation": "FAIR", "volatility": "LOW"},
    {"trend": "UP", "momentum": "NEUTRAL", "valuation": "FAIR", "volatility": "NORMAL"},
    {"trend": "UP", "momentum": "NEUTRAL", "valuation": "FAIR", "volatility": "NORMAL"},
]

# 当前状态
current_states = get_signal_states(...)

# 风险评估
risk_result = evaluate_risk(
    signal_states=current_states,
    history=history
)

# 置信度评估（包含持续性评估，使用 Risk Engine 的 rapid_transitions 输出）
confidence_result = calculate_confidence(
    signal_states=current_states,
    risk_result=risk_result,  # 必需：包含 rapid_transitions 输出
    market_regime={"confidence": "high"},
)
```

### 单独评估某个置信度维度

```python
from confidence_engine import (
    signal_agreement_confidence,
    regime_stability_confidence,
    signal_persistence_confidence,
    valuation_trend_conflict_confidence,
)

# 信号一致性置信度
agreement_conf = signal_agreement_confidence(
    signal_disagreement_risk="LOW"  # 来自 Risk Engine
)

# 制度稳定性置信度
regime_conf = regime_stability_confidence(
    market_regime={"confidence": "high"}
)

# 信号持续性置信度（已废弃，现在使用 Risk Engine 的输出）
# ⚠️ 已废弃：不再使用此函数
# persistence_conf = signal_persistence_confidence(...)

# ✅ 正确方式：使用 Risk Engine 的 rapid_transitions 输出
rapid_transitions_risk = risk_result["components"].get("rapid_transitions")
# 通过内部函数转换为置信度等级（LOW 风险 → HIGH 置信度）

# 估值趋势冲突置信度
conflict_conf = valuation_trend_conflict_confidence(
    trend_state=signal_states.get("trend"),
    valuation_state=signal_states.get("valuation")
)
```

## 输出格式

Confidence Engine 的统一输出格式：

```python
{
    "confidence": "LOW" | "MEDIUM" | "HIGH",
    "confidence_reason": [
        "high_signal_agreement" | "low_signal_agreement" |
        "stable_regime" | "unstable_regime" |
        "persistent_signals" | "volatile_signals" |
        "valuation_trend_aligned" | "valuation_trend_conflict"
    ]
}
```

## 置信度等级聚合规则

将四个维度的置信度等级聚合为单一置信度等级：

1. **所有维度均为 HIGH** → 整体置信度为 `HIGH`
2. **任一维度为 LOW** → 降级
   - 若只有一个 LOW 且其他都是 HIGH → `MEDIUM`（轻微降级）
   - 否则 → `LOW`（严重降级）
3. **最差维度为 MEDIUM** → 整体置信度为 `MEDIUM`

## 置信度原因

置信度原因用于标识具体的置信度来源：

- `"high_signal_agreement"` - 信号高度一致
- `"low_signal_agreement"` - 信号严重分歧
- `"stable_regime"` - 制度稳定
- `"unstable_regime"` - 制度不稳定
- `"persistent_signals"` - 信号状态持续
- `"volatile_signals"` - 信号状态频繁变化
- `"valuation_trend_aligned"` - 估值与趋势一致
- `"valuation_trend_conflict"` - 估值与趋势冲突

## 架构位置

Confidence Engine 是四层架构的第三层：

```
原始数据
    ↓
Signal Engine
    ↓
Risk Engine
    ↓
Confidence Engine ← 当前层
    ↓
Decision Engine
```

## 关键约束

### 禁止使用原始数据

**错误示例：**
```python
# ❌ 在 Confidence Engine 中使用原始数据
def calculate_confidence(atr_pct, rsi, ...):
    if atr_pct > 3.0:  # 错误！应该使用 Risk Engine 的输出
        return "LOW"
```

**正确示例：**
```python
# ✅ 使用 Risk Engine 的输出
def calculate_confidence(signal_states, risk_result):
    volatility_risk = risk_result["components"]["volatility_regime"]
    if volatility_risk == "HIGH":  # 正确！
        return "LOW"
```

### 禁止重新计算信号

**错误示例：**
```python
# ❌ 在 Confidence Engine 中重新计算信号
def calculate_confidence(data):
    rsi = calculate_rsi(data)  # 错误！
    momentum = momentum_state(rsi)  # 错误！
```

**正确示例：**
```python
# ✅ 使用 Signal Engine 的输出
def calculate_confidence(signal_states, risk_result):
    momentum = signal_states.get("momentum")  # 正确！
```

### 置信度与信号方向无关

**重要：** 置信度评估的是信号的可靠性，而不是信号的方向。

- ✅ 高置信度可以出现在看多或看空信号中
- ✅ 低置信度可以出现在看多或看空信号中
- ❌ 不能因为信号看多就提高置信度
- ❌ 不能因为信号看空就降低置信度

**示例：**
```python
# 看多信号，高置信度
signal_states = {"trend": "UP", "valuation": "CHEAP", ...}
confidence = "HIGH"  # ✅ 正确：信号一致，高置信度

# 看空信号，高置信度
signal_states = {"trend": "DOWN", "valuation": "EXPENSIVE", ...}
confidence = "HIGH"  # ✅ 正确：信号一致，高置信度

# 看多信号，低置信度
signal_states = {"trend": "UP", "valuation": "EXPENSIVE", ...}
confidence = "MEDIUM"  # ✅ 正确：信号冲突，置信度降低
```

## 相关文档

- [置信度定义详细说明](CONFIDENCE_DEFINITIONS.md)
- [核心架构文档](../docs/CORE_ARCHITECTURE.md)
- [Signal Engine 文档](../signal_engine/README.md)
- [Risk Engine 文档](../risk_engine/README.md)
