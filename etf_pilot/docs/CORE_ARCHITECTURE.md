# 核心逻辑架构 - 四层独立系统

## 总原则

系统必须包含四个严格独立的层：

1. **Signal Engine** - 信号引擎
2. **Risk Engine** - 风险引擎
3. **Confidence Engine** - 置信度引擎
4. **Decision Engine** - 决策引擎

## 核心规则

- ✅ 每层只能使用前一层（或更早层）的输出
- ✅ 任何层不得重新计算前一层已计算的指标
- ✅ 不允许共享评分系统
- ✅ 不允许跨层重复逻辑
- ✅ 每层单一职责

---

## 依赖方向

```
原始数据 (价格、净值、技术指标等)
    ↓
┌─────────────────────────────────────┐
│  1. Signal Engine                   │
│  输入: 原始数据                      │
│  输出: signal_states                 │
│  {momentum, trend, valuation,       │
│   volatility}                        │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  2. Risk Engine                     │
│  输入: Signal Engine 输出 + 原始数据 │
│  输出: risk_level                    │
│  {level: LOW/MEDIUM/HIGH,           │
│   volatility_regime,                │
│   drawdown_risk,                    │
│   signal_disagreement,              │
│   concentration_risk}               │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  3. Confidence Engine               │
│  输入: Signal Engine 输出 +          │
│       Risk Engine 输出（部分）       │
│  输出: confidence_level              │
│  LOW / MEDIUM / HIGH                │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  4. Decision Engine                 │
│  输入: Signal Engine 输出 +          │
│       Risk Engine 输出 +             │
│       Confidence Engine 输出 +       │
│       市场状态 (market_regime)       │
│  输出: 买卖建议                      │
│  {action, reason, display_label,    │
│   confidence_band, total_score}    │
└─────────────────────────────────────┘
```

---

## 各层详细说明

### 1. Signal Engine（信号引擎）

**职责：**
- 计算技术指标（RSI、ATR、趋势回归等）
- 将指标转换为状态标签
- **不产出任何买卖建议**

**输入：**
- 原始价格数据
- 净值数据
- 技术指标计算所需参数

**输出：**
```python
signal_states = {
    "momentum": "oversold" | "neutral" | "overbought",
    "trend": "strong_up" | "weak_up" | "down" | "unknown",
    "valuation": "cheap" | "fair_low" | "fair_high" | "expensive" | "unknown",
    "volatility": "low" | "medium" | "high" | "unknown"
}
```

**禁止：**
- ❌ 输出买卖建议
- ❌ 计算风险等级
- ❌ 计算置信度
- ❌ 计算评分

---

### 2. Risk Engine（风险引擎）

**职责：**
- 基于 Signal Engine 的输出评估风险
- 综合多个风险维度输出单一风险等级
- **不产出买卖建议**

**输入：**
- Signal Engine 的 `signal_states`
- 原始数据（ATR%、回撤、集中度等）

**输出：**
```python
risk_result = {
    "level": "LOW" | "MEDIUM" | "HIGH",
    "volatility_regime": "LOW" | "MEDIUM" | "HIGH",
    "drawdown_risk": "LOW" | "MEDIUM" | "HIGH",
    "signal_disagreement": "LOW" | "MEDIUM" | "HIGH",
    "concentration_risk": "LOW" | "MEDIUM" | "HIGH"
}
```

**禁止：**
- ❌ 重新计算 Signal Engine 已计算的状态
- ❌ 输出买卖建议
- ❌ 计算置信度
- ❌ 计算评分

**允许：**
- ✅ 使用 Signal Engine 的 `signal_states` 计算信号分歧
- ✅ 使用原始数据（如 ATR%）计算波动率风险

---

### 3. Confidence Engine（置信度引擎）

**职责：**
- 基于 Signal Engine 和 Risk Engine 的输出评估置信度
- 评估信号一致性、制度稳定性、波动率水平
- **不产出买卖建议**

**输入：**
- Signal Engine 的 `signal_states`
- Risk Engine 的部分输出（如 `signal_disagreement`, `volatility_regime`）
- 市场制度信息（`market_regime`）

**输出：**
```python
confidence_level = "LOW" | "MEDIUM" | "HIGH"
```

**禁止：**
- ❌ 重新计算 Signal Engine 已计算的状态
- ❌ 重新计算 Risk Engine 已计算的风险指标
- ❌ 输出买卖建议
- ❌ 计算评分

**允许：**
- ✅ 使用 Risk Engine 的 `signal_disagreement` 评估信号一致性
- ✅ 使用 Risk Engine 的 `volatility_regime` 评估波动率水平
- ✅ 使用市场制度的 `confidence` 字段评估制度稳定性

---

### 4. Decision Engine（决策引擎）

**职责：**
- 组合 Signal Engine、Risk Engine、Confidence Engine 的输出
- 结合市场状态生成最终买卖建议
- **唯一产出买卖建议的层**

**输入：**
- Signal Engine 的 `signal_states`
- Risk Engine 的 `risk_result`（特别是 `level`）
- Confidence Engine 的 `confidence_level`
- 市场状态 `market_regime`
- 溢价偏离度等额外风险指标

**输出：**
```python
decision_result = {
    "action": "强烈建议补仓" | "持有观望" | "考虑套利/减仓",
    "reason": str,
    "display_label": str,
    "confidence_band": "high" | "medium" | "low",
    "total_score": float
}
```

**禁止：**
- ❌ 重新计算 Signal Engine 已计算的状态
- ❌ 重新计算 Risk Engine 已计算的风险指标
- ❌ 重新计算 Confidence Engine 已计算的置信度

**允许：**
- ✅ 将 Signal Engine 的状态转换为评分（仅用于决策阈值）
- ✅ 使用 Risk Engine 的风险等级调整决策阈值
- ✅ 使用 Confidence Engine 的置信度作为输出的一部分

---

## 关键约束

### 1. 禁止重复计算

**错误示例：**
```python
# ❌ 在 Decision Engine 中重新计算 RSI
def get_advice(...):
    rsi = calculate_rsi(data)  # 错误！Signal Engine 已经计算过
    momentum = momentum_state(rsi)  # 错误！应该使用 signal_states["momentum"]
```

**正确示例：**
```python
# ✅ 使用 Signal Engine 的输出
def get_advice(signal_states, ...):
    momentum = signal_states["momentum"]  # 直接使用
```

### 2. 禁止共享评分系统

**错误示例：**
```python
# ❌ 在多个层中使用同一个评分函数
# Signal Engine 中
score = calculate_score(...)

# Risk Engine 中
score = calculate_score(...)  # 错误！重复使用
```

**正确示例：**
```python
# ✅ 每层有独立的评估逻辑
# Signal Engine: 输出状态
signal_states = get_signal_states(...)

# Risk Engine: 输出风险等级
risk_level = evaluate_risk(...)

# Decision Engine: 组合所有输出
decision = combine_for_decision(signal_states, risk_level, ...)
```

### 3. 禁止跨层重复逻辑

**错误示例：**
```python
# ❌ 在 Risk Engine 和 Confidence Engine 中都计算信号分歧
# Risk Engine
def evaluate_risk(signal_states):
    disagreement = calculate_disagreement(signal_states)  # 计算一次

# Confidence Engine
def calculate_confidence(signal_states):
    disagreement = calculate_disagreement(signal_states)  # 错误！重复计算
```

**正确示例：**
```python
# ✅ Risk Engine 计算，Confidence Engine 使用
# Risk Engine
def evaluate_risk(signal_states):
    disagreement = calculate_disagreement(signal_states)
    return {"signal_disagreement": disagreement, ...}

# Confidence Engine
def calculate_confidence(signal_states, risk_result):
    disagreement = risk_result["signal_disagreement"]  # 使用 Risk Engine 的输出
```

---

## 数据流示例

```python
# 1. Signal Engine
signal_states = signal_engine.get_signal_states(
    last_row=last,
    r2=r2,
    slope=slope,
    premium_pctile_60=premium_pctile_60,
    atr_pct=atr_pct
)
# 输出: {"momentum": "oversold", "trend": "strong_up", ...}

# 2. Risk Engine（使用 Signal Engine 的输出）
risk_result = risk_engine.evaluate_risk(
    signal_states=signal_states,  # 来自 Signal Engine（必需）
    history=history,  # 可选：历史状态序列（用于评估快速状态转换）
    lookback_days=5  # 可选：历史窗口天数
)
# 输出: {
#     "risk_level": "LOW" | "MEDIUM" | "HIGH",
#     "risk_flags": [...],
#     "components": {
#         "volatility_regime": "LOW" | "MEDIUM" | "HIGH",
#         "trend_instability": "LOW" | "MEDIUM" | "HIGH",
#         "signal_disagreement": "LOW" | "MEDIUM" | "HIGH",
#         "rapid_transitions": "LOW" | "MEDIUM" | "HIGH"
#     }
# }

# 3. Confidence Engine（使用 Signal Engine 和 Risk Engine 的输出）
confidence_result = confidence_engine.calculate_confidence(
    signal_states=signal_states,  # 来自 Signal Engine
    risk_result=risk_result,  # 来自 Risk Engine（必需）
    market_regime=market_regime
)
# 输出: {"confidence": "HIGH", "confidence_reason": [...]}

# 4. Decision Engine（使用所有前序层的输出）
decision = decision_engine.make_decision(
    signal_states=signal_states,  # 来自 Signal Engine
    risk_result=risk_result,  # 来自 Risk Engine
    confidence_result=confidence_result  # 来自 Confidence Engine
)
# 输出: {
#     "action": "INCREASE" | "HOLD" | "REDUCE" | "WAIT",
#     "aggressiveness": "LOW" | "MEDIUM" | "HIGH",
#     "reason_tags": [...]
# }
```

---

## 目录结构

```
etf_pilot/
├── signal_engine/          # 1. Signal Engine
│   ├── indicators.py       # 技术指标计算
│   ├── states.py           # 状态转换
│   └── signals.py          # 信号状态
│
├── risk_engine/            # 2. Risk Engine
│   ├── volatility_regime.py
│   ├── drawdown_risk.py
│   ├── signal_disagreement.py
│   ├── concentration_risk.py
│   └── assessment.py       # 汇总评估
│
├── confidence_engine/       # 3. Confidence Engine（需从 decision_engine 移出）
│   └── confidence.py       # 置信度计算
│
└── decision_engine/        # 4. Decision Engine
    ├── scoring.py          # 状态→评分映射（仅用于决策阈值）
    └── daily_action.py     # 每日建议
```

---

## 下一步行动

1. ✅ 创建架构文档（本文档）
2. ⏳ 将 `confidence_engine.py` 从 `decision_engine/` 移至独立的 `confidence_engine/` 目录
3. ⏳ 重构各层，确保严格遵循依赖方向
4. ⏳ 移除所有重复计算和共享评分系统
5. ⏳ 更新所有导入和引用
