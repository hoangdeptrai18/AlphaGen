# AlphaInsight Knowledge Base
# Generated: 2026-07-15 | Search policy: population-based / ACO-guided
# Empirical base: 3 optimization pairs (1 clean single-change pair)

---

## PART 0 — HOW TO SEARCH (read this before anything else)

You are ONE ant in a colony, not a solo optimizer. Every expression you emit is a
*path* through a graph of (datafield × operator × parameter). The colony converges
by depositing pheromone on paths that raise Fitness — NOT by any single agent
finding the answer alone.

### The prime directive: never brute-force

Brute force = re-emitting the same skeleton with a tweaked constant
(`ts_mean(x, 20)` → `ts_mean(x, 21)` → `ts_mean(x, 22)`).
This is FORBIDDEN. Window jitter is not a hypothesis; it is noise sampling.
If your only change from the previous iteration is a numeric constant, your
expression is invalid — regenerate it.

Every expression you emit must answer: **"What economic hypothesis am I testing
that no previous iteration has tested?"** If you cannot state it in one sentence,
you are on a rut path.

### Mutation ladder — pick the RIGHT magnitude for the situation

Order operators by how much structure they destroy. Match the rung to the signal:

| Rung | Mutation type | Example | Use when |
|---|---|---|---|
| 1 | **Parameter drift** | window 220 → 180 | ONLY as a final polish on an alpha already ≥ median Fitness. Never as your main move. |
| 2 | **Operator swap (same family)** | `ts_mean` → `ts_decay_linear` | Metrics near-median, one specific check failing (e.g. turnover). |
| 3 | **Family jump** | add a `Group` layer to a pure Time-Series expr | Metrics plateaued for 2+ iterations. |
| 4 | **Datafield substitution** | swap one field for an unexplored one | Same field appeared in 3+ of your last 4 expressions. |
| 5 | **Skeleton rebuild** | new topology, new hypothesis | You were PRUNED, or Sharpe < 0.5 × median. |

**Rule: your rung must be ≥ 2 unless you are polishing a proven winner.**
**Rule: when PRUNED, jump straight to rung 5. Do not creep.** A pruned path has
near-zero pheromone; reinforcing it wastes the colony's budget.

### Exploration vs exploitation schedule

Treat the iteration budget as a temperature schedule:

- **Early (iterations 1–5) — EXPLORE.**
  Maximise coverage of the (family × datafield) grid. Deliberately try families
  no agent has touched. A low-Sharpe result that maps unexplored territory is
  *more valuable* than a mediocre copy of a peer's alpha. Do not converge yet.

- **Middle (iterations 6–14) — EXPLOIT WITH DIVERSITY.**
  Recombine: take the *structural idea* from the best path so far and cross it
  with a component from a different family or datafield. This is crossover, not
  copying. Copying a peer's expression with one constant changed is the worst
  possible move — it burns an evaluation and adds zero information.

- **Late (iterations 15+) — INTENSIFY.**
  Only now is rung-1 parameter drift permitted, and only on the incumbent best.

### Pheromone rules — how to read the history

Your compressed history and peers' results ARE the pheromone trail. Read them as
evidence, not as instructions.

- **Deposit (reinforce):** a *component* (operator, field, or pairing) that appears
  in results above the running median → its pheromone is high. Reuse the
  **component**, but place it in a **new structure**. Reinforce ideas, not strings.
- **Evaporate (decay):** if a component appears in 3+ consecutive iterations across
  the colony *without* Fitness improving, its pheromone has evaporated regardless of
  how good it once looked. Abandon it, even if it is in the "effective combinations"
  list below. Stale success is a local optimum.
- **Negative trail:** a PRUNED or FAILED path marks its region as poisoned. Do not
  enter the neighbourhood of a pruned expression — that means no same-skeleton,
  no same-field-pair, for at least 3 iterations.
- **Never deposit on unverified paths.** Do not assume an untried combination is
  good because it sounds plausible. Try it, then let the metric decide.

### Anti-convergence guards (hard checks before you output)

Reject your own draft if ANY of these is true:

1. Its operator set overlaps > 60% with your own previous iteration.
2. Its operator set overlaps > 60% with any peer's current iteration.
3. It uses the same datafield pair as the incumbent best AND the same top-level
   operator.
4. The only delta from any prior expression is a numeric constant.
5. It uses zero operators from your assigned diversity-directive family.
6. You have used the same top-level wrapper (e.g. `winsorize(...)`) for 3
   iterations straight.

A distinct-but-mediocre alpha beats a duplicate-but-decent one. The colony's value
is in the *spread* of paths it explores; duplicates collapse the population to a
single point and the search dies.

### Structural diversity targets

Across your own trajectory, aim to cover:
- ≥ 4 distinct operator families in any 5-iteration span
- ≥ 3 distinct datafields in any 5-iteration span
- ≥ 2 distinct expression topologies (e.g. correlation-based vs. conditional-filter
  based vs. cross-sectional-rank based)

Topology archetypes to rotate through — do not stay in one:
- **Co-movement:** `ts_corr` / `ts_covariance` / `ts_regression` between two fields
- **Conditional gating:** `trade_when(condition, signal, -1)`
- **Cross-sectional relative:** `group_rank` / `group_zscore` / `group_neutralize`
- **Event/timing:** `days_from_last_change`, `ts_arg_max`, `hump`, `ts_step`
- **Non-linear reshaping:** `signed_power`, `bucket`, `winsorize`
- **Dispersion:** `ts_std_dev`, `quantile`, `vec_*` on vector fields

If your last 3 expressions were all the same archetype, you are in a rut. Switch.

---

## PART 1 — EMPIRICAL PRIORS (weak evidence — treat as hints, not rules)

Sample size is tiny. These are starting hypotheses, NOT settled facts. Do not let
them narrow the search — they exist to seed exploration, not to end it.

### LOW CONFIDENCE (limited data)

- **[SIGN FLIP]** (n=1, success_rate=100%, Sharpe Δ ≈ 0.000, Turnover Δ +0.000, Fitness Δ +0.000)
  A sign error was corrected, re-orienting the signal and lifting Sharpe, Fitness
  and Drawdown together.
  *Search implication:* sign correction is a **free diagnostic, not a strategy**.
  If |Sharpe| ≥ 1.25 and negative, flip once — then move on to a real structural
  hypothesis. Never count a flip as your iteration's contribution.

- **[COMPOSITE]** (n=2, success_rate=100%, Sharpe Δ ≈ +0.025, std 0.007, Turnover Δ −0.001, Fitness Δ +0.080)
  A volume-based trading condition was layered on to filter trades toward liquid
  periods; modest Sharpe gain, larger Fitness gain.
  *Search implication:* conditional gating is a **cheap, general-purpose wrapper**
  that composes with almost any core signal. Because it is cheap, it is also the
  most likely thing for the whole colony to converge on. If two peers already gate
  on volume this iteration, **do something else** — gating is not your edge.

### UNRELIABLE PATTERNS (high variance)
- (not enough data yet — this is expected early; keep exploring rather than
  over-fitting to n=1 results)

---

## PART 2 — DATAFIELD × OPERATOR PAIRS

**Read this section as a pheromone map with an evaporation clock, not a menu.**
Every entry below has been reinforced at most twice. Any entry reused without
Fitness improvement should be treated as evaporated.

### Reinforced combinations (moderate pheromone — recombine, don't repeat)

- **`rp_ess_ptg` + `days_from_last_change`**
  *Why:* captures time elapsed since the last change in `rp_ess_ptg` — a proxy for
  mean-reversion or momentum driven by the field's change frequency / stability.
  Post-sign-flip it carried real predictive information.
  *When:* works when `rp_ess_ptg` has predictable change-frequency patterns;
  sensitive to the field's implicit lookback.
  *Recombine, don't repeat:* the transferable idea is **"stability-as-signal"** —
  try `days_from_last_change` on a *different* field, or apply a different
  event-timing operator (`ts_arg_max`, `ts_step`, `hump`) to `rp_ess_ptg`.
  Re-emitting this exact pair is a rut path.

- **`rp_ess_ptg` + `signed_power`**
  *Why:* exponent ~1.5 non-linearly rescales the signal, reshaping its distribution
  against future returns.
  *When:* effective under non-linear signal→return relationships; risky with
  extreme outliers or large exponents.
  *Recombine, don't repeat:* the transferable idea is **"non-linear reshaping"**.
  Alternatives that test the same hypothesis differently: `bucket`, `quantile`,
  `winsorize` + `rank`. If someone already used `signed_power` this iteration,
  reach for one of these instead.
  *Caution:* `signed_power` amplifies tails → watch weight-concentration checks.
  Pair it with a normalisation layer rather than tuning the exponent.

- **`volume` + `trade_when`** and **`adv20` + `trade_when`**
  *Why:* gates execution to liquid regimes (`volume` vs. `adv20` benchmark),
  cutting slippage and improving realised performance.
  *When:* strongest where liquidity varies materially; near-useless in uniformly
  liquid/illiquid names.
  *Recombine, don't repeat:* these two are **the same idea twice** — liquidity
  gating. Counting them as two discoveries overstates the evidence. Untested
  gating conditions worth exploring instead: volatility regime (`ts_std_dev`),
  dispersion, sentiment state, or a *non*-liquidity condition entirely.
  *Colony rule:* at most ONE agent per iteration may use liquidity gating.
  If a peer has it, you don't.

### Explicitly unexplored (high value — go here first)

The map is mostly empty. Fields and archetypes with **no** recorded evidence are
where the information is. Prefer an unexplored path over a reinforced one whenever
the reinforced path has already been sampled this iteration.

Known-unexplored territory as of this generation:
- Group-family interaction with `rp_ess_ptg` (no `group_*` evidence at all)
- Co-movement archetype (`ts_corr` / `ts_covariance` / `ts_regression`) — untested
- Dispersion / vector operators — untested
- Any datafield outside `rp_ess_ptg`, `volume`, `adv20`

---

## PART 3 — SELF-CHECK BEFORE EMITTING

Answer these in your Analysis / Refinement Strategy. If any answer is weak,
rebuild the expression.

1. What is my one-sentence economic hypothesis? Has any prior iteration tested it?
2. Which mutation rung am I on, and does it match my situation? (Pruned → rung 5.)
3. Which of my operators is *new* relative to my last iteration and to my peers?
4. Which diversity-directive family am I satisfying, and with which operator?
5. Am I reinforcing a *component* in a new structure, or copying a *string*?
6. Do I pass all six anti-convergence guards?
7. Is my change larger than a numeric constant? (If no → invalid.)

**Remember:** the objective is not to find a good alpha this iteration. It is to
give the colony maximum information per evaluation. Fitness comes from the
population's coverage over time — a well-placed failure is a contribution; a
duplicated success is not.
