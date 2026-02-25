# 层独立性完整审计报告

## 审计日期
2024年（当前）

## 审计范围
- Signal Engine
- Risk Engine
- Confidence Engine
- Decision Engine

---

## ✅ 符合架构原则的部分

### 1. Signal Engine
- ✅ **职责清晰**：仅输出市场状态，不输出买卖建议
- ✅ **无评分逻辑**：不计算任何评分
- ✅ **无风险评估**：不包含任何风险评估逻辑
- ✅ **无置信度逻辑**：不包含任何置信度评估逻辑
- ✅ **无决策逻辑**：不包含任何决策逻辑

### 2. Risk Engine 使用 Signal Engine 输出
- ✅ **volatility_regime.py**：正确使用 Signal Engine 的 `volatility` 状态
- ✅ **trend_instability.py**：正确使用 Signal Engine 的 `trend` 状态
- ✅ **signal_disagreement.py**：正确使用 Signal Engine 的完整状态字典
- ✅ **rapid_transitions.py**：正确使用 Signal Engine 的历史状态序列

### 3. Confidence Engine 使用前序层输出
- ✅ **signal_agreement.py**：正确使用 Risk Engine 的 `signal_disagreement` 输出
- ✅ **assessment.py**：正确使用 Risk Engine 的 `rapid_transitions` 输出（已修复）
- ✅ **valuation_trend_conflict.py**：正确使用 Signal Engine 的 `trend` 和 `valuation` 状态

### 4. Decision Engine 使用前序层输出（新架构）
- ✅ **risk_constraint.py**：正确使用 Risk Engine 的输出
- ✅ **confidence_adjustment.py**：正确使用 Confidence Engine 的输出
- ✅ **decision.py**：正确使用所有前序层的输出

---

## ❌ 发现的逻辑重叠问题

### 问题 1：信号方向判断逻辑重复（高优先级）

**位置：**
- `risk_engine/signal_disagreement.py` - `_is_bullish()` 和 `_is_bearish()` 函数
- `decision_engine/signal_direction.py` - `_count_bullish_signals()` 和 `_count_bearish_signals()` 函数

**问题描述：**
两个引擎都实现了判断信号看多/看空方向的逻辑，虽然用途不同（Risk Engine 用于评估分歧，Decision Engine 用于确定方向），但逻辑有重叠。

**代码对比：**

**Risk Engine（signal_disagreement.py）：**
```python
def _is_bullish(state: str, factor: str) -> bool:
    if factor == "trend":
        return state_upper == TREND_UP
    elif factor == "momentum":
        return state_upper == MOMENTUM_NEUTRAL  # 保守判断
    elif factor == "valuation":
        return state_upper in (VALUATION_CHEAP, VALUATION_FAIR)
    elif factor == "volatility":
        return state_upper in (VOLATILITY_LOW, VOLATILITY_NORMAL)
```

**Decision Engine（signal_direction.py）：**
```python
def _count_bullish_signals(signal_states: dict[str, str]) -> int:
    if trend == TREND_UP:
        count += 1
    if valuation in (VALUATION_CHEAP, VALUATION_FAIR):
        count += 1
    if momentum in (MOMENTUM_ACCELERATING, MOMENTUM_NEUTRAL):  # 不同！
        count += 1
    if volatility in (VOLATILITY_LOW, VOLATILITY_NORMAL):
        count += 1
```

**差异：**
- Risk Engine 的 `_is_bullish()` 对 momentum 的判断更保守（只有 NEUTRAL 视为看多）
- Decision Engine 的 `_count_bullish_signals()` 对 momentum 的判断更激进（ACCELERATING 和 NEUTRAL 都视为看多）

**影响：**
- 逻辑不一致可能导致决策和风险评估不匹配
- 违反了"禁止跨层重复逻辑"的原则

**建议修复：**
- **方案 A（推荐）**：Decision Engine 使用 Risk Engine 的 `signal_disagreement` 输出，而不是重新判断信号方向
  - 优点：完全符合架构原则，消除重复逻辑
  - 缺点：需要调整 Decision Engine 的接口

- **方案 B**：统一判断逻辑，但保持两个函数（不推荐，仍然有重复）

**推荐方案：方案 A**

---

### 问题 2：Decision Engine 中的旧代码违反架构原则（高优先级）

**位置：**
- `decision_engine/scoring.py` - `calculate_score()` 和 `state_to_score()` 函数
- `decision_engine/confidence_engine.py` - `calculate_confidence()` 函数
- `decision_engine/daily_action.py` - `compute_daily_action()` 函数

**问题描述：**

#### 2.1 `scoring.py` 中的评分系统

**违反点：**
- `calculate_score()` 直接使用原始数据（rsi, atr_pct等）
- `state_to_score()` 进行状态→分数映射，这是评分系统
- 违反了"禁止评分聚合"的原则

**代码：**
```python
def calculate_score(
    last_row: Any,
    r2: float | None = None,
    slope: float | None = None,
    premium_pctile_60: float | None = None,
    atr_pct: float | None = None,
) -> dict[str, float]:
    # ❌ 直接使用原始数据
    rsi_val = last_row.get("RSI")
    # ❌ 进行评分计算
    trend = _score_trend(r2, slope)
    momentum = _score_momentum_rsi(rsi_val)
    ...
```

#### 2.2 `confidence_engine.py` 中的旧逻辑

**违反点：**
- 直接调用 `signal_disagreement_risk(signal_states)`，而不是使用 Risk Engine 的输出
- 直接调用 `volatility_risk_level(atr_pct)`，使用原始数据而不是 Signal Engine 的输出

**代码：**
```python
def calculate_confidence(...):
    # ❌ 重新计算信号分歧
    signal_disagreement = signal_disagreement_risk(signal_states or {})
    # ❌ 使用原始数据计算波动率风险
    volatility_risk = volatility_risk_level(atr_pct)
```

#### 2.3 `daily_action.py` 中的旧接口

**违反点：**
- `compute_daily_action()` 直接传递原始数据给 Risk Engine
- 使用旧的 `get_advice()` 函数，而不是新的 `make_decision()` 函数

**代码：**
```python
def compute_daily_action(...):
    risk_result = evaluate_risk(
        atr_pct=atr_pct,  # ❌ 直接传递原始数据
        pct_drawdown_from_high=pct_drawdown_from_high,
        signal_states=signal_states,
        ...
    )
    # ❌ 使用旧的 get_advice() 函数
    action, reason, ... = get_advice(...)
```

**影响：**
- 违反了架构原则
- 可能导致代码混乱和不一致

**建议修复：**
- 标记旧函数为废弃（deprecated）
- 逐步迁移到新的架构
- 更新 `daily_action.py` 使用新的 `make_decision()` 函数

---

### 问题 3：Decision Engine 的 signal_direction 与 Risk Engine 的 signal_disagreement 逻辑不一致（中优先级）

**位置：**
- `decision_engine/signal_direction.py` - `_count_bullish_signals()` 函数
- `risk_engine/signal_disagreement.py` - `_is_bullish()` 函数

**问题描述：**
两个函数对 momentum 状态的判断不一致：
- Risk Engine：只有 `MOMENTUM_NEUTRAL` 视为看多（保守）
- Decision Engine：`MOMENTUM_ACCELERATING` 和 `MOMENTUM_NEUTRAL` 都视为看多（激进）

**影响：**
- 可能导致决策和风险评估不匹配
- 例如：Risk Engine 可能评估为"信号分歧 HIGH"，但 Decision Engine 可能评估为"看多"

**建议修复：**
- 统一判断逻辑，或
- Decision Engine 使用 Risk Engine 的输出，而不是重新判断

---

## ⚠️ 潜在的架构问题

### 问题 4：Decision Engine 中的评分系统

**位置：**
- `decision_engine/scoring.py` - 整个文件

**问题描述：**
Decision Engine 中仍然存在完整的评分系统（`state_to_score()`, `calculate_score()`），这违反了"禁止评分聚合"的原则。

**建议：**
- 标记为废弃（deprecated）
- 逐步迁移到新的三层决策逻辑
- 保留以便向后兼容，但添加废弃警告

---

## 📊 层依赖关系检查

### Signal Engine → Risk Engine
- ✅ **正确**：Risk Engine 只使用 Signal Engine 的输出
- ✅ **无重复计算**：Risk Engine 不重新计算任何 Signal Engine 已计算的状态

### Signal Engine → Confidence Engine
- ✅ **正确**：Confidence Engine 使用 Signal Engine 的输出
- ✅ **无重复计算**：Confidence Engine 不重新计算任何 Signal Engine 已计算的状态

### Risk Engine → Confidence Engine
- ✅ **正确**：Confidence Engine 使用 Risk Engine 的输出（已修复）
- ✅ **无重复计算**：Confidence Engine 不再重新计算 rapid_transitions

### Signal Engine → Decision Engine
- ✅ **正确**：Decision Engine 使用 Signal Engine 的输出（新架构）
- ⚠️ **部分问题**：Decision Engine 的 `signal_direction.py` 重新实现了信号方向判断逻辑

### Risk Engine → Decision Engine
- ✅ **正确**：Decision Engine 使用 Risk Engine 的输出（新架构）
- ⚠️ **部分问题**：Decision Engine 的 `signal_direction.py` 与 Risk Engine 的逻辑不一致

### Confidence Engine → Decision Engine
- ✅ **正确**：Decision Engine 使用 Confidence Engine 的输出（新架构）

---

## 🔧 修复优先级

### 高优先级
1. **修复 Decision Engine 中的旧代码违反架构原则**（问题 2）
   - 影响：严重违反架构原则
   - 修复难度：中等
   - 建议：
     - 标记 `scoring.py` 中的函数为废弃
     - 标记 `confidence_engine.py` 为废弃（已有新的 `confidence_engine/` 目录）
     - 更新 `daily_action.py` 使用新的架构

2. **修复信号方向判断逻辑重复**（问题 1）
   - 影响：违反架构原则，逻辑不一致
   - 修复难度：中等
   - 建议：Decision Engine 使用 Risk Engine 的 `signal_disagreement` 输出

### 中优先级
3. **统一信号方向判断逻辑**（问题 3）
   - 影响：可能导致决策和风险评估不匹配
   - 修复难度：低
   - 建议：统一判断逻辑，或 Decision Engine 使用 Risk Engine 的输出

### 低优先级
4. **清理 Decision Engine 中的评分系统**（问题 4）
   - 影响：代码整洁度
   - 修复难度：低
   - 建议：标记为废弃，逐步迁移

---

## 📝 详细问题列表

### 逻辑重叠问题

| 问题 | 位置 | 类型 | 优先级 | 状态 |
|------|------|------|--------|------|
| 信号方向判断逻辑重复 | Decision Engine vs Risk Engine | 逻辑重复 | 高 | ⏳ 待修复 |
| 旧代码违反架构原则 | Decision Engine (scoring.py) | 架构违反 | 高 | ⏳ 待修复 |
| 旧代码违反架构原则 | Decision Engine (confidence_engine.py) | 架构违反 | 高 | ⏳ 待修复 |
| 旧代码违反架构原则 | Decision Engine (daily_action.py) | 架构违反 | 高 | ⏳ 待修复 |
| 信号方向判断逻辑不一致 | Decision Engine vs Risk Engine | 逻辑不一致 | 中 | ⏳ 待修复 |
| 评分系统存在 | Decision Engine (scoring.py) | 架构违反 | 低 | ⏳ 待修复 |

---

## 🔍 具体代码问题

### 问题 1：Decision Engine 的 signal_direction.py

**当前实现：**
```python
# decision_engine/signal_direction.py
def _count_bullish_signals(signal_states):
    if momentum in (MOMENTUM_ACCELERATING, MOMENTUM_NEUTRAL):
        count += 1  # ACCELERATING 和 NEUTRAL 都视为看多
```

**Risk Engine 的实现：**
```python
# risk_engine/signal_disagreement.py
def _is_bullish(state, factor):
    if factor == "momentum":
        return state_upper == MOMENTUM_NEUTRAL  # 只有 NEUTRAL 视为看多
```

**问题：** 逻辑不一致，可能导致决策和风险评估不匹配。

### 问题 2：Decision Engine 的旧代码

**scoring.py：**
```python
# ❌ 违反架构原则
def calculate_score(last_row, r2, slope, premium_pctile_60, atr_pct):
    rsi_val = last_row.get("RSI")  # 直接使用原始数据
    trend = _score_trend(r2, slope)  # 评分计算
```

**confidence_engine.py：**
```python
# ❌ 违反架构原则
def calculate_confidence(signal_states, atr_pct, ...):
    signal_disagreement = signal_disagreement_risk(signal_states)  # 重新计算
    volatility_risk = volatility_risk_level(atr_pct)  # 使用原始数据
```

**daily_action.py：**
```python
# ❌ 违反架构原则
def compute_daily_action(...):
    risk_result = evaluate_risk(
        atr_pct=atr_pct,  # 直接传递原始数据
        ...
    )
```

---

## 📋 修复建议总结

### 立即修复（高优先级）

1. **Decision Engine 使用 Risk Engine 的输出**
   - 修改 `signal_direction.py`，使用 Risk Engine 的 `signal_disagreement` 输出
   - 或统一判断逻辑

2. **标记旧代码为废弃**
   - `scoring.py` 中的 `calculate_score()` 和 `state_to_score()`
   - `confidence_engine.py` 整个文件（已有新的 `confidence_engine/` 目录）
   - `daily_action.py` 中的 `compute_daily_action()` 使用旧接口的部分

3. **更新 daily_action.py**
   - 使用新的 `make_decision()` 函数
   - 不再直接传递原始数据给 Risk Engine

### 后续优化（中低优先级）

4. **统一信号方向判断逻辑**
   - 确保 Decision Engine 和 Risk Engine 的判断一致

5. **逐步移除评分系统**
   - 在确保向后兼容的前提下，逐步移除 `scoring.py` 中的评分函数

---

## 下一步行动

1. ✅ 创建完整审计报告（本文档）
2. ⏳ 修复 Decision Engine 中的旧代码违反架构原则
3. ⏳ 修复信号方向判断逻辑重复
4. ⏳ 统一信号方向判断逻辑
5. ⏳ 更新 daily_action.py 使用新架构
6. ⏳ 验证修复后的架构独立性

---

## 总结

### 符合架构原则的部分
- Signal Engine 职责清晰，无重叠
- Risk Engine 正确使用 Signal Engine 的输出
- Confidence Engine 正确使用 Signal Engine 和 Risk Engine 的输出（已修复）
- Decision Engine 的新架构正确使用所有前序层的输出

### 需要修复的问题
1. **信号方向判断逻辑重复**：Decision Engine 和 Risk Engine 都实现了判断逻辑
2. **Decision Engine 中的旧代码**：仍然存在违反架构原则的旧代码
3. **逻辑不一致**：Decision Engine 和 Risk Engine 对 momentum 的判断不一致

### 修复建议
- Decision Engine 应该使用 Risk Engine 的 `signal_disagreement` 输出，而不是重新判断信号方向
- 标记所有旧代码为废弃，逐步迁移到新架构
- 统一判断逻辑，确保决策和风险评估一致
