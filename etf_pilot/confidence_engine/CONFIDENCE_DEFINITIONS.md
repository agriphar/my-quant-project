# Confidence Engine - 置信度定义

## 总则

Confidence Engine 评估当前信号的可靠性，**仅基于 Signal Engine 和 Risk Engine 的输出**。

- ✅ 只能使用 Signal Engine 的输出
- ✅ 只能使用 Risk Engine 的输出
- ❌ 禁止使用价格数据（价格、收益率等）
- ❌ 禁止使用技术指标（RSI、MA、ATR 等）
- ❌ 禁止重用评分系统
- ❌ 禁止包含决策逻辑

**重要：置信度不能直接与信号方向相关。** 置信度评估的是信号的可靠性，而不是信号的方向（看多或看空）。

## 置信度维度

### 1. Signal Agreement Level（信号一致性水平）

**定义：** 评估多个信号状态之间的一致性程度，一致性越高，置信度越高。

**置信度等级：**
- `HIGH` - 高一致性：信号分歧风险为 LOW（3-4 个信号一致）
- `MEDIUM` - 中等一致性：信号分歧风险为 MEDIUM（部分分歧）
- `LOW` - 低一致性：信号分歧风险为 HIGH（严重分歧）

**逻辑：**
- 使用 Risk Engine 的 `signal_disagreement` 输出
- 低分歧（高一致性）→ 高置信度
- 高分歧（低一致性）→ 低置信度

**输入：**
- Risk Engine 的 `risk_result["components"]["signal_disagreement"]`

**输出：** `"LOW" | "MEDIUM" | "HIGH"`

---

### 2. Regime Stability（制度稳定性）

**定义：** 评估市场制度的稳定性，稳定性越高，置信度越高。

**置信度等级：**
- `HIGH` - 制度稳定：市场制度明确且稳定
- `MEDIUM` - 制度中等稳定：市场制度部分明确
- `LOW` - 制度不稳定：市场制度不明确或频繁变化

**逻辑：**
- 基于市场制度信息（market_regime）的稳定性指标
- 如果 market_regime 包含 "confidence" 字段，直接使用
- 如果 market_regime 包含 "risk_regime" 字段，评估其稳定性
- 如果没有 market_regime 信息，视为中等稳定性

**输入：**
- `market_regime` 字典（可选，外部输入）
  - `market_regime.get("confidence")` - 制度置信度
  - `market_regime.get("risk_regime")` - 风险制度（risk_on/risk_off）

**输出：** `"LOW" | "MEDIUM" | "HIGH"`

---

### 3. Persistence of Signal States（信号状态的持续性）

**定义：** 评估信号状态的持续性，状态越稳定，置信度越高。

**置信度等级：**
- `HIGH` - 状态持续：过去 N 天内状态变化次数 <= 1
- `MEDIUM` - 状态中等持续：过去 N 天内状态变化次数 2-3
- `LOW` - 状态不持续：过去 N 天内状态变化次数 >= 4

**逻辑：**
- 需要 Signal Engine 的历史状态序列
- 统计每个信号因子（trend, momentum, valuation, volatility）的状态变化次数
- 取所有信号因子中变化次数的最大值
- 如果任一信号状态频繁变化，置信度降低

**输入：**
- Signal Engine 的当前 `signal_states`
- Signal Engine 的历史 `signal_states` 序列（过去 N 天，默认 5 天）

**输出：** `"LOW" | "MEDIUM" | "HIGH"`

---

### 4. Conflict Between Valuation and Trend（估值与趋势的冲突）

**定义：** 评估估值状态和趋势状态之间的冲突，冲突越大，置信度越低。

**置信度等级：**
- `HIGH` - 无冲突：估值和趋势方向一致
- `MEDIUM` - 部分冲突：估值和趋势方向部分一致
- `LOW` - 严重冲突：估值和趋势方向相反

**逻辑：**
- 基于 Signal Engine 的 `trend` 和 `valuation` 状态
- **偏多组合**：
  - trend = "UP" 且 valuation = "CHEAP" 或 "FAIR" → HIGH（一致看多）
  - trend = "UP" 且 valuation = "EXPENSIVE" → MEDIUM（趋势看多但估值高）
- **偏空组合**：
  - trend = "DOWN" 且 valuation = "EXPENSIVE" → HIGH（一致看空）
  - trend = "DOWN" 且 valuation = "CHEAP" 或 "FAIR" → MEDIUM（趋势看空但估值低）
- **冲突组合**：
  - trend = "UP" 且 valuation = "EXPENSIVE" → MEDIUM（趋势看多但估值高，部分冲突）
  - trend = "DOWN" 且 valuation = "CHEAP" → MEDIUM（趋势看空但估值低，部分冲突）
- **不确定组合**：
  - trend = "SIDEWAYS" 或 "UNKNOWN" → MEDIUM（无法判断）
  - valuation = "UNKNOWN" → MEDIUM（无法判断）

**输入：**
- Signal Engine 的 `signal_states["trend"]`
- Signal Engine 的 `signal_states["valuation"]`

**输出：** `"LOW" | "MEDIUM" | "HIGH"`

---

## 综合置信度评估

### 置信度等级聚合规则

将四个维度的置信度等级聚合为单一置信度等级：

1. **所有维度均为 HIGH** → 整体置信度为 `HIGH`
2. **任一维度为 LOW** → 降级
   - 若只有一个 LOW 且其他都是 HIGH → `MEDIUM`（轻微降级）
   - 否则 → `LOW`（严重降级）
3. **最差维度为 MEDIUM** → 整体置信度为 `MEDIUM`

### 置信度原因（Confidence Reasons）

置信度原因用于标识具体的置信度来源：

- `"high_signal_agreement"` - 信号高度一致
- `"low_signal_agreement"` - 信号严重分歧
- `"stable_regime"` - 制度稳定
- `"unstable_regime"` - 制度不稳定
- `"persistent_signals"` - 信号状态持续
- `"volatile_signals"` - 信号状态频繁变化
- `"valuation_trend_aligned"` - 估值与趋势一致
- `"valuation_trend_conflict"` - 估值与趋势冲突

---

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

---

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

---

## 数据流

```
Signal Engine 输出
    ↓
{
    "trend": "UP",
    "momentum": "NEUTRAL",
    "valuation": "FAIR",
    "volatility": "HIGH"
}
    ↓
Risk Engine 评估
    ↓
{
    "risk_level": "MEDIUM",
    "components": {
        "signal_disagreement": "LOW",
        ...
    }
}
    ↓
Confidence Engine 评估
    ↓
{
    "confidence": "HIGH",
    "confidence_reason": [
        "high_signal_agreement",
        "valuation_trend_aligned"
    ]
}
```
