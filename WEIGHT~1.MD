# WEIGHT CONTROL KNOWLEDGE

## What is the Weight Test?
The weight test measures capital concentration in a single stock. In WorldQuant BRAIN, the hard limit is **10% of total book size**. An alpha fails if:
- Any single stock holds ≥10% of total alpha weight for a significant number of days, OR
- Too few stocks are assigned weight (e.g., long or short side < 10 stocks, total < 20 stocks)

**Our pipeline rejects any alpha with weight > 20% immediately — do not generate such expressions.**

---

## Root Causes of High Weight

### 0. Over-complexity (often overlooked)
Using too many operators or datafields can INCREASE weight concentration and overfitting:
- Chaining many operators narrows the set of stocks that receive valid (non-NaN) output → weight concentrates on fewer stocks
- Using rare/low-coverage datafields in combination multiplies NaN gaps across fields → even fewer stocks survive
- Complex expressions that "select" very specific stocks naturally concentrate weight on those stocks

**When weight is high AND your expression is complex: SIMPLIFY FIRST.**
- Remove 1-2 operators from the chain — fewer transformations = more stocks with valid output
- Replace a rare/low-coverage datafield with a high-coverage equivalent (e.g., swap `adv5` for `volume`, swap `analyst_target` for `close`)
- Break a multi-signal combination into a simpler 2-field expression
- Use `rank()` at fewer intermediate steps — one final `rank()` on the whole expression is often better than multiple nested `rank()` calls

Rule of thumb: if your expression has more than 4-5 nested operator levels or more than 3 datafields AND weight is failing, simplify before adding more operators.

### 1. Low Coverage (most common)
When a data field has many NaN values, few stocks receive non-NaN weights → remaining stocks carry concentrated weights.

**Fixes:**
- `ts_backfill(field, 10)` — for daily/weekly updated MATRIX fields (default)
- `ts_backfill(field, 60)` — for quarterly fundamental data
- `ts_backfill(field, 2)` — if data is missing for only 1 day
- `group_count(is_nan(a), market) > 40 ? a : nan` — guard against abnormal coverage drops in short horizon
- You can also detect NaN manually: `is_nan()`, `last_diff_value()`, `days_from_last_change()`
- NOTE: ts_backfill only works on MATRIX fields, NOT EVENT fields

### 2. Data Distribution / Outliers
When a few stocks have extreme values, they dominate the portfolio weight.

**Fixes (use available operators — paraphrase if exact name unavailable):**
- `rank(x)` — transforms to uniform distribution [0,1], best for balancing long-short count
- `group_rank(x, group)` — rank within sector/industry for neutralization
- `zscore(x)` — standardize to mean=0, std=1
- `group_zscore(x, group)` — zscore within group
- `ts_scale(x, d)` — scale time-series to [-1, 1] range
- `signed_power(x, p)` with 0 < p < 1 — soften extreme values (e.g., `signed_power(x, 0.5)`)
  → If `signed_power` is not available, approximate with: `sign(x) * pow(abs(x), 0.5)`
- `log(abs(x) + 1) * sign(x)` — log-compress to reduce outlier magnitude
- `ts_decay_linear(x, d)` — smooth time-series to reduce day-to-day spikes

**"winsorize" / truncation:**
- If `winsorize` operator is not available: use `min(max(x, low), high)` pattern, or apply `rank()` followed by `ts_scale()` to achieve similar effect
- Setting truncation=0.05 in simulation settings also caps weight at 5%

---

## Techniques to Reduce Weight Concentration

### Priority order (most impactful first):

**Step 1 — Normalize first:**
Always apply `rank()` or `zscore()` to your primary signal before combining.
```
rank(ts_mean(signal, 20))
```

**Step 2 — Group neutralization:**
Apply group-level operators to ensure balance across sectors/industries:
```
group_rank(signal, sector)
group_zscore(signal, industry)
group_mean(signal, market)
```

**Step 3 — Soften magnitude:**
If weight is still concentrated, compress signal magnitudes:
```
signed_power(rank(signal), 0.5)      # soften with fractional power
ts_scale(rank(signal), 20)           # scale within rolling window
```

**Step 4 — Fix coverage gaps:**
Ensure enough stocks receive non-NaN weights:
```
ts_backfill(fundamental_field, 10)
group_count(is_nan(a), market) > 40 ? a : nan
```

**Step 5 — Smooth via decay:**
Reduce day-to-day weight fluctuations:
```
ts_decay_linear(rank(signal), 5)
ts_mean(rank(signal), 10)
```

---

## Simplification Decision Tree (use when weight > 10%)

```
Is the expression longer than 4 operator levels OR has 3+ datafields?
├── YES → Try simplification FIRST before adding more operators:
│         1. Remove the outermost/most complex operator layer
│         2. Replace lowest-coverage datafield with a high-coverage equivalent
│         3. Reduce to core 2-field signal: rank(field_A) - rank(field_B)
│         Then re-check weight. If still failing, apply rank()/group_rank().
└── NO  → Expression is already simple. Weight issue is from coverage or outliers.
          Apply: rank(), ts_backfill(field, 10), group_zscore(x, sector)
```

High-coverage datafields (prefer these when weight is a problem):
- Price/volume: `close`, `open`, `volume`, `returns`, `vwap`, `adv20`
- These fields have near-100% coverage on TOP3000 universe

Low-coverage datafields (use carefully, always with ts_backfill):
- Fundamentals: `eps`, `revenue`, `book_value`, `debt` — quarterly updates
- Analyst: `target_price`, `rating` — sparse coverage
- Alternative: sentiment, news scores — may be missing for many stocks

## What NOT to Do
- Do NOT overuse `ts_backfill` with very large windows (>60 days) — hurts performance
- Do NOT rely on truncation alone to pass the weight test — it's a defensive tool, not a solution
- Do NOT keep adding operators to fix weight — more operators often make weight WORSE
- If ALL techniques are tried and weight still fails → abandon this alpha idea and start fresh. Weight-failing ideas have limited capacity.

---

## Operator Paraphrasing Guide
Some operators may not be available on your account. Use these equivalents:

| Unavailable | Use instead |
|---|---|
| `winsorize(x, a, b)` | `rank(x)` or `ts_scale(x, d)` |
| `signed_power(x, p)` | `sign(x) * pow(abs(x), p)` |
| `group_backfill(x, g)` | `ts_backfill(x, 10)` per group logic |
| `hump(x)` | `ts_mean(x, 5)` or `ts_decay_linear(x, 5)` |

---

## Summary Rule
**If weight > 10% (BRAIN limit) or > 20% (our pipeline limit):**
1. Apply `rank()` or `zscore()` to normalize
2. Wrap low-coverage MATRIX fields in `ts_backfill(x, 10)`
3. Apply `group_rank(x, sector)` for group balance
4. Use `signed_power(rank(x), 0.5)` to soften
5. If still failing → change alpha idea entirely
