# A 股跨境 ETF 监控工具

基于 Python + Streamlit + AkShare 的跨境 ETF 监控与回测工具：支持多类别筛选、Core/Tactical 信号、多因子轮动与等权再平衡回测。

---

## 功能概览

- **实时雷达**：按类别筛选 ETF，拉取日线并计算 MA/RSI/布林带、偏离度、追高提示、补仓建议与买卖信号（Core / Tactical 区分）。
- **策略详情**：表格展示全量标的的类型、最新价、涨跌幅、MA、RSI、偏离度、信号与建议仓位。
- **个股深度分析**：选择单只 ETF，查看 K 线、均线、布林带与成交量。
- **策略回测**：**跨资产等权动态再平衡**——自选多只标的等权分配，每两周检查、权重偏离 ±3% 触发再平衡；对比「再平衡策略净值」与「所选标的简单平均不调仓」净值，图中红三角标记再平衡时刻。

---

## 环境要求

- **Python 3.9+**
- 依赖见 `requirements.txt`

---

## 安装

```bash
cd etf_pilot
pip install -r requirements.txt
```

---

## 配置 ETF 列表

将 ETF 列表放到 **`data/ETF汇总.xlsx`** 中，需包含列：

- **代码**：ETF 代码（如 513100、518880）
- **名称**：ETF 名称（如 纳指ETF、黄金ETF）
- **指数简称**（可选）：用于类别筛选
- **类型**（可选）：Core / Tactical，不填则按名称自动分类

若未放置该文件，首次运行会在 `data` 目录下生成示例 Excel，可在此基础上增删改。

---

## 运行

在项目根目录执行：

```bash
streamlit run main.py
```

浏览器会打开监控页面。建议使用 **Streamlit 1.33+**（精选池多选时不会跳回第一个 Tab）。

---

## 策略回测说明

- **精选池配置**：在「策略回测」Tab 中可多选参与等权组合的标的；默认 5 只（纳指/标普/黄金/日经/标普油气），也可从当前加载的 ETF 列表中自选。
- **再平衡规则**：初始资金 50 万，所选 N 只各 1/N 仓位；每约 10 个交易日检查一次，若某标的权重偏离 1/N 超过 **±3%**，则卖出超配、买入欠配，使各只回到等权。
- **成本**：佣金万五（0.0005），最低 0 元。
- **基准**：所选标的「买入持有等权」净值（不调仓）。

---

## 项目结构

```
etf_pilot/
├── main.py                 # Streamlit 入口（四 Tab：雷达 / 详情 / 深度 / 回测）
├── etf_data.py             # 数据加载、AkShare 拉取、MA/RSI/布林带、等权 panel
├── config/
│   ├── settings.py        # 均线/RSI/回测/等权再平衡等参数
│   ├── categories.py      # 类别关键词（用于筛选）
│   ├── asset_types.py     # Core 关键词
│   ├── equal_weight_pool.py  # 等权回测默认精选池（5 只）
│   └── rsr_groups.py      # 多因子轮动分组（当前回测未用）
├── strategy/
│   ├── signals.py         # Core/Tactical 买卖信号、偏离度、补仓建议
│   ├── backtest.py        # 单标的 ATR/排名回测（可选）
│   ├── rsr_backtest.py    # 多因子分类轮动回测（可选）
│   ├── equal_weight_backtest.py  # 等权动态再平衡回测
│   ├── classification.py  # 自动 Core/Tactical 分类
│   ├── asset_type.py      # 资产类型常量
│   └── constants.py       # 偏离度、补仓步长等常数
├── data/
│   ├── ETF汇总.xlsx       # ETF 列表（需自备或自动生成）
│   └── etf_classification.json  # 分类缓存（可选）
├── requirements.txt
└── README.md
```

---

## 免责声明

本工具仅供学习与研究，不构成任何投资建议。实盘决策请自行判断并承担风险。
