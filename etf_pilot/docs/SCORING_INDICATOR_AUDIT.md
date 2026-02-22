# Scoring Indicator Audit — Factor Exposure & Redundancy

## 1. Original indicators used in scoring (before audit)

| Indicator | Input | Score range | Current bucket |
|-----------|--------|-------------|-----------------|
| RSI | last_row["RSI"] | 0 ~ 1.33 | tech (momentum) |
| Bias_MA20 | (close - MA20) / MA20 * 100 | 0 ~ 1.33 | tech (momentum) |
| Bias_MA200 | (close - MA200) / MA200 * 100 | 0 ~ 1.34 | tech (trend position) |
| R² (180d regression) | linear regression fit | 0 ~ 3 (with slope) | trend |
| Slope (180d regression) | linear regression slope | 0 ~ 3 (with R²) | trend |
| Premium 60d percentile | 溢价分位60d | 0 ~ 3 | premium (valuation) |
| Premium deviation | (current - mean22) / std22 | veto only (>2.5) | valuation (safety) |

**Total score:** tech 4 + trend 3 + premium 3 = 10.

---

## 2. Grouping by underlying factor exposure

### Trend (directional persistence / long-term direction)
- **R² + slope** — 180d linear regression: fit (R²) and direction (slope). Pure trend strength and direction.
- **Bias_MA200** — Price vs 200d average. Measures “where price is” relative to long-term trend.

**Redundancy:** High correlation. When trend is strong and up (high R², slope > 0), price is often above MA200 (positive Bias_MA200). When trend is down, price is often below MA200. Both capture “trend”; one is regression-based, one is level vs MA. **Keep one:** R² + slope (more interpretable: fit + direction). **Remove from score:** Bias_MA200.

### Momentum (short-term speed / overbought–oversold)
- **RSI** — Rate of price changes over 14d; oversold/overbought.
- **Bias_MA20** — (Close - MA20) / MA20; short-term deviation from 20d average.

**Redundancy:** Correlated. In uptrends, high RSI often coincides with positive Bias_MA20; in mean reversion both reward “not overbought” and “near or below MA20”. Both are short-horizon. **Keep one:** RSI (standard, single momentum signal). **Remove from score:** Bias_MA20.

### Valuation (relative cheapness / premium)
- **Premium 60d percentile** — Where current premium sits vs last 60d. Low = cheap, high = expensive.
- **Premium deviation** — Z-score vs 22d; used only as veto (>2.5 = 极度过热，禁买). Not a score component.

**Redundancy:** None. One level (percentile), one safety (deviation veto). **Keep both:** percentile in score, deviation as veto only.

### Volatility (uncertainty / range)
- **None in score.** ATR and Bollinger exist in codebase but are not used in scoring.

**Gap:** Volatility carries different information (regime risk, not trend/momentum/valuation). **Add one:** ATR% (ATR/close × 100) so that high vol reduces score, low vol is neutral/slight positive.

---

## 3. Correlated pairs and action

| Pair | Correlation / overlap | Action |
|------|------------------------|--------|
| R²+slope vs Bias_MA200 | Both trend; R²+slope = fit+direction, Bias_MA200 = level vs long-term MA | **Drop Bias_MA200** from score |
| RSI vs Bias_MA20 | Both short-term; RSI = change, Bias_MA20 = level vs MA20 | **Drop Bias_MA20** from score |
| Premium pctile vs premium deviation | Different roles (level vs extreme) | Keep both (pctile in score, deviation as veto) |

---

## 4. Target factor structure (one indicator per factor)

| Factor | Single indicator | Score weight | Rationale |
|--------|-------------------|--------------|-----------|
| **Trend** | R² + slope (180d) | 3 | Directional persistence; no second trend measure. |
| **Momentum** | RSI | 2 | One short-term momentum/overbought signal. |
| **Valuation** | Premium 60d percentile | 3 | Relative premium level. |
| **Volatility** | ATR% (ATR/close × 100) | 2 | Distinct risk/regime signal. |

**Total:** 3 + 2 + 3 + 2 = 10.  
**Veto unchanged:** premium deviation > 2.5 → 极度过热，禁买.

---

## 5. Indicators kept for display only (not in score)

- **Bias_MA20, Bias_MA60, Bias_MA200** — Still computed and shown in UI; no longer inputs to `calculate_score`.
- **距一年高% / 距一年低%** — Display only; not used in score (would overlap with momentum/trend if added).

---

## 6. Volatility scoring rule (ATR%)

- **ATR%** = ATR(14) / close × 100.
- Low ATR% (e.g. &lt; 1.5): calm regime → neutral/slight positive (2).
- High ATR% (e.g. &gt; 3): high uncertainty → lower score (0).
- Mid: linear or step in between (e.g. 1).

Thresholds are configurable in `decision_engine/scoring.py`.
