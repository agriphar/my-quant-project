# A 股跨境 ETF 监控工具

基于 Python + Streamlit + AkShare 的跨境 ETF 监控工具，可读取自选 ETF 列表、拉取近 30 日日线、计算 MA5/MA20，并给出简单的持有/减仓信号。

## 环境要求

- Python 3.9+
- 依赖见 `requirements.txt`

## 安装

```bash
pip install -r requirements.txt
```

## 配置 ETF 列表

将你的 ETF 列表放到 **`data/ETF汇总.xlsx`** 中，需包含两列：

- **代码**：ETF 代码（如 513100、513500）
- **名称**：ETF 名称（如 纳指ETF、标普500ETF）

若未放置该文件，首次运行会自动在 `data` 目录下生成一份示例 Excel（含若干跨境 ETF），可直接在此基础上增删改。

## 运行

在项目目录下执行：

```bash
streamlit run main.py
```

浏览器会打开监控页面，表格中展示：**最新价、涨跌幅、MA5、MA20、信号**。  
**信号规则**：当前价 ≥ MA20 为 **持有**，跌破 MA20 为 **减仓**。

## 项目结构

```
etf_pilot/
├── main.py          # Streamlit 入口
├── etf_data.py      # 数据加载、AkShare 拉取、MA 与信号计算
├── data/
│   └── ETF汇总.xlsx # ETF 列表（代码、名称）
├── requirements.txt
└── README.md
```
