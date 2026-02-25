# 迁移指南：从旧架构到新架构

## 概述

本文档帮助您将代码从旧架构迁移到新的四层独立架构。

---

## 主要变更

### 1. Decision Engine 接口变更

#### 旧接口（已废弃）

```python
from decision_engine import get_advice, compute_daily_action

# 旧接口：返回元组
action, reason, display_label, confidence_band, total_score = get_advice(
    signal_states,
    premium_deviation_val,
    market_regime,
    risk_level=risk_result["level"],
    atr_pct=atr_pct,
)

# 旧接口：返回元组
action, reason, display_label, confidence_band, conflicting_signals, total_score = compute_daily_action(
    last=last_row,
    premium_pct=premium_pct,
    atr_pct=atr_pct,
    ...
)
```

#### 新接口（推荐）

```python
from decision_engine import make_decision
from decision_engine.daily_action import compute_daily_action_v2
from decision_engine.compat import decision_to_legacy_format

# 新接口：返回字典
decision = make_decision(
    signal_states=signal_states,
    risk_result=risk_result,
    confidence_result=confidence_result,
)

# 新接口：返回字典
result = compute_daily_action_v2(
    last=last_row,
    premium_pctile_60=premium_pctile_60,
    r2=r2,
    slope=slope,
    atr_pct=atr_pct,
    market_regime=market_regime,
    history=history,
)

# 如果需要旧格式，使用适配器
action, reason, display_label, confidence_band, conflicting_signals, total_score = decision_to_legacy_format(result)
```

---

## 迁移步骤

### 步骤 1：更新导入

**旧代码：**
```python
from decision_engine import get_advice, compute_daily_action
from decision_engine.scoring import calculate_score, state_to_score
```

**新代码：**
```python
from decision_engine import make_decision
from decision_engine.daily_action import compute_daily_action_v2
from decision_engine.compat import decision_to_legacy_format
```

---

### 步骤 2：更新决策生成

#### 场景 A：使用 `make_decision()`

**旧代码：**
```python
from decision_engine import get_advice
from risk_engine import evaluate_risk

signal_states = get_signal_states(...)
risk_result = evaluate_risk(...)
action, reason, display_label, confidence_band, total_score = get_advice(
    signal_states,
    premium_deviation_val,
    market_regime,
    risk_level=risk_result["level"],
    atr_pct=atr_pct,
)
```

**新代码：**
```python
from decision_engine import make_decision
from risk_engine import evaluate_risk
from confidence_engine import calculate_confidence

signal_states = get_signal_states(...)
risk_result = evaluate_risk(signal_states=signal_states, ...)
confidence_result = calculate_confidence(
    signal_states=signal_states,
    risk_result=risk_result,
    market_regime=market_regime,
)

decision = make_decision(
    signal_states=signal_states,
    risk_result=risk_result,
    confidence_result=confidence_result,
)

action = decision["action"]  # "INCREASE" | "HOLD" | "REDUCE" | "WAIT"
aggressiveness = decision["aggressiveness"]  # "LOW" | "MEDIUM" | "HIGH"
reason_tags = decision["reason_tags"]  # [...]
```

#### 场景 B：使用 `compute_daily_action_v2()`

**旧代码：**
```python
from decision_engine.daily_action import compute_daily_action

action, reason, display_label, confidence_band, conflicting_signals, total_score = compute_daily_action(
    last=last_row,
    premium_pct=premium_pct,
    avg_premium_22d=avg_premium_22d,
    premium_std_22d=premium_std_22d,
    premium_pctile_60=premium_pctile_60d,
    r2=r2,
    slope=slope,
    atr_pct=atr_pct,
    pct_drawdown_from_high=pct_drawdown_from_high,
)
```

**新代码：**
```python
from decision_engine.daily_action import compute_daily_action_v2
from decision_engine.compat import decision_to_legacy_format

# 准备历史状态序列（可选）
history = None  # TODO: 可以从历史数据构建

result = compute_daily_action_v2(
    last=last_row,
    premium_pctile_60=premium_pctile_60d,  # 注意：不再需要 premium_pct, avg_premium_22d, premium_std_22d
    r2=r2,
    slope=slope,
    atr_pct=atr_pct,
    market_regime=market_regime,  # 可选
    history=history,  # 可选
)

# 如果需要旧格式，使用适配器
action, reason, display_label, confidence_band, conflicting_signals, total_score = decision_to_legacy_format(result)

# 或者直接使用新格式
action = result["action"]
aggressiveness = result["aggressiveness"]
reason_tags = result["reason_tags"]
```

---

### 步骤 3：更新动作名称映射

**旧格式：**
- `"强烈建议补仓"`
- `"持有观望"`
- `"考虑套利/减仓"`

**新格式：**
- `"INCREASE"`
- `"HOLD"`
- `"REDUCE"`
- `"WAIT"`

**转换：**
```python
action_map = {
    "INCREASE": "强烈建议补仓",
    "HOLD": "持有观望",
    "REDUCE": "考虑套利/减仓",
    "WAIT": "等待",
}
action_cn = action_map.get(action, "持有观望")
```

---

### 步骤 4：更新置信度格式

**旧格式：**
- `"high"` (小写)
- `"medium"` (小写)
- `"low"` (小写)

**新格式：**
- `"HIGH"` (大写，在 `aggressiveness` 字段中)
- `"MEDIUM"` (大写)
- `"LOW"` (大写)

**转换：**
```python
aggressiveness_to_confidence = {
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
}
confidence_band = aggressiveness_to_confidence.get(aggressiveness, "medium")
```

---

### 步骤 5：移除评分系统依赖

**旧代码：**
```python
from decision_engine.scoring import calculate_score, state_to_score

score_result = calculate_score(...)
total_score = score_result["total"]
```

**新代码：**
```python
# 不再使用评分系统
# 直接使用 make_decision() 生成决策
decision = make_decision(...)
# total_score 已废弃，返回 0.0
```

---

## 向后兼容

### 使用适配器函数

如果您需要保持旧格式的返回值，可以使用适配器函数：

```python
from decision_engine.compat import decision_to_legacy_format, compute_daily_action_compat

# 方式 1：使用适配器函数（完全兼容旧接口）
action, reason, display_label, confidence_band, conflicting_signals, total_score = compute_daily_action_compat(
    last=last_row,
    premium_pct=premium_pct,
    ...
)

# 方式 2：使用新接口 + 适配器
decision = compute_daily_action_v2(...)
action, reason, ... = decision_to_legacy_format(decision)
```

---

## 常见问题

### Q1: 如何获取 `total_score`？

**A:** `total_score` 已废弃，新架构不再使用评分系统。如果需要，可以返回 `0.0`。

### Q2: 如何获取 `conflicting_signals`？

**A:** 从 `risk_result` 中获取：

```python
risk_result = evaluate_risk(...)
conflicting_signals = risk_result.get("risk_flags", []).count("signal_conflict") > 0
# 或者
signal_disagreement = risk_result.get("components", {}).get("signal_disagreement", "")
conflicting_signals = signal_disagreement == "HIGH"
```

### Q3: 如何构建历史状态序列？

**A:** 从历史数据构建 Signal Engine 的状态序列：

```python
history = []
for _, row in hist.iterrows():
    signal_states = get_signal_states(
        row,
        r2=None,  # 需要计算
        slope=None,  # 需要计算
        premium_pctile_60=None,  # 需要计算
        atr_pct=None,  # 需要计算
    )
    history.append(signal_states)
```

### Q4: 旧代码还能用吗？

**A:** 可以，但会显示废弃警告。建议尽快迁移到新架构。

---

## 迁移检查清单

- [ ] 更新所有 `get_advice()` 调用为 `make_decision()`
- [ ] 更新所有 `compute_daily_action()` 调用为 `compute_daily_action_v2()`
- [ ] 移除所有 `calculate_score()` 和 `state_to_score()` 调用
- [ ] 更新动作名称映射（旧中文 → 新英文）
- [ ] 更新置信度格式（旧小写 → 新大写）
- [ ] 添加 Confidence Engine 的调用
- [ ] 更新 Risk Engine 的调用（移除原始数据参数）
- [ ] 测试所有变更
- [ ] 更新文档和注释

---

## 示例：完整迁移

### 迁移前

```python
from decision_engine.daily_action import compute_daily_action
from risk_engine import evaluate_risk

# 计算指标
r2, slope = compute_trend_classification(hist)
atr_pct = calculate_atr_pct(last)

# 评估风险（旧接口）
risk_result = evaluate_risk(
    atr_pct=atr_pct,
    pct_drawdown_from_high=pct_drawdown_from_high,
    signal_states=signal_states,
)

# 生成决策（旧接口）
action, reason, display_label, confidence_band, conflicting_signals, total_score = compute_daily_action(
    last=last_row,
    premium_pct=premium_pct,
    avg_premium_22d=avg_premium_22d,
    premium_std_22d=premium_std_22d,
    premium_pctile_60=premium_pctile_60d,
    r2=r2,
    slope=slope,
    atr_pct=atr_pct,
    pct_drawdown_from_high=pct_drawdown_from_high,
)
```

### 迁移后

```python
from decision_engine.daily_action import compute_daily_action_v2
from decision_engine.compat import decision_to_legacy_format
from risk_engine import evaluate_risk
from confidence_engine import calculate_confidence
from signal_engine import get_signal_states

# 1. Signal Engine
signal_states = get_signal_states(
    last_row,
    r2=r2,
    slope=slope,
    premium_pctile_60=premium_pctile_60d,
    atr_pct=atr_pct,
)

# 2. Risk Engine（新接口：只使用 Signal Engine 的输出）
risk_result = evaluate_risk(
    signal_states=signal_states,
    history=history,  # 可选
    lookback_days=5,
)

# 3. Confidence Engine
confidence_result = calculate_confidence(
    signal_states=signal_states,
    risk_result=risk_result,
    market_regime=market_regime,
)

# 4. Decision Engine（新接口）
result = compute_daily_action_v2(
    last=last_row,
    premium_pctile_60=premium_pctile_60d,
    r2=r2,
    slope=slope,
    atr_pct=atr_pct,
    market_regime=market_regime,
    history=history,
)

# 转换为旧格式（如果需要）
action, reason, display_label, confidence_band, conflicting_signals, total_score = decision_to_legacy_format(result)
```

---

## 总结

新架构的主要优势：

1. **清晰的依赖关系**：每层只使用前序层的输出
2. **无逻辑重复**：消除了所有跨层重复逻辑
3. **易于测试**：每层可以独立测试
4. **易于维护**：职责清晰，易于理解和修改

迁移到新架构后，您的代码将更加清晰、可维护，并且完全符合架构原则。
