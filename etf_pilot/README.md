# 跨境 ETF 决策辅助仪表盘

基于 Python + Streamlit + AkShare 的**跨境 ETF 每日操作指导**工具：不负责自动交易，仅提供行情透视、偏离度、溢价分位与明日操作建议。

---

## 功能概览

### 决策看板
- **行情透视**：最新价、涨跌幅、距一年高/低%、Bias_MA20/60/200，定位当前价格空间。
- **明日建议**：基于**四层独立架构**生成「INCREASE（增加仓位）/ HOLD（持有）/ REDUCE（减少仓位）/ WAIT（等待）」及理由。
- **溢价率**：IOPV 与历史净值计算；(市价 - IOPV)/IOPV × 100%，带 60 日百分位进度条；高分位时明日建议变红并显示 ⚠️。
- **信号准确率 30d**：仅统计「补仓」「减仓」两类建议，发出买入后 5 日涨或发出卖出后 5 日跌记为正确；样本不足时显示「近期无动作」「样本不足」或百分比。
- 表格按**建议操作频率**排序，支持整表 `fillna("-")` 与 inf 清洗；数据源异常行（缺少 IOPV/溢价数据不足）浅橘色背景，「样本极少」浅黄色背景。
- 点击选择 ETF 可查看**明日操作卡片**（明天建议 + 理由）。

### 实时雷达
- 精简一览：最新价、涨跌幅、MA5/20/60/200、RSI（与决策看板不重复）。

### 个股深度分析
- 选择单只 ETF，查看 K 线、均线、布林带与成交量。

### 信号准确率 Tab
- 列：代码、名称、明日建议、建议操作频率、准确率 30d（文案或百分比）。
- 说明：锚定场内收盘价；仅统计补仓/减仓；准确定义为 5 日内价格方向与建议一致。

### 其他
- **极端风险模拟**：侧栏输入当前账户/持仓市值，显示「若标的发生 15% 回撤后」的金额。
- **ETF 列表**：`data/ETF汇总.xlsx`，需包含「代码」「名称」；可选「指数简称」用于类别筛选。

---

## 核心架构：四层独立系统

系统采用**严格分层的四层独立架构**，每层职责清晰，依赖关系明确：

```
原始数据
    ↓
Signal Engine（信号引擎）
    ↓
Risk Engine（风险引擎）
    ↓
Confidence Engine（置信度引擎）
    ↓
Decision Engine（决策引擎）
```

### 1. Signal Engine（信号引擎）

**职责：** 描述 ETF 市场状态，检测市场正在做什么。

**输出：** 独立的状态类别
- `trend`: "UP" | "DOWN" | "SIDEWAYS" | "UNKNOWN"
- `momentum`: "ACCELERATING" | "WEAKENING" | "NEUTRAL" | "UNKNOWN"
- `valuation`: "CHEAP" | "FAIR" | "EXPENSIVE" | "UNKNOWN"
- `volatility`: "LOW" | "NORMAL" | "HIGH" | "UNKNOWN"

**约束：**
- ❌ 不输出买卖建议
- ❌ 不计算评分
- ❌ 不评估风险
- ❌ 不评估置信度

### 2. Risk Engine（风险引擎）

**职责：** 评估交易风险条件。

**输入：** Signal Engine 的输出

**输出：**
- `risk_level`: "LOW" | "MEDIUM" | "HIGH"
- `risk_flags`: ["high_volatility", "trend_unknown", "signal_conflict", "rapid_transitions"]
- `components`: {volatility_regime, trend_instability, signal_disagreement, rapid_transitions}

**约束：**
- ✅ 只能使用 Signal Engine 的输出
- ❌ 禁止使用原始数据（价格、RSI、ATR 等）
- ❌ 禁止重新计算信号

### 3. Confidence Engine（置信度引擎）

**职责：** 评估信号可靠性。

**输入：** Signal Engine 和 Risk Engine 的输出

**输出：**
- `confidence`: "LOW" | "MEDIUM" | "HIGH"
- `confidence_reason`: ["high_signal_agreement", "stable_regime", "persistent_signals", ...]

**约束：**
- ✅ 只能使用 Signal Engine 和 Risk Engine 的输出
- ❌ 禁止使用原始数据
- ❌ 禁止重新计算前序层的指标

### 4. Decision Engine（决策引擎）

**职责：** 将系统状态转换为投资组合操作。

**输入：** Signal Engine、Risk Engine 和 Confidence Engine 的输出

**输出：**
- `action`: "INCREASE" | "HOLD" | "REDUCE" | "WAIT"
- `aggressiveness`: "LOW" | "MEDIUM" | "HIGH"
- `reason_tags`: ["bullish_signals", "high_risk_constraint", "high_confidence", ...]

**决策逻辑（三层）：**
1. **Layer 1: Signal Direction** - 基于 Signal Engine 的输出确定基础信号方向
2. **Layer 2: Risk Constraint** - 基于 Risk Engine 的输出调整初步动作
3. **Layer 3: Confidence Adjustment** - 基于 Confidence Engine 的输出调整激进程度

**约束：**
- ✅ 只能使用前序层的输出
- ❌ 禁止指标计算
- ❌ 禁止评分聚合
- ❌ 禁止信号重新计算

---

## 决策逻辑说明

### 决策动作

- **INCREASE（增加仓位）**：信号看多且风险可控
- **HOLD（持有）**：信号中性或需要观望
- **REDUCE（减少仓位）**：信号看空或风险过高
- **WAIT（等待）**：不确定性过高，暂不操作

### 决策规则优先级

1. **风险优先**：高风险时优先保护，限制增加仓位
2. **信号其次**：基于信号方向确定初步动作
3. **置信度最后**：调整激进程度，但不改变基本动作

### 示例决策流程

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

---

## 溢价与数据容错

- 溢价分位以**场内交易日**为主表 left 关联净值，关联后对单位净值 `ffill()`，缓解跨境披露滞后。
- 无 IOPV/净值时明日建议显示「缺少 IOPV/净值数据，无法评估溢价」，溢价率显示「无净值数据」；有净值但有效样本为 0 时显示「溢价数据不足」/「无净值数据」。
- 实时 IOPV 缺失时，会尝试用最近日线 + 净值估算临时溢价率，避免直接 N/A。

---

## 环境与安装

- **Python 3.9+**
- 依赖见 `requirements.txt`

```bash
cd etf_pilot
pip install -r requirements.txt
```

---

## 配置 ETF 列表

将 ETF 列表放到 **`data/ETF汇总.xlsx`**，需包含列：

- **代码**：ETF 代码（如 513100、518880）
- **名称**：ETF 名称
- **指数简称**（可选）：用于侧栏类别筛选

若未放置该文件，首次运行会在 `data` 目录下生成示例 Excel。

---

## 运行

```bash
streamlit run main.py
```

---

## 架构文档

详细的架构说明请参考：
- [核心架构文档](docs/CORE_ARCHITECTURE.md)
- [迁移指南](docs/MIGRATION_GUIDE.md)
- [Signal Engine 文档](signal_engine/README.md)
- [Risk Engine 文档](risk_engine/README.md)
- [Confidence Engine 文档](confidence_engine/README.md)
- [Decision Engine 文档](decision_engine/README.md)

---

## 免责声明

本工具仅供学习与研究，不构成任何投资建议。实盘决策请自行判断并承担风险。
