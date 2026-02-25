# Decision Engine

## 概述

Decision Engine 是四层架构的第四层（最后一层），负责**将系统状态转换为投资组合操作**，**仅基于前序层的输出**。

## 核心原则

- ✅ **只能使用 Signal Engine 的输出**：所有决策都基于 Signal Engine 的状态
- ✅ **只能使用 Risk Engine 的输出**：使用 Risk Engine 的风险评估结果
- ✅ **只能使用 Confidence Engine 的输出**：使用 Confidence Engine 的置信度评估结果
- ❌ **禁止指标计算**：不计算任何技术指标
- ❌ **禁止评分聚合**：不进行任何评分计算
- ❌ **禁止信号重新计算**：不重新计算任何 Signal Engine 已计算的状态

## 决策动作

Decision Engine 输出四种动作：

- **INCREASE** - 增加仓位：信号看多且风险可控
- **HOLD** - 持有：信号中性或需要观望
- **REDUCE** - 减少仓位：信号看空或风险过高
- **WAIT** - 等待：不确定性过高，暂不操作

## 决策逻辑层次结构

Decision Engine 采用三层决策逻辑：

### Layer 1: Signal Direction（信号方向）

基于 Signal Engine 的输出确定基础信号方向。

**输入：** Signal Engine 的 `signal_states`

**输出：**
- `direction`: "BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN"
- `preliminary_action`: "INCREASE" | "HOLD" | "REDUCE" | "WAIT"

**逻辑：**
- 优先使用 Risk Engine 的 `signal_disagreement` 输出判断方向
- 如果 Risk Engine 输出不可用，基于 Signal Engine 的状态进行简单判断
- 如果不确定信号 >= 2 → UNKNOWN → WAIT
- 如果信号一致看多 → BULLISH → INCREASE
- 如果信号一致看空 → BEARISH → REDUCE
- 如果信号分歧 → NEUTRAL → HOLD

### Layer 2: Risk Constraint（风险约束）

基于 Risk Engine 的输出调整初步动作，风险过高时限制操作。

**输入：** Risk Engine 的 `risk_result`

**输出：**
- `adjusted_action`: 调整后的动作
- `reason_tags`: 风险相关的原因标签

**逻辑：**
- **高风险（HIGH）**：
  - INCREASE → HOLD（禁止增加仓位）
  - HOLD → WAIT（转为等待）
- **中等风险（MEDIUM）**：
  - INCREASE → HOLD（降低激进程度）
- **低风险（LOW）**：
  - 不调整动作
- **特殊风险标志**：
  - `signal_conflict` → 强制 WAIT
  - `trend_unknown` → INCREASE 降级为 HOLD

### Layer 3: Confidence Adjustment（置信度调整）

基于 Confidence Engine 的输出调整激进程度。

**输入：** Confidence Engine 的 `confidence_result`

**输出：**
- `final_action`: 最终动作（可能根据置信度进一步调整）
- `aggressiveness`: "LOW" | "MEDIUM" | "HIGH"
- `reason_tags`: 置信度相关的原因标签

**逻辑：**
- confidence = "HIGH" → aggressiveness = "HIGH"
- confidence = "MEDIUM" → aggressiveness = "MEDIUM"
- confidence = "LOW" → aggressiveness = "LOW"
- 如果 confidence = "LOW" 且 action = "INCREASE" → 降级为 HOLD（保守策略）

## 使用方法

### 基本用法

```python
from signal_engine import get_signal_states
from risk_engine import evaluate_risk
from confidence_engine import calculate_confidence
from decision_engine import make_decision

# 1. 获取 Signal Engine 的输出
signal_states = get_signal_states(...)

# 2. 获取 Risk Engine 的输出
risk_result = evaluate_risk(
    signal_states=signal_states,
    history=history
)

# 3. 获取 Confidence Engine 的输出
confidence_result = calculate_confidence(
    signal_states=signal_states,
    risk_result=risk_result,
    market_regime=market_regime
)

# 4. 生成决策（使用所有前序层的输出）
decision = make_decision(
    signal_states=signal_states,  # 来自 Signal Engine
    risk_result=risk_result,  # 来自 Risk Engine
    confidence_result=confidence_result  # 来自 Confidence Engine
)

# 输出示例：
# {
#     "action": "INCREASE",
#     "aggressiveness": "HIGH",
#     "reason_tags": [
#         "bullish_signals",
#         "high_confidence"
#     ]
# }
```

### 单独使用各层

```python
from decision_engine import (
    determine_signal_direction,
    apply_risk_constraint,
    apply_confidence_adjustment,
)

# Layer 1: 信号方向
direction, preliminary_action = determine_signal_direction(signal_states)

# Layer 2: 风险约束
adjusted_action, risk_tags = apply_risk_constraint(
    preliminary_action, risk_result
)

# Layer 3: 置信度调整
final_action, aggressiveness, confidence_tags = apply_confidence_adjustment(
    adjusted_action, confidence_result
)
```

## 输出格式

Decision Engine 的统一输出格式：

```python
{
    "action": "INCREASE" | "HOLD" | "REDUCE" | "WAIT",
    "aggressiveness": "LOW" | "MEDIUM" | "HIGH",
    "reason_tags": [
        "bullish_signals" | "bearish_signals" | "neutral_signals" |
        "high_risk_constraint" | "medium_risk_constraint" |
        "high_confidence" | "low_confidence" | ...
    ]
}
```

## 原因标签

原因标签用于标识决策的具体原因：

### 信号方向标签
- `"bullish_signals"` - 看多信号
- `"bearish_signals"` - 看空信号
- `"neutral_signals"` - 中性信号
- `"uncertain_signals"` - 不确定信号

### 风险约束标签
- `"high_risk_constraint"` - 高风险约束
- `"medium_risk_constraint"` - 中等风险约束
- `"signal_conflict_risk"` - 信号冲突风险
- `"volatility_risk"` - 波动率风险
- `"trend_uncertainty"` - 趋势不确定性
- `"rapid_transitions"` - 快速状态转换

### 置信度标签
- `"high_confidence"` - 高置信度
- `"low_confidence"` - 低置信度
- `"low_confidence_adjustment"` - 低置信度调整

## 决策示例

### 示例 1：看多信号 + 低风险 + 高置信度

```python
signal_states = {
    "trend": "UP",
    "valuation": "CHEAP",
    "momentum": "NEUTRAL",
    "volatility": "LOW"
}
risk_result = {"risk_level": "LOW", ...}
confidence_result = {"confidence": "HIGH", ...}

decision = make_decision(signal_states, risk_result, confidence_result)
# {
#     "action": "INCREASE",
#     "aggressiveness": "HIGH",
#     "reason_tags": ["bullish_signals", "high_confidence"]
# }
```

### 示例 2：看多信号 + 高风险 + 低置信度

```python
signal_states = {
    "trend": "UP",
    "valuation": "FAIR",
    "momentum": "ACCELERATING",
    "volatility": "HIGH"
}
risk_result = {
    "risk_level": "HIGH",
    "risk_flags": ["high_volatility", "signal_conflict"]
}
confidence_result = {"confidence": "LOW", ...}

decision = make_decision(signal_states, risk_result, confidence_result)
# {
#     "action": "WAIT",
#     "aggressiveness": "LOW",
#     "reason_tags": [
#         "bullish_signals",
#         "high_risk_constraint",
#         "signal_conflict_risk",
#         "volatility_risk",
#         "low_confidence"
#     ]
# }
```

### 示例 3：看空信号 + 中等风险 + 中等置信度

```python
signal_states = {
    "trend": "DOWN",
    "valuation": "EXPENSIVE",
    "momentum": "WEAKENING",
    "volatility": "NORMAL"
}
risk_result = {"risk_level": "MEDIUM", ...}
confidence_result = {"confidence": "MEDIUM", ...}

decision = make_decision(signal_states, risk_result, confidence_result)
# {
#     "action": "REDUCE",
#     "aggressiveness": "MEDIUM",
#     "reason_tags": ["bearish_signals", "medium_risk_constraint"]
# }
```

## 架构位置

Decision Engine 是四层架构的第四层（最后一层）：

```
原始数据
    ↓
Signal Engine
    ↓
Risk Engine
    ↓
Confidence Engine
    ↓
Decision Engine ← 当前层
```

## 关键约束

### 禁止重新计算

**错误示例：**
```python
# ❌ 在 Decision Engine 中重新计算 RSI
def make_decision(data):
    rsi = calculate_rsi(data)  # 错误！
    momentum = momentum_state(rsi)  # 错误！
```

**正确示例：**
```python
# ✅ 使用 Signal Engine 的输出
def make_decision(signal_states, risk_result, confidence_result):
    trend = signal_states.get("trend")  # 正确！
    momentum = signal_states.get("momentum")  # 正确！
```

### 禁止评分聚合

**错误示例：**
```python
# ❌ 在 Decision Engine 中进行评分聚合
def make_decision(signal_states):
    score = calculate_total_score(signal_states)  # 错误！
    if score > 7:
        return "INCREASE"
```

**正确示例：**
```python
# ✅ 基于状态直接决策
def make_decision(signal_states, risk_result, confidence_result):
    # 基于状态判断方向，不进行评分
    if signal_states["trend"] == "UP" and signal_states["valuation"] == "CHEAP":
        action = "INCREASE"
```

## 决策规则优先级

1. **风险优先**：高风险时优先保护，限制增加仓位
2. **信号其次**：基于信号方向确定初步动作
3. **置信度最后**：调整激进程度，但不改变基本动作

## 相关文档

- [决策规则详细说明](DECISION_RULES.md)
- [核心架构文档](../docs/CORE_ARCHITECTURE.md)
- [Signal Engine 文档](../signal_engine/README.md)
- [Risk Engine 文档](../risk_engine/README.md)
- [Confidence Engine 文档](../confidence_engine/README.md)
