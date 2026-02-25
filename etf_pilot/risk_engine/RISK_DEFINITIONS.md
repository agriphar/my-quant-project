# Risk Engine - 风险定义

## 总则

Risk Engine 评估交易风险条件，**仅基于 Signal Engine 的输出**。

- ✅ 只能使用 Signal Engine 的输出
- ❌ 禁止使用价格指标（价格、收益率等）
- ❌ 禁止使用技术指标（RSI、MA、ATR 等）
- ❌ 禁止重新计算信号
- ❌ 禁止使用评分系统

## 风险维度

### 1. Volatility Regime（波动率制度）

**定义：** 基于 Signal Engine 的 `volatility` 状态评估波动率风险。

**风险等级：**
- `LOW` - 低波动风险：volatility = "LOW"
- `MEDIUM` - 中等波动风险：volatility = "NORMAL" 或 "UNKNOWN"
- `HIGH` - 高波动风险：volatility = "HIGH"

**逻辑：**
- Signal Engine 的 `volatility` 状态直接映射到风险等级
- 高波动环境意味着更高的交易风险

**输入：**
- Signal Engine 的 `signal_states["volatility"]`

**输出：** `"LOW" | "MEDIUM" | "HIGH"`

---

### 2. Trend Instability（趋势不稳定性）

**定义：** 评估趋势的稳定性，基于 Signal Engine 的 `trend` 状态及其历史变化。

**风险等级：**
- `LOW` - 趋势稳定：trend = "UP" 或 "DOWN"（明确趋势）
- `MEDIUM` - 趋势不稳定：trend = "SIDEWAYS"（横盘震荡）
- `HIGH` - 趋势极不稳定：trend = "UNKNOWN"（无法判断趋势）

**逻辑：**
- 明确的趋势（UP/DOWN）意味着较低的风险（方向明确）
- 横盘震荡（SIDEWAYS）意味着中等风险（方向不明确）
- 无法判断趋势（UNKNOWN）意味着高风险（完全不确定）

**输入：**
- Signal Engine 的 `signal_states["trend"]`
- 可选：历史 trend 状态序列（用于检测趋势变化）

**输出：** `"LOW" | "MEDIUM" | "HIGH"`

---

### 3. Signal Disagreement（信号分歧）

**定义：** 评估多个信号状态之间的一致性，信号分歧越大风险越高。

**风险等级：**
- `LOW` - 信号一致：多个信号指向同一方向（3-4 个信号一致）
- `MEDIUM` - 信号部分分歧：信号方向混合（2-2 或 1-3 分布）
- `HIGH` - 信号严重分歧：信号严重冲突（2-2 且方向相反）

**逻辑：**
- 统计四个信号（trend, momentum, valuation, volatility）的"偏多"和"偏空"数量
- 4-0 或 3-1 一致 → LOW（方向明确）
- 2-2 分歧 → HIGH（严重冲突）
- 1-3 或 0-4 一致但偏空 → MEDIUM（方向一致但不利）

**信号方向判断：**
- **偏多（Bullish）**：
  - trend: "UP"
  - momentum: "ACCELERATING"（在超卖区域）或 "NEUTRAL"
  - valuation: "CHEAP" 或 "FAIR"
  - volatility: "LOW" 或 "NORMAL"
- **偏空（Bearish）**：
  - trend: "DOWN"
  - momentum: "ACCELERATING"（在超买区域）或 "WEAKENING"
  - valuation: "EXPENSIVE"
  - volatility: "HIGH"

**输入：**
- Signal Engine 的完整 `signal_states` 字典

**输出：** `"LOW" | "MEDIUM" | "HIGH"`

---

### 4. Rapid State Transitions（快速状态转换）

**定义：** 评估信号状态的快速变化，频繁的状态转换意味着高风险。

**风险等级：**
- `LOW` - 状态稳定：状态变化频率低（过去 N 天内变化次数 <= 1）
- `MEDIUM` - 状态不稳定：状态变化频率中等（过去 N 天内变化次数 2-3）
- `HIGH` - 状态极不稳定：状态变化频率高（过去 N 天内变化次数 >= 4）

**逻辑：**
- 需要历史状态序列（过去 N 天的 signal_states）
- 统计每个信号状态的变化次数
- 如果任一信号状态频繁变化，风险升高

**输入：**
- Signal Engine 的当前 `signal_states`
- 历史 `signal_states` 序列（过去 N 天，默认 5 天）

**输出：** `"LOW" | "MEDIUM" | "HIGH"`

---

## 综合风险评估

### 风险等级聚合规则

将四个维度的风险等级聚合为单一风险等级：

1. **任一维度为 HIGH** → 整体风险为 `HIGH`
2. **两个或以上维度为 MEDIUM** → 整体风险为 `MEDIUM`
3. **所有维度均为 LOW** → 整体风险为 `LOW`
4. **其他情况** → 整体风险为 `MEDIUM`

### 风险标志（Risk Flags）

风险标志用于标识具体的风险来源：

- `"high_volatility"` - 高波动率风险
- `"trend_unknown"` - 趋势无法判断
- `"signal_conflict"` - 信号严重分歧
- `"rapid_transitions"` - 状态快速转换

---

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

---

## 关键约束

### 禁止使用原始数据

**错误示例：**
```python
# ❌ 在 Risk Engine 中使用原始数据
def evaluate_risk(atr_pct, rsi, ...):
    if atr_pct > 3.0:  # 错误！应该使用 Signal Engine 的 volatility 状态
        return "HIGH"
```

**正确示例：**
```python
# ✅ 使用 Signal Engine 的输出
def evaluate_risk(signal_states):
    volatility = signal_states.get("volatility")
    if volatility == "HIGH":  # 使用 Signal Engine 的状态
        return "HIGH"
```

### 禁止重新计算信号

**错误示例：**
```python
# ❌ 在 Risk Engine 中重新计算 RSI
def evaluate_risk(data):
    rsi = calculate_rsi(data)  # 错误！Signal Engine 已经计算过
    momentum = momentum_state(rsi)  # 错误！应该使用 signal_states["momentum"]
```

**正确示例：**
```python
# ✅ 使用 Signal Engine 的输出
def evaluate_risk(signal_states):
    momentum = signal_states.get("momentum")  # 直接使用
```

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
    "risk_level": "HIGH",
    "risk_flags": ["high_volatility"],
    "components": {
        "volatility_regime": "HIGH",
        "trend_instability": "LOW",
        "signal_disagreement": "LOW",
        "rapid_transitions": "LOW"
    }
}
```
