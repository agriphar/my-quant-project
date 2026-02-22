# 金融科技审阅报告 — ETF Pilot

**角色：** 金融科技审阅人。  
**关注点：** 过度设计、虚假抽象、隐藏耦合、误导性投资信号、长期维护风险。

---

## 1. AI 式过度设计

### 1.1 未产生实际收益的分层

- **六层架构**（market_regime、signal_engine、risk_engine、decision_engine、explanation_engine、ui_dashboard）在文档中有说明并被遵循，但存在以下问题：
  - **market_regime** 从未进入主流程：`etf_data.build_monitor_table_advanced` 调用 `compute_daily_action(..., r2=..., slope=..., atr_pct=..., pct_drawdown_from_high=...)` 时**从未传入 `market_regime`**。因此 `get_advice(..., market_regime=...)` 在运行中始终收到 `None`。「regime」相关分支（例如 risk_off → 提高阈值）在生产环境中是死代码。
  - **explanation_engine** 存在两个入口（`get_reason_for_signal` 与 `explain_decision` / `generate_reasoning`）。前者仍被 `get_signal_from_score`（兼容路径）使用，后者被 `get_advice` 使用。两套并行的「解释」路径职责重叠，增加认知负担和逻辑漂移风险。

### 1.2 重复的状态 → 文案映射

- **信号状态字符串**在 `signal_engine.states` 中定义（如 `"oversold"`、`"strong_up"`）。
- **risk_engine.signal_disagreement** 用字符串字面量重新定义相同语义（如 `BULLISH_MOMENTUM = "oversold"` 等），并注释「与 signal_engine.states 对齐（仅读状态名，不导入避免循环）」——即依赖人工同步，没有单一数据源。
- **explanation_engine.structured_reasoning** 中定义了 `MOMENTUM_LABELS`、`TREND_LABELS` 等，键与上述状态一致。新增一种状态（例如新的趋势档位）需要在至少三个模块中修改并更新文档；没有类型或测试保证一致性。

### 1.3 「信心区间」只是又一层阈值

- **信心区间**由与决策相同的分数和阈值推导得出（`_confidence_band(total, strong_buy, hold, risk_level, vetoed)`）。因此实际链路是：  
  **分数 → 动作（经 strong_buy/hold）→ display_label + confidence_band**。  
  区间没有提供新信息，只是冗余的派生展示。若阈值或风险逻辑变更，信心逻辑必须同步调整，否则界面会错误表达「信心」。

---

## 2. 虚假抽象

### 2.1 「信号引擎不输出买卖」

- 架构说明信号引擎「仅产出状态/概率，不产出买卖建议」。实际情况是：
  - **decision_engine** 通过 `state_to_score()` 用相同阈值和语义（如 oversold→2、overbought→0）把这些状态映射成**数值分数**。因此「状态」只是同一套逻辑的中间编码，最终仍会变成「补仓/减仓」。
  - 「信号层不输出买卖」仅通过措辞满足；决策层的打分是对同一批输入的直接、刚性映射。没有真正的抽象边界，只是多了一层间接，以及两处需要同步的阈值（例如 states 中的 RSI 45/70 与 `_score_momentum_rsi` 中的设定）。

### 2.2 「解释引擎无业务依赖」

- ARCHITECTURE 称「explanation_engine → 无业务依赖（仅接收决策结果）」。
  - 实际上它接收 **regime、signal_states、risk_level、decision**，并依据**精确的决策字符串**（如 `if decision == "强烈建议补仓"`）和状态键（`momentum`、`trend` 等）做分支。因此与决策层的**动作枚举**以及信号/风险的**词汇表**强耦合。任何新增动作或状态都会迫使解释引擎一起改。这是很强的业务依赖，只是没有以导入 decision/signal/risk 代码的形式体现。

### 2.3 strategy「兼容」再导出

- **strategy/** 为「兼容」而再导出 `get_signal_from_score` 等。该 API 返回 `(action, reason)`，**不**返回 `display_label` 或 `confidence_band`。因此存在两套对外决策 API：一套 4 元组（应用主流程用）、一套 2 元组（strategy 用）。信心、分歧等新能力无法通过 strategy 层体现；「兼容层」是一个不完整的第二门面。

---

## 3. 隐藏耦合

### 3.1 魔法动作字符串

- 四种内部动作在多处以**字符串字面量**出现：
  - `decision_engine.scoring`：`"极度过热，禁买"`、`"强烈建议补仓"`、`"持有观望"`、`"考虑套利/减仓"`（见于 `_display_label`、`get_advice`、`get_signal_from_score`）。
  - `explanation_engine.structured_reasoning`：同上四个在 `_why_this_decision` 中。
  - `explanation_engine.reasons`：同上在 `get_reason_for_signal` 中。
  - `ui_dashboard.styling`：同上在 `_row_style_simple` 中（通过数据中的 `advice_type`）。
  - `decision_engine.daily_action`：同上在频率与准确率逻辑中。
  - `etf_data`：`"持有观望"` 等用于兜底。
- **没有统一的常量或枚举**。重命名或新增动作（如「轻仓试探」）需要全局搜索并在 6+ 个文件中协同修改；测试或类型系统无法约束唯一定义。

### 3.2 Regime 从未接入

- **market_regime** 是 `get_advice` 和 `compute_daily_action` 的可选参数，但**主应用中没有调用方传入**。结果是：
  - 文档与代码暗示「市场状态」会调节行为（如 risk_off → 更严阈值）。
  - 生产环境中该路径从未执行。要么是未完成功能（应明确标注并接入），要么是死代码（应删除），否则会误导阅读者和后续「为什么 regime 不起作用？」的排查。

### 3.3 数据行形态的隐式约定

- **etf_data** 构建的行依赖一整套隐式约定：`明日建议`、`建议理由`、`信心区间`、`信号分歧`、`信号分歧显示`、`建议类型` 等。**styling** 与 **main** 假定存在 `建议类型`、`信号分歧`、`溢价分位60d`、`样本极少` 等列且类型固定。该约定没有在单一位置（如 dataclass 或 schema）声明。增删或重命名列可能静默破坏样式或筛选，重构容易出错。

---

## 4. 误导性投资信号

### 4.1 「信心」暗示多于实际含义

- 界面展示**信心区间：高/中/低**。它仅由与当前结论相同的分数和风险等级推导而来。因此「高」实际含义是「模型分数高于（经风险调整的）阈值」，并非独立的可靠性度量（例如回测准确率、稳定性或数据质量）。用户可能把「高」理解为「这次结论更可靠」，而系统并未对该含义做量化。

### 4.2 「信号分歧」作为唯一的不确定性提示

- **信号分歧**在 `signal_disagreement_risk(signal_states) == "HIGH"` 时展示（例如 2–2 多空）。其他不确定性来源没有以同样方式呈现：例如数据缺失或过少（样本极少）、regime 不确定、波动率状态等。界面容易让人以为「无分歧 = 更可靠」，在数据薄弱或 regime 不清时这一推断并不成立。

### 4.3 措辞软化与内部逻辑

- 界面用**「偏多，可考虑补仓」**替代「强烈建议补仓」以降低确定性感。**底层逻辑**（阈值 7/4、2.5σ 否决、同一套分数公式）未变。因此只是**措辞**软化，并未在**决策**结构上更保守或更概率化。监管或用户仍可能将输出视为建议；改动是展示层面的，而非决策规则或风险披露的实质变化。

### 4.4 准确率页与「准确率」

- **信号准确率30d** 定义为：在固定 30 日窗口、固定 5 日前瞻下的方向正确率。该指标对周期与前瞻长度敏感，且不等于「这条建议对我是否适用」。在「明日建议」旁展示时若未明确说明周期、前瞻及不保证未来结果，容易被理解为「该策略准确率为 X%」，从而夸大数字含义。

---

## 5. 长期维护风险

### 5.1 新增动作或状态

- **新增动作（如「轻仓试探」）：**  
  需修改：`get_advice` 分支、`_display_label`、`_confidence_band`（若需要）、`_why_this_decision`、`get_reason_for_signal`、styling 的 `_row_style_simple`、daily_action 的频率/准确率逻辑以及相关 UI 文案。没有统一枚举或代码生成，漏改一处即可能导致行为或文案不一致。

### 5.2 修改阈值

- **示例：RSI 45/70。**  
  使用位置：`signal_engine.states.momentum_state`（状态）与 `decision_engine.scoring._score_momentum_rsi`（分数）。两处若只改一处，状态与分数可能脱节（例如状态为「中性」但分数仍为 2）。趋势（R² 0.2/0.4）、估值（25/50/75）、波动（1.0/3.0 ATR%）同理。

### 5.3 Regime 与解释的漂移

- 若后续有人**接入** market_regime（例如来自真实 regime 检测器），必须保证 `get_advice` 与 `explanation_engine.structured_reasoning`（REGIME_*_LABELS）对键（`risk_regime`、`liquidity`、`usd_trend`）及取值约定一致。目前没有共享类型或 schema；regime 字典是自由形态的约定。

### 5.4 strategy 再导出与旧 API

- **strategy** 暴露的是 `get_signal_from_score`（2 元组），而非 `get_advice`（4 元组）。仅存在于 4 元组路径上的能力（display_label、confidence_band、conflicting_signals）对使用 strategy 层的代码不可见。要么将 strategy 层弃用并把调用方迁到 decision_engine，要么扩展并同步 strategy API，否则代码库会长期维持两套决策「表面」，行为与维护成本都会分裂。

### 5.5 测试与重构

- 在魔法字符串且无共享常量的情况下，对「强烈建议补仓」或「偏多，可考虑补仓」做断言的**自动化测试**会很脆弱：重命名或拆分动作会破坏大量测试。若改为单一动作枚举（及单一展示文案映射），可减少重复并便于测试与修改。

---

## 6. 总结与建议

| 问题 | 严重程度 | 建议 |
|------|----------|------|
| 生产环境中从未传入 market_regime | 高 | 在 etf_data 中接入 regime 并文档化，或移除该参数及相关分支，避免死代码与误解。 |
| 6+ 个文件中出现魔法动作字符串 | 高 | 为内部动作引入单一枚举或常量模块，在 decision、explanation、styling、etf_data 中统一使用。 |
| 状态语义重复（states / signal_disagreement / labels） | 中 | 优先从 signal_engine（或共享词汇模块）导入规范的状态键/值，避免在其他处重复定义相同字符串。 |
| 解释引擎与决策/信号词汇强耦合 | 中 | 将约定（动作集合、状态键）文档化，或改为传入小型结构化载荷（如动作枚举 + 因子标签列表）而非原始 dict。 |
| 信心区间与分数/动作冗余 | 中 | 要么取消信心区间，要么用独立量定义（如历史命中率、分数分布宽度），并明确「信心」的含义。 |
| 两套解释 API（get_reason_for_signal vs explain_decision） | 低 | 合并或弃用其一：单一入口，可选接收完整上下文，同时返回简短理由与结构化解释。 |
| strategy 再导出与 decision_engine 不一致 | 低 | 将 strategy API 与主流程对齐（如返回相同 4 元组或小型结果对象），或明确弃用 strategy 供新代码使用。 |
| 数据行约定隐式 | 低 | 为「监控行」定义小型 schema 或 dataclass，使 styling 与 UI 依赖单一、文档化的形态。 |

**总体：** 分层以及「信号层不输出买卖」「解释层无业务依赖」在架构图中看起来清晰，但被未接线的 regime、重复的状态/动作字面量以及强隐式耦合削弱。优先处理高严重项（regime 接入或移除、动作常量、状态语义单一数据源）可在不重写的前提下降低隐藏耦合与维护风险。
