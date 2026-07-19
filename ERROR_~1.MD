# WorldQuant BRAIN Error Messages — Know Before You Simulate

Study these errors carefully. Every error listed below has been seen in production.
Your goal is to write expressions that NEVER trigger these errors.

---

## SYNTAX ERRORS (most common — caused by malformed expressions)

### "Unexpected end of input"
**Cause:** Missing closing parenthesis `)` or missing semicolon `;`
**Rule:** Every `(` must have a matching `)`. Count them before submitting.
**Bad:**  `rank(sales/assets`         ← missing `)`
**Good:** `rank(sales/assets)`

### "Expression cannot be empty"
**Cause:** You assigned the alpha to a variable but never returned it.
**Rule:** If you use `variable = expr;` you MUST add the variable name on its own line at the end.
**Bad:**  `alpha = -ts_delta(close, 5);`
**Good:** `alpha = -ts_delta(close, 5); alpha`

### "Got invalid value for attribute 'lookback', must be constant or string"
**Cause:** You used a non-constant value as the lookback window, OR put parameters in the wrong order.
**Rule:** Lookback must always be a literal integer (e.g., 5, 10, 20). Never use a data field as lookback.
**Bad:**  `ts_rank(sales/assets, days_from_last_change(sales))`
**Good:** `ts_rank(sales/assets, 20)`

### "Required attribute 'lookback' must have a value"
**Cause:** You called a time-series operator without specifying the lookback period.
**Rule:** All ts_* operators require an explicit integer lookback as their last argument.
**Bad:**  `ts_mean(close)`
**Good:** `ts_mean(close, 20)`

### "Invalid number of inputs: X, should be exactly Y input(s)"
**Cause:** You passed the wrong number of arguments to an operator.
**Rule:** Always check the exact signature. group_mean takes exactly 3 args: (field, decay, group).
**Bad:**  `group_mean(sales/assets, market)`             ← only 2 args
**Bad:**  `group_mean(sales/assets, 1, market, 1)`       ← 4 args
**Good:** `group_mean(sales/assets, 1, market)`          ← correct: 3 args

### "Got invalid input at index 1, expected a date in format 'YYYY-MM-DD'"
**Cause:** A date argument was passed as a number instead of a quoted string.
**Good:** Use `"2020-01-01"` (with quotes), not `20200101`

---

## DATA FIELD ERRORS

### "Attempted to use unknown variable 'xxx'"
**Cause:** The data field name is misspelled, or it does not exist in this region/universe.
**Rule:** Only use exact field IDs from the "Data Field Context" section provided. Do NOT invent names.
**Tip:** If a field appears in blue text in the Brain editor, it is recognized correctly.

**CRITICAL — Forbidden invented variables:** The following identifiers do NOT exist in WQ Brain and will always cause this error:
- `last_result` — does NOT exist. There is no way to reference the previous simulation result inside an expression.
- `prev_close`, `prev_price`, `yesterday` — use `ts_delay(close, 1)` instead.
- `portfolio`, `weight`, `position` — portfolio-level variables are not accessible in alpha expressions.
- Any camelCase name like `stockRank`, `sectorReturn` — WQ fields use snake_case only.
- Any name you invented that is not literally in the "Data Field Context" list provided.

**Fix:** Replace with an exact field ID from the Data Field Context. If you want "previous value", use `ts_delay(field, N)`. If you want "change", use `ts_delta(field, N)`.

### "Invalid data field 'XXX'"
**Cause:** The field is a DECM data field not available in the current simulation context.

### "Grouping data used outside of group operator"
**Cause:** You used a grouping variable (sector, industry, market) inside a non-group operator.
**Rule:** Grouping variables can ONLY be used as arguments to group_* operators.
**Bad:**  `ts_delta(industry, 5)`       ← industry is a group, not a matrix field
**Good:** `group_rank(close, 1, industry)`

### "Incompatible unit for input at index … expected … found …"
**Cause:** Arithmetic between two fields with different units (e.g., price × volume).
**Rule:** Apply `rank()` to each field first to make them unitless before combining.
**Bad:**  `close + adv20`
**Good:** `rank(close) + rank(adv20)`

---

## VECTOR / MATRIX TYPE ERRORS

### "Operator X does not support event inputs"
**Cause:** You applied a MATRIX operator (e.g., ts_backfill, rank, ts_mean) to an EVENT type field.
**Rule:** EVENT fields CANNOT use ts_backfill, rank, ts_mean, etc.
  - For EVENT fields: use `ts_sum(event_field, window)` or `ts_count(event_field, window)`
  - Check field type in "Data Field Context" — if type=EVENT, never use MATRIX operators on it

### "Please check if you are using vector data field correctly"
**Cause:** Mixed VECTOR and MATRIX data without proper conversion, OR used matrix operator on vector data.
**Rules:**
  - Do NOT use MATRIX data fields with vector operators (vec_avg, vec_sum)
  - Do NOT use VECTOR data fields directly with MATRIX operators (rank, ts_mean, etc.)
  - To use a VECTOR field in a MATRIX context: first apply `vec_avg(vector_field)` or `vec_sum(vector_field)`

### "Your simulation probably took too much resource"
**Cause 1:** Expression is too complex — too many nested operators or large datasets.
**Cause 2:** Used a VECTOR data field without a vector operator.
**Fix:** Simplify the expression. Check field types. If using a VECTOR field, wrap it with vec_avg() first.

---

## GROUP INDEX ERRORS

### "Illegal group index value, cannot exceed number of elements"
**Cause:** The group index is not dense (e.g., values like [0, 5, 8, 26, 107] with gaps).
**Fix:** Use `densify(group)` instead of `group` directly.
**Good:** `group_rank(close, 1, densify(industry))`

### "Illegal group index value, cannot be negative"
**Cause:** Negative group index value.
**Fix:** Use `densify(group)` to ensure non-negative dense indices.

---

## LOOKBACK / HISTORY ERRORS

### "Cumulative lookback of expression exceeds available history"
**Cause:** Nested time-series operators whose lookbacks add up to more than available data history.
**Rule:** The cumulative lookback = sum of all nested ts_* lookbacks. Keep total under ~500 days.
**Bad:**  `ts_rank(ts_mean(close, 250), 250)`   ← cumulative lookback = 500 (borderline)
**Good:** `ts_rank(ts_mean(close, 20), 20)`      ← cumulative lookback = 40

---

## SUBMISSION ERRORS (for reference — pipeline handles these separately)

### "Found unused variables/data fields/operators 'b', 'a', 'c'"
**Cause:** Variables defined but never used in the final expression.
**Rule:** Every variable you define with `var = ...;` must be used in subsequent lines.
**Fix:** Remove unused lines or make sure all intermediate variables contribute to the final result.

---

## SYNTAX CHECKLIST — Run through this before every expression:

1. [ ] Every `(` has a matching `)` — count them: opening = closing
2. [ ] All `ts_*` operators have an explicit integer lookback argument
3. [ ] All group_* operators have exactly the right number of arguments
4. [ ] No grouping variables (sector, industry, market) used outside group_* operators
5. [ ] No EVENT type fields used with ts_backfill, rank, ts_mean — use ts_sum/ts_count instead
6. [ ] No VECTOR fields used directly with MATRIX operators — wrap with vec_avg() first
7. [ ] If you used `var = expr;`, the variable name appears alone on the last line
8. [ ] All datafield names match exactly what is in the "Data Field Context" — no typos
9. [ ] Lookback arguments are integer constants, not data fields or expressions
10. [ ] No arithmetic between fields with different units — apply rank() first
