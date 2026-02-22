# ETF Pilot 分层架构

重构后的六层架构，每层单一职责，业务逻辑与 UI 分离。

## 新文件夹结构

```
etf_pilot/
├── config/                          # 配置（非业务层）
│   ├── __init__.py
│   ├── settings.py
│   ├── categories.py
│   └── asset_types.py
│
├── market_regime/                   # 1. 市场状态与资产性格
│   ├── __init__.py
│   ├── classification.py           # Core/Tactical 分类（波动率+回撤+宽基关键词）
│   └── trend.py                     # 趋势/震荡分类（R²+斜率）
│
├── signal_engine/                   # 2. 信号与指标（仅产出状态/概率，不产出买卖建议）
│   ├── __init__.py
│   ├── indicators.py                # RSI、布林带、MA、ATR、乖离、1年高低
│   ├── states.py                    # 动量/趋势/估值/波动状态（oversold、strong_up、cheap、low 等）
│   └── signals.py                   # 网格/方向状态（below_center、bullish、addon_opportunity 等）
│
├── risk_engine/                     # 3. 风险（Decision Engine 依赖此处）
│   ├── __init__.py
│   ├── drawdown.py                  # 兼容：15% 回撤后账户金额
│   ├── volatility_regime.py         # 波动率状态 → LOW/MEDIUM/HIGH
│   ├── drawdown_risk.py             # 距高回撤 + 15% 极端模拟
│   ├── signal_disagreement.py       # 信号分歧 → LOW/MEDIUM/HIGH
│   ├── concentration_risk.py       # 集中度 → LOW/MEDIUM/HIGH
│   └── assessment.py                # evaluate_risk() 汇总 → level
│
├── decision_engine/                  # 4. 决策（组合 信号状态 + 市场状态 + 风险 → 买卖建议）
│   ├── __init__.py
│   ├── scoring.py                   # state_to_score、溢价偏离度、get_advice(states, risk, regime)
│   └── daily_action.py              # 每日建议、建议操作频率、信号准确率 30d
│
├── explanation_engine/               # 5. 说明与理由
│   ├── __init__.py
│   ├── reasons.py                  # 建议理由短句（兼容无 regime/signals 的入口）
│   └── structured_reasoning.py     # 根据 regime、signals、risk、decision 生成结构化理由（无分数）
│
├── ui_dashboard/                    # 6. 界面
│   ├── __init__.py
│   ├── main.py                      # Streamlit 入口：布局、Tab、缓存，无业务逻辑
│   └── styling.py                  # 表格行样式、溢价/RSI/明日建议样式、类别筛选与排序
│
├── data/                            # 运行时数据目录（不变）
├── etf_data.py                      # 数据获取与编排：列表、日线、净值、溢价、监控表构建
├── main.py                          # 应用入口（调用 ui_dashboard）
├── strategy/                        # 兼容保留：对外 re-export 各层
│   ├── __init__.py
│   ├── asset_type.py
│   ├── constants.py
│   ├── classification.py           # → market_regime
│   ├── signals.py                   # → signal_engine
│   └── scoring.py                   # → decision_engine
├── requirements.txt
└── README.md
```

## 层职责一览

| 层 | 职责 | 不包含 |
|----|------|--------|
| **market_regime** | 资产分类（Core/Tactical）、趋势 vs 震荡性格 | 具体买卖信号、评分 |
| **signal_engine** | 技术指标计算、仅产出状态/概率（如 oversold、strong_up、bullish），不产出买卖建议 | 评分、最终建议、UI |
| **risk_engine** | 波动率状态、回撤、信号分歧、集中度 → 风险等级 LOW/MEDIUM/HIGH | 信号、决策、UI |
| **decision_engine** | 组合信号状态 + **风险引擎等级** + 市场状态 → 买卖建议；依赖 risk_engine | 理由文案、UI、数据拉取 |
| **explanation_engine** | 根据 regime、signals、risk、final decision 生成结构化、可读的「为什么」说明（不输出分数） | 评分计算、决策逻辑、UI 样式 |
| **ui_dashboard** | 页面结构、组件、缓存、表格/图表展示与样式 | 业务规则、指标计算、决策逻辑 |

## 依赖方向

- `ui_dashboard` → `etf_data`（拉表、图表数据）、`config`、`risk_engine`（仅侧栏回撤展示）
- `etf_data` → `config`、`market_regime`、`signal_engine`、`decision_engine`、`explanation_engine`（通过 decision_engine）
- `decision_engine` → `risk_engine`（风险等级）、`signal_engine`（状态）、`explanation_engine`（理由）
- `explanation_engine` → 无业务依赖（仅接收决策结果）
- `signal_engine` → `config`
- `market_regime` → `config`
- `risk_engine` → 无

## 重构原则

- 不改变现有功能与行为，仅移动职责。
- 每层单一职责。
- UI 文件不包含业务逻辑（样式规则集中在 `ui_dashboard/styling.py`，由数据驱动）。
