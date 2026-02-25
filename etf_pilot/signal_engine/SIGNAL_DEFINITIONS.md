# Signal Engine - 信号定义

## 总则

Signal Engine 描述**市场正在做什么**，而非**投资者应该做什么**。

- ❌ 不输出买卖决策
- ❌ 不计算聚合评分
- ❌ 不包含风险评估
- ❌ 不包含置信度逻辑

## 信号类别

### 1. Trend State（趋势状态）

**定义：** 描述价格的中长期方向性运动。

**状态值：**
- `UP` - 上升趋势：价格呈现明确的向上运动
- `DOWN` - 下降趋势：价格呈现明确的向下运动
- `SIDEWAYS` - 横盘震荡：价格无明显方向性，在区间内波动

**计算方法：**
- 基于线性回归的 R²（决定系数）和斜率（slope）
- R² >= 0.4 且 slope > 0 → `UP`
- R² >= 0.4 且 slope < 0 → `DOWN`
- R² < 0.4 或 slope ≈ 0 → `SIDEWAYS`
- 数据不足或无法计算 → `UNKNOWN`

**输入：**
- `r2`: 线性回归的 R² 值（0-1）
- `slope`: 线性回归的斜率

**输出：** `"UP" | "DOWN" | "SIDEWAYS" | "UNKNOWN"`

---

### 2. Momentum State（动量状态）

**定义：** 描述价格短期动能的强弱和方向。

**状态值：**
- `ACCELERATING` - 加速：价格动能强劲，可能超买或超卖后反弹
- `WEAKENING` - 减弱：价格动能疲弱，可能接近转折点
- `NEUTRAL` - 中性：价格动能在正常范围内

**计算方法：**
- 基于 RSI（相对强弱指标）
- RSI < 30 → `ACCELERATING`（超卖，可能反弹加速）
- RSI > 70 → `ACCELERATING`（超买，可能加速上涨）
- 30 <= RSI <= 45 → `WEAKENING`（动能减弱，偏弱）
- 55 <= RSI <= 70 → `WEAKENING`（动能减弱，偏强）
- 45 < RSI < 55 → `NEUTRAL`（中性）
- 数据不足或无法计算 → `UNKNOWN`

**输入：**
- `rsi`: RSI 值（0-100）

**输出：** `"ACCELERATING" | "WEAKENING" | "NEUTRAL" | "UNKNOWN"`

---

### 3. Valuation State（估值状态）

**定义：** 描述当前价格相对于历史水平的估值位置。

**状态值：**
- `CHEAP` - 便宜：当前价格处于历史低位
- `FAIR` - 合理：当前价格处于历史中位
- `EXPENSIVE` - 昂贵：当前价格处于历史高位

**计算方法：**
- 基于溢价率的 60 日分位数（percentile）
- 分位数 <= 25 → `CHEAP`
- 25 < 分位数 <= 75 → `FAIR`
- 分位数 > 75 → `EXPENSIVE`
- 数据不足或无法计算 → `UNKNOWN`

**输入：**
- `premium_pctile_60`: 溢价率在 60 日历史中的分位数（0-100）

**输出：** `"CHEAP" | "FAIR" | "EXPENSIVE" | "UNKNOWN"`

---

### 4. Volatility State（波动率状态）

**定义：** 描述价格波动的剧烈程度。

**状态值：**
- `LOW` - 低波动：价格波动较小，市场相对稳定
- `NORMAL` - 正常波动：价格波动在正常范围内
- `HIGH` - 高波动：价格波动剧烈，市场不稳定

**计算方法：**
- 基于 ATR%（平均真实波幅占收盘价的百分比）
- ATR% <= 1.0 → `LOW`
- 1.0 < ATR% < 3.0 → `NORMAL`
- ATR% >= 3.0 → `HIGH`
- 数据不足或无法计算 → `UNKNOWN`

**输入：**
- `atr_pct`: ATR / 收盘价 * 100

**输出：** `"LOW" | "NORMAL" | "HIGH" | "UNKNOWN"`

---

## 输出格式

Signal Engine 的统一输出格式：

```python
{
    "trend": "UP" | "DOWN" | "SIDEWAYS" | "UNKNOWN",
    "momentum": "ACCELERATING" | "WEAKENING" | "NEUTRAL" | "UNKNOWN",
    "valuation": "CHEAP" | "FAIR" | "EXPENSIVE" | "UNKNOWN",
    "volatility": "LOW" | "NORMAL" | "HIGH" | "UNKNOWN"
}
```

## 状态转换规则

### 数据有效性检查

所有状态计算函数必须：
1. 检查输入是否为 `None`
2. 检查输入是否为有限数值（`math.isfinite()`）
3. 对于无效输入，返回 `UNKNOWN` 状态

### 边界处理

- 边界值应明确归属（使用 `<=` 或 `>=` 而非 `<` 或 `>`）
- 边界归属规则应在代码注释中明确说明

---

## 与旧版本的兼容性

旧版本的状态值（如 `oversold`, `strong_up`, `cheap` 等）将在内部映射到新状态值，但 Signal Engine 的公共 API 将使用新的状态值。
