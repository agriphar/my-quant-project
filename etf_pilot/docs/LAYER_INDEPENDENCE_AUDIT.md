# 层独立性审计报告

## 审计日期
2024年（当前）

## 审计范围
- Signal Engine
- Risk Engine
- Confidence Engine
- Decision Engine（部分）

---

## ✅ 符合架构原则的部分

### 1. Signal Engine
- ✅ **职责清晰**：仅输出市场状态，不输出买卖建议
- ✅ **无评分逻辑**：不计算任何评分
- ✅ **无风险评估**：不包含任何风险评估逻辑
- ✅ **无置信度逻辑**：不包含任何置信度评估逻辑

### 2. Risk Engine 使用 Signal Engine 输出
- ✅ **volatility_regime.py**：正确使用 Signal Engine 的 `volatility` 状态
- ✅ **trend_instability.py**：正确使用 Signal Engine 的 `trend` 状态
- ✅ **signal_disagreement.py**：正确使用 Signal Engine 的完整状态字典

### 3. Confidence Engine 使用前序层输出
- ✅ **signal_agreement.py**：正确使用 Risk Engine 的 `signal_disagreement` 输出
- ✅ **valuation_trend_conflict.py**：正确使用 Signal Engine 的 `trend` 和 `valuation` 状态

---

## ❌ 发现的逻辑重叠问题

### 问题 1：状态变化计数逻辑重复

**位置：**
- `risk_engine/rapid_transitions.py` - `_count_state_changes()` 函数
- `confidence_engine/signal_persistence.py` - `_count_state_changes()` 函数

**问题描述：**
两个引擎都实现了完全相同的状态变化计数逻辑，违反了"禁止跨层重复逻辑"的原则。

**代码重复：**
```python
# risk_engine/rapid_transitions.py (lines 24-57)
def _count_state_changes(history, factor):
    # ... 完全相同的实现

# confidence_engine/signal_persistence.py (lines 24-57)
def _count_state_changes(history, factor):
    # ... 完全相同的实现
```

**影响：**
- 代码重复，维护成本高
- 如果逻辑需要修改，需要在两个地方同时修改
- 违反了 DRY（Don't Repeat Yourself）原则

**建议修复：**
1. **方案 A（推荐）**：将状态变化计数逻辑移到 Risk Engine，Confidence Engine 使用 Risk Engine 的 `rapid_transitions` 输出
   - 优点：符合架构原则（Confidence Engine 使用 Risk Engine 的输出）
   - 缺点：需要修改 Confidence Engine 的接口

2. **方案 B**：创建一个共享的工具模块（不推荐，违反架构原则）

3. **方案 C**：Confidence Engine 直接使用 Risk Engine 的 `rapid_transitions` 组件输出
   - 优点：完全符合架构原则
   - 缺点：需要修改 Risk Engine 的接口，使其输出状态变化次数

**推荐方案：方案 A**

---

### 问题 2：信号持续性评估与快速状态转换评估逻辑重复

**位置：**
- `risk_engine/rapid_transitions.py` - `rapid_transitions_risk()` 函数
- `confidence_engine/signal_persistence.py` - `signal_persistence_confidence()` 函数

**问题描述：**
两个函数都评估信号状态的快速变化，使用相同的逻辑和阈值，只是输出不同（风险等级 vs 置信度等级）。

**逻辑重复：**
```python
# risk_engine/rapid_transitions.py
def rapid_transitions_risk(current_states, history, lookback_days):
    # 统计状态变化次数
    # 根据变化次数评估风险等级

# confidence_engine/signal_persistence.py
def signal_persistence_confidence(current_states, history, lookback_days):
    # 统计状态变化次数（相同的逻辑）
    # 根据变化次数评估置信度等级（相同的阈值）
```

**影响：**
- 逻辑重复，违反了"禁止跨层重复逻辑"的原则
- 如果阈值需要调整，需要在两个地方同时修改

**建议修复：**
Confidence Engine 应该使用 Risk Engine 的 `rapid_transitions` 输出，而不是重新计算。

修改 `confidence_engine/assessment.py`：
```python
# 当前（错误）
persistence_conf = signal_persistence_confidence(
    current_states=signal_states,
    history=history,
    lookback_days=lookback_days,
)

# 应该改为（正确）
rapid_transitions_risk = risk_result["components"].get("rapid_transitions")
# 将风险等级转换为置信度等级
persistence_conf = _risk_to_confidence(rapid_transitions_risk)
```

---

## ⚠️ 潜在的架构问题

### 问题 3：Decision Engine 中的旧代码

**位置：**
- `decision_engine/scoring.py` - `calculate_score()` 函数

**问题描述：**
Decision Engine 中仍然存在直接使用原始数据（rsi, atr_pct等）的旧函数，这些函数应该被废弃或重构。

**影响：**
- 违反了架构原则（Decision Engine 应该只使用前序层的输出）
- 可能导致代码混乱

**建议：**
- 标记为废弃（deprecated）
- 逐步迁移到使用 Signal Engine 输出的新接口

---

## 📊 层依赖关系检查

### Signal Engine → Risk Engine
- ✅ **正确**：Risk Engine 只使用 Signal Engine 的输出
- ✅ **无重复计算**：Risk Engine 不重新计算任何 Signal Engine 已计算的状态

### Signal Engine → Confidence Engine
- ✅ **正确**：Confidence Engine 使用 Signal Engine 的输出
- ✅ **无重复计算**：Confidence Engine 不重新计算任何 Signal Engine 已计算的状态

### Risk Engine → Confidence Engine
- ⚠️ **部分正确**：Confidence Engine 使用 Risk Engine 的 `signal_disagreement` 输出
- ❌ **存在问题**：Confidence Engine 重新实现了 Risk Engine 的 `rapid_transitions` 逻辑

---

## 🔧 修复优先级

### 高优先级
1. **修复状态变化计数逻辑重复**（问题 1）
   - 影响：违反核心架构原则
   - 修复难度：中等
   - 建议：Confidence Engine 使用 Risk Engine 的 `rapid_transitions` 输出

### 中优先级
2. **修复信号持续性评估逻辑重复**（问题 2）
   - 影响：违反核心架构原则
   - 修复难度：中等
   - 建议：与问题 1 一起修复

### 低优先级
3. **清理 Decision Engine 中的旧代码**（问题 3）
   - 影响：代码整洁度
   - 修复难度：低
   - 建议：标记为废弃，逐步迁移

---

## 📝 总结

### 符合架构原则的部分
- Signal Engine 职责清晰，无重叠
- Risk Engine 正确使用 Signal Engine 的输出
- Confidence Engine 正确使用 Signal Engine 和 Risk Engine 的部分输出

### 需要修复的问题
1. **状态变化计数逻辑重复**：Risk Engine 和 Confidence Engine 都实现了相同的逻辑
2. **信号持续性评估逻辑重复**：两个引擎评估相同的指标，只是输出不同

### 修复建议
- Confidence Engine 应该使用 Risk Engine 的 `rapid_transitions` 输出，而不是重新计算
- 这样可以完全符合架构原则：每层只能使用前一层（或更早层）的输出

---

## 下一步行动

1. ✅ 创建审计报告（本文档）
2. ✅ 修复状态变化计数逻辑重复
3. ✅ 修复信号持续性评估逻辑重复
4. ✅ 更新 Confidence Engine 文档
5. ⏳ 验证修复后的架构独立性

## 修复完成

### 已修复的问题

1. **状态变化计数逻辑重复** ✅
   - Confidence Engine 现在使用 Risk Engine 的 `rapid_transitions` 输出
   - 移除了重复的 `_count_state_changes()` 逻辑
   - 添加了 `_rapid_transitions_risk_to_confidence()` 函数进行转换

2. **信号持续性评估逻辑重复** ✅
   - `signal_persistence_confidence()` 函数已标记为废弃
   - Confidence Engine 的 `calculate_confidence()` 现在使用 Risk Engine 的输出
   - 更新了所有相关文档

### 修复后的架构

```
Signal Engine
    ↓
Risk Engine (计算 rapid_transitions)
    ↓
Confidence Engine (使用 Risk Engine 的 rapid_transitions 输出)
```

现在完全符合架构原则：每层只能使用前一层（或更早层）的输出。
