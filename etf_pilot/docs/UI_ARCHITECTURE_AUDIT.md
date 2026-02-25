# ETF Pilot — 最终 UI 架构审计

## 目标效果（四层与后端一一对应）

```
ETF PILOT

GLOBAL MARKET STATE
──────────────────
Signal Layer

RISK ENVIRONMENT
──────────────────
Risk Layer

SYSTEM CONFIDENCE
──────────────────
Confidence Layer

PORTFOLIO ACTION
──────────────────
Decision Layer
```

---

## 1. UI ↔ 后端映射

| UI 区块（英文标题） | UI 层名称 | 后端引擎 | 数据来源（每行） |
|--------------------|-----------|----------|------------------|
| **GLOBAL MARKET STATE** | Signal Layer | `signal_engine` | `signal_states`, `state_stability` |
| **RISK ENVIRONMENT** | Risk Layer | `risk_engine` | `risk_result` |
| **SYSTEM CONFIDENCE** | Confidence Layer | `confidence_engine` | `confidence_result` |
| **PORTFOLIO ACTION** | Decision Layer | `decision_engine` | `decision` |

- 每个 UI 区块**仅**消费对应引擎的输出，不暴露原始指标、不展示聚合分数、不与其它层混用数据。
- 推理顺序固定：Signal → Risk → Confidence → Decision，与后端 `compute_daily_action_v2` 调用顺序一致。

---

## 2. 后端四层逻辑（简要）

| 层 | 引擎入口 | 输出（供 UI） |
|----|----------|----------------|
| 1. Signal | `signal_engine.states.get_signal_states` | `trend`, `momentum`, `valuation`, `volatility`；稳定性由 risk 的 `rapid_transitions` 反推 |
| 2. Risk | `risk_engine.assessment.evaluate_risk` | `risk_level`, `risk_flags`, `components` |
| 3. Confidence | `confidence_engine.assessment.calculate_confidence` | `confidence`, `confidence_reason` |
| 4. Decision | `decision_engine.decision.make_decision` | `action`, `aggressiveness`, `reason_tags` |

数据流：`etf_data.build_monitor_table_advanced` 内对每只 ETF 调用 `compute_daily_action_v2`，得到 `signal_states`, `risk_result`, `confidence_result`, `decision`，写入行；UI 只读这些字段并交给对应 layer 组件渲染。

**溢价率/历史净值**：四层中仅 **Signal 层的估值状态**（valuation）依赖溢价 60 日分位（`premium_pctile_60`）。若关闭溢价拉取（`config.settings.ENABLE_PREMIUM_FETCH = False`），不请求历史净值与实时溢价，估值恒为「未知」，可显著加快启动。

---

## 3. 前端实现与审计结论

| 项目 | 位置 | 审计结果 |
|------|------|----------|
| 页面标题 | `main.py` | 使用「ETF PILOT」与四层标题一致 |
| 四层标题与分隔 | `etf_drilldown.py` | 使用 GLOBAL MARKET STATE / RISK ENVIRONMENT / SYSTEM CONFIDENCE / PORTFOLIO ACTION + ────────────────── + 层名 |
| Signal 内容 | `signal_layer_ui.render_signal_layer_cards` | 仅展示状态标签与稳定性，无 RSI/MA/分数 ✅ |
| Risk 内容 | `risk_layer_ui.render_risk_layer_cards` | 仅展示风险等级与风险来源，无概率数字 ✅ |
| Confidence 内容 | `confidence_layer_ui.render_confidence_layer_cards` | 仅展示置信度与一致/冲突，无百分比 ✅ |
| Decision 内容 | `decision_layer_ui.render_decision_layer_cards` | 仅展示操作倾向、激进程度、推理依据，无紧迫话术 ✅ |
| 无 Tab 割裂 | `main.py` | 单一纵向流 + 选择标的 → drill-down，无多 Tab ✅ |
| Drill-down 不重复全局逻辑 | `etf_drilldown.py` | 仅接收 `sel_row`，不拉数、不筛列表 ✅ |

---

## 4. 命名与展示规范

- **页面级**：应用标题统一为 **ETF PILOT**（或副标题说明「四层推理流」）。
- **区块级**：四块固定为上述英文全大写标题 + 下划线分隔 + 层名（Signal Layer / Risk Layer / Confidence Layer / Decision Layer）。
- **层内**：各 layer 模块不出现其它层的标题或数据；决策层不出现「买入/卖出」等确定性交易话术。

---

## 5. 当前实现（与目标一致）

- **入口**：`main.py` 标题为 **跨境 ETF 决策辅助仪表盘**，选择标的后进入 `render_etf_drilldown`。
- **Drill-down 四块**（`etf_drilldown.py`）：
  1. `**GLOBAL MARKET STATE**` + `──────────────────` + `*Signal Layer*` → `render_signal_layer_cards`
  2. `**RISK ENVIRONMENT**` + `──────────────────` + `*Risk Layer*` → `render_risk_layer_cards`
  3. `**SYSTEM CONFIDENCE**` + `──────────────────` + `*Confidence Layer*` → `render_confidence_layer_cards`
  4. `**PORTFOLIO ACTION**` + `──────────────────` + `*Decision Layer*` → `render_decision_layer_cards`

---

## 6. 审计日期与版本

- 审计日期：当前
- 适用范围：`ui_dashboard/`（main、etf_drilldown、signal/risk/confidence/decision_layer_ui）与 `etf_data` 中四层数据写入。
