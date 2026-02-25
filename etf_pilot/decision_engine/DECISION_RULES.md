# Decision Engine - 决策规则层次结构

## 总则

Decision Engine 将系统状态转换为投资组合操作，**仅基于前序层的输出**。

- ✅ 只能使用 Signal Engine 的输出
- ✅ 只能使用 Risk Engine 的输出
- ✅ 只能使用 Confidence Engine 的输出
- ❌ 禁止指标计算
- ❌ 禁止评分聚合
- ❌ 禁止信号重新计算

## 决策动作

Decision Engine 输出四种动作：

- **INCREASE** - 增加仓位：信号看多且风险可控
- **HOLD** - 持有：信号中性或需要观望
- **REDUCE** - 减少仓位：信号看空或风险过高
- **WAIT** - 等待：不确定性过高，暂不操作

## 决策逻辑层次结构

### Layer 1: Signal Direction（信号方向）

**目的：** 基于 Signal Engine 的输出确定基础信号方向。

**输入：**
- Signal Engine 的 `signal_states`
  - `trend`: "UP" | "DOWN" | "SIDEWAYS" | "UNKNOWN"
  - `momentum`: "ACCELERATING" | "WEAKENING" | "NEUTRAL" | "UNKNOWN"
  - `valuation`: "CHEAP" | "FAIR" | "EXPENSIVE" | "UNKNOWN"
  - `volatility`: "LOW" | "NORMAL" | "HIGH" | "UNKNOWN"

**逻辑：**
1. **看多信号（BULLISH）**：
   - trend = "UP" 且 valuation = "CHEAP" 或 "FAIR"
   - 或 trend = "UP" 且 momentum = "ACCELERATING"（在超卖区域）
   - 或 valuation = "CHEAP" 且 volatility = "LOW"

2. **看空信号（BEARISH）**：
   - trend = "DOWN" 且 valuation = "EXPENSIVE"
   - 或 trend = "DOWN" 且 momentum = "WEAKENING"
   - 或 valuation = "EXPENSIVE" 且 volatility = "HIGH"

3. **中性信号（NEUTRAL）**：
   - trend = "SIDEWAYS"
   - 或信号混合（部分看多，部分看空）

4. **不确定信号（UNKNOWN）**：
   - 多个状态为 "UNKNOWN"
   - 或信号严重冲突

**输出：**
- `BULLISH` - 看多
- `BEARISH` - 看空
- `NEUTRAL` - 中性
- `UNKNOWN` - 不确定

**初步动作映射：**
- BULLISH → INCREASE（初步）
- BEARISH → REDUCE（初步）
- NEUTRAL → HOLD（初步）
- UNKNOWN → WAIT（初步）

---

### Layer 2: Risk Constraint（风险约束）

**目的：** 基于 Risk Engine 的输出调整初步动作，风险过高时限制操作。

**输入：**
- Risk Engine 的 `risk_result`
  - `risk_level`: "LOW" | "MEDIUM" | "HIGH"
  - `risk_flags`: ["high_volatility", "trend_unknown", "signal_conflict", "rapid_transitions"]
  - `components`: {volatility_regime, trend_instability, signal_disagreement, rapid_transitions}

**逻辑：**
1. **高风险约束（RISK_HIGH）**：
   - 如果 risk_level = "HIGH"：
     - INCREASE → HOLD（禁止增加仓位）
     - REDUCE → REDUCE（允许减少仓位）
     - HOLD → WAIT（转为等待）
     - WAIT → WAIT（保持等待）

2. **中等风险约束（RISK_MEDIUM）**：
   - 如果 risk_level = "MEDIUM"：
     - INCREASE → HOLD（降低激进程度）
     - REDUCE → REDUCE（保持减少）
     - HOLD → HOLD（保持持有）
     - WAIT → WAIT（保持等待）

3. **低风险约束（RISK_LOW）**：
   - 如果 risk_level = "LOW"：
     - 不调整初步动作（允许执行）

4. **特殊风险标志**：
   - `signal_conflict` → 强制 WAIT（信号冲突，等待）
   - `trend_unknown` → 如果初步动作为 INCREASE，降级为 HOLD
   - `rapid_transitions` → 如果初步动作为 INCREASE，降级为 HOLD

**输出：**
- 调整后的动作（INCREASE | HOLD | REDUCE | WAIT）

---

### Layer 3: Confidence Adjustment（置信度调整）

**目的：** 基于 Confidence Engine 的输出调整激进程度（aggressiveness）。

**输入：**
- Confidence Engine 的 `confidence_result`
  - `confidence`: "LOW" | "MEDIUM" | "HIGH"
  - `confidence_reason`: ["high_signal_agreement", "low_signal_agreement", ...]

**逻辑：**
1. **激进程度映射**：
   - confidence = "HIGH" → aggressiveness = "HIGH"
   - confidence = "MEDIUM" → aggressiveness = "MEDIUM"
   - confidence = "LOW" → aggressiveness = "LOW"

2. **动作调整（可选）**：
   - 如果 confidence = "LOW" 且 action = "INCREASE"：
     - 可以考虑降级为 HOLD（低置信度时更保守）
   - 如果 confidence = "LOW" 且 action = "REDUCE"：
     - 保持 REDUCE（风险控制优先）

**输出：**
- 最终动作（INCREASE | HOLD | REDUCE | WAIT）
- 激进程度（LOW | MEDIUM | HIGH）

---

## 决策流程

```
1. Signal Engine 输出
   ↓
2. Layer 1: Signal Direction
   确定初步动作（BULLISH → INCREASE, BEARISH → REDUCE, ...）
   ↓
3. Risk Engine 输出
   ↓
4. Layer 2: Risk Constraint
   根据风险等级调整动作（HIGH 风险 → 限制操作）
   ↓
5. Confidence Engine 输出
   ↓
6. Layer 3: Confidence Adjustment
   确定激进程度（HIGH confidence → HIGH aggressiveness）
   ↓
7. 最终输出
   {
       "action": "INCREASE" | "HOLD" | "REDUCE" | "WAIT",
       "aggressiveness": "LOW" | "MEDIUM" | "HIGH",
       "reason_tags": [...]
   }
```

---

## 原因标签（Reason Tags）

原因标签用于标识决策的具体原因：

### 信号方向标签
- `"bullish_signals"` - 看多信号
- `"bearish_signals"` - 看空信号
- `"neutral_signals"` - 中性信号
- `"conflicting_signals"` - 信号冲突

### 风险约束标签
- `"high_risk_constraint"` - 高风险约束
- `"medium_risk_constraint"` - 中等风险约束
- `"signal_conflict_risk"` - 信号冲突风险
- `"volatility_risk"` - 波动率风险
- `"trend_uncertainty"` - 趋势不确定性

### 置信度标签
- `"high_confidence"` - 高置信度
- `"low_confidence"` - 低置信度
- `"uncertain_signals"` - 信号不确定

---

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

---

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

---

## 决策规则优先级

1. **风险优先**：高风险时优先保护，限制增加仓位
2. **信号其次**：基于信号方向确定初步动作
3. **置信度最后**：调整激进程度，但不改变基本动作

---

## 示例决策流程

### 示例 1：看多信号 + 低风险 + 高置信度

```
Signal: trend=UP, valuation=CHEAP, momentum=NEUTRAL
  → Layer 1: BULLISH → INCREASE（初步）

Risk: risk_level=LOW
  → Layer 2: 不调整 → INCREASE

Confidence: confidence=HIGH
  → Layer 3: aggressiveness=HIGH

最终输出:
{
    "action": "INCREASE",
    "aggressiveness": "HIGH",
    "reason_tags": ["bullish_signals", "high_confidence"]
}
```

### 示例 2：看多信号 + 高风险 + 低置信度

```
Signal: trend=UP, valuation=FAIR, momentum=ACCELERATING
  → Layer 1: BULLISH → INCREASE（初步）

Risk: risk_level=HIGH, risk_flags=["high_volatility", "signal_conflict"]
  → Layer 2: INCREASE → HOLD（高风险约束）

Confidence: confidence=LOW
  → Layer 3: aggressiveness=LOW

最终输出:
{
    "action": "HOLD",
    "aggressiveness": "LOW",
    "reason_tags": ["bullish_signals", "high_risk_constraint", "low_confidence", "signal_conflict_risk"]
}
```

### 示例 3：看空信号 + 中等风险 + 中等置信度

```
Signal: trend=DOWN, valuation=EXPENSIVE, momentum=WEAKENING
  → Layer 1: BEARISH → REDUCE（初步）

Risk: risk_level=MEDIUM
  → Layer 2: 不调整 → REDUCE

Confidence: confidence=MEDIUM
  → Layer 3: aggressiveness=MEDIUM

最终输出:
{
    "action": "REDUCE",
    "aggressiveness": "MEDIUM",
    "reason_tags": ["bearish_signals", "medium_risk_constraint", "medium_confidence"]
}
```

### 示例 4：不确定信号 + 高风险 + 低置信度

```
Signal: trend=UNKNOWN, valuation=UNKNOWN, momentum=UNKNOWN
  → Layer 1: UNKNOWN → WAIT（初步）

Risk: risk_level=HIGH, risk_flags=["trend_unknown", "rapid_transitions"]
  → Layer 2: 不调整 → WAIT

Confidence: confidence=LOW
  → Layer 3: aggressiveness=LOW

最终输出:
{
    "action": "WAIT",
    "aggressiveness": "LOW",
    "reason_tags": ["uncertain_signals", "high_risk_constraint", "low_confidence", "trend_uncertainty"]
}
```
