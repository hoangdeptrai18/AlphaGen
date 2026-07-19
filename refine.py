import argparse
import json
import os
import re
import statistics
import time as _time
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter, sleep

from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console

from ace_extensions import (
    get_alpha_recordset,
    get_datafield,
    get_stored_session,
    simulate_single_alpha,
)
from ace_lib import get_simulation_result_json
from alpha_utils import (
    copy,
    extract_datafields,
    fix_fastexpr,
    generate_pnl_chart,
    get_insample_context,
    strict_submissibility,
)
from pnl_features import build_pnl_features

# ── Constants ─────────────────────────────────────────────────────────────────

NUM_AGENTS   = 3
WINDOW_SIZE  = 4    # Keep last N iterations verbatim per agent; older → compressed summary

# ── Baseline / forced-rebuild policy ──────────────────────────────────────────
STAGNATION_LIMIT = 4      # Consecutive iterations without beating incumbent → force rebuild
IMPROVEMENT_EPS  = 0.02   # Fitness must exceed incumbent by this margin to count as progress

OPERATOR_FAMILIES: dict[str, set] = {
    "Time-Series": {
        "ts_mean", "ts_sum", "ts_std_dev", "ts_rank", "ts_zscore", "ts_delta",
        "ts_delay", "ts_corr", "ts_covariance", "ts_regression", "ts_product",
        "ts_quantile", "ts_scale", "ts_decay_linear", "ts_backfill", "ts_av_diff",
        "ts_count_nans", "ts_arg_max", "ts_arg_min", "ts_step",
        "days_from_last_change", "hump", "kth_element", "last_diff_value",
    },
    "Group": {
        "group_mean", "group_neutralize", "group_rank", "group_scale",
        "group_zscore", "group_backfill",
    },
    "Statistical": {
        "rank", "zscore", "scale", "normalize", "quantile", "winsorize", "vector_neut",
    },
    "Arithmetic": {
        "abs", "add", "subtract", "multiply", "divide", "log", "sqrt", "power",
        "sign", "signed_power", "inverse", "reverse", "max", "min", "densify",
    },
    "Transformational": {"bucket", "trade_when"},
    "Vector": {"vec_avg", "vec_sum"},
}

FOCUS_ROTATION = ["Time-Series", "Group", "Statistical", "Arithmetic", "Transformational"]

# Modification strategies — ALL 3 agents do DATAFIELD SWAP but from DIFFERENT categories.
# Categories rotate each iteration so agents never repeat the same category twice in a row.
# Format: list of 3 (strategy_name, instructions) tuples, one per agent slot.
#
# Category rotation across iterations:
#   iter 0: Agent1=PRICE, Agent2=FUNDAMENTAL, Agent3=SENTIMENT/ALTERNATIVE
#   iter 1: Agent1=FUNDAMENTAL, Agent2=SENTIMENT/ALTERNATIVE, Agent3=PRICE
#   iter 2: Agent1=SENTIMENT/ALTERNATIVE, Agent2=PRICE, Agent3=FUNDAMENTAL
#   ... cycles

# 9 data categories from WorldQuant BRAIN, split into 3 groups of 3.
# Each agent gets one group per iteration; groups rotate each iteration.
#
# Rotation:
#   iter 0: Agent1=Group A, Agent2=Group B, Agent3=Group C
#   iter 1: Agent1=Group B, Agent2=Group C, Agent3=Group A
#   iter 2: Agent1=Group C, Agent2=Group A, Agent3=Group B
#   ...
#
# Group A — Quantitative / Price-based:  Price Volume · Fundamental · Model
# Group B — Analyst / Derivatives:       Analyst · Earnings · Option
# Group C — Alternative / Sentiment:     News · Sentiment · Social Media

_DATAFIELD_CATEGORIES = [
    (
        "DATAFIELD SWAP — Group A: Price Volume / Fundamental / Model",
        "PRIMARY TASK: Replace or add ONE datafield from ONE of these 3 categories: "
        "Price Volume (close, open, high, low, volume, vwap, returns, adv20, adv60, "
        "market_cap, turnover_ratio, amihud_illiquidity, realized_volatility), "
        "Fundamental (eps, sales, revenue, book_value, total_assets, total_equity, "
        "net_income, cash_flow, free_cash_flow, roe, roa, gross_margin, "
        "debt_to_equity, pe_ratio, pb_ratio, ps_ratio, ev_ebitda, dividend_yield), "
        "or Model (model-based factor fields, composite rankings, risk model outputs, "
        "alpha factors from published quant models). "
        "Do NOT use Analyst, Earnings, Option, News, Sentiment, or Social Media fields. "
        "Do NOT reuse a field already in the seed. "
        "SECONDARY (only if your analysis justifies it): You MAY also adjust operators or "
        "window sizes IF you have a specific reason from analyzing the seed's weaknesses "
        "(e.g. if turnover is high, shorten/smooth; if signal is noisy, add rank(); "
        "if fundamental field needs backfill, add ts_backfill). "
        "State the reason clearly in your Analysis before making operator/window changes. "
        "Do NOT change operators or windows without justification."
    ),
    (
        "DATAFIELD SWAP — Group B: Analyst / Earnings / Option",
        "PRIMARY TASK: Replace or add ONE datafield from ONE of these 3 categories: "
        "Analyst (analyst_rating, price_target, recommendation, consensus_estimate, "
        "target_price_revision, analyst_dispersion, coverage_count), "
        "Earnings (eps, eps_estimate, eps_surprise, eps_revision, earnings_growth, "
        "revenue_surprise, guidance_revision, earnings_quality), "
        "or Option (implied_volatility, put_call_ratio, option_volume, option_open_interest, "
        "iv_skew, iv_term_structure, realized_vs_implied_vol). "
        "Do NOT use Price Volume, Fundamental, Model, News, Sentiment, or Social Media fields. "
        "Do NOT reuse a field already in the seed. "
        "SECONDARY (only if your analysis justifies it): You MAY also adjust operators or "
        "window sizes IF you have a specific reason from analyzing the seed's weaknesses "
        "(e.g. if turnover is high, shorten/smooth; if signal is noisy, add rank(); "
        "if fundamental field needs backfill, add ts_backfill). "
        "State the reason clearly in your Analysis before making operator/window changes. "
        "Do NOT change operators or windows without justification."
    ),
    (
        "DATAFIELD SWAP — Group C: News / Sentiment / Social Media",
        "PRIMARY TASK: Replace or add ONE datafield from ONE of these 3 categories: "
        "News (news_sentiment, news_volume, news_buzz, event_count, "
        "earnings_news_proximity, media_coverage_score), "
        "Sentiment (sentiment_score, bull_bear_ratio, investor_sentiment, "
        "fear_greed_index, short_interest, days_to_cover, institutional_ownership), "
        "or Social Media (social_buzz, twitter_mention_count, reddit_activity, "
        "social_sentiment_score, viral_score, trending_score). "
        "Do NOT use Price Volume, Fundamental, Model, Analyst, Earnings, or Option fields. "
        "Do NOT reuse a field already in the seed. "
        "SECONDARY (only if your analysis justifies it): You MAY also adjust operators or "
        "window sizes IF you have a specific reason from analyzing the seed's weaknesses "
        "(e.g. if turnover is high, shorten/smooth; if signal is noisy, add rank(); "
        "if fundamental field needs backfill, add ts_backfill). "
        "State the reason clearly in your Analysis before making operator/window changes. "
        "Do NOT change operators or windows without justification."
    ),
]


def get_mod_strategies_for_iteration(iteration: int) -> list[tuple[str, str]]:
    """Return 3 (name, desc) tuples, one per agent, rotating category assignment each iter."""
    n = len(_DATAFIELD_CATEGORIES)
    return [_DATAFIELD_CATEGORIES[(i + iteration) % n] for i in range(NUM_AGENTS)]


# Keep for backward compat — replaced by get_mod_strategies_for_iteration
MOD_STRATEGIES = _DATAFIELD_CATEGORIES

# ── Argument parsing ──────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(
    description="Multi-agent parallel Alpha refinement pipeline for WorldQuant Brain."
)
parser.add_argument("--alpha_id", "-id", type=str, help="Alpha ID")
args   = parser.parse_args()
alpha_id = args.alpha_id

if not alpha_id:
    parser.error("Please input an Alpha ID.")

console = Console()
load_dotenv()

openrouter_api_key = os.getenv("OPENROUTER_API_KEYS").split(",")[0].strip()
or_client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_api_key)

# ── Session & files ───────────────────────────────────────────────────────────

brain_session = get_stored_session(duration=10800)

with open("model.json", "r", encoding="utf-8") as f:
    model = json.load(f)

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

simulated_alpha = get_simulation_result_json(brain_session, alpha_id)
pnl = get_alpha_recordset(brain_session, alpha_id, "pnl")
generate_pnl_chart(config["pnl_chart"], pnl)

# Same PnL data the chart is drawn from, converted to text the LLM can read.
baseline_pnl_text = build_pnl_features(pnl, config["pnl_chart"]["test"])

datafields = extract_datafields(simulated_alpha["regular"]["code"])

# ── System instructions ───────────────────────────────────────────────────────

print()
system_instruction_datafield = "Data Field Context:"
for datafield in datafields:
    df_info    = get_datafield(brain_session, datafield)
    df_id      = df_info.get("id") or df_info.get("dataFieldId") or df_info.get("fieldId") or datafield
    df_type    = df_info.get("type") or df_info.get("dataType") or "MATRIX"
    description = df_info.get("description") or df_info.get("desc") or ""
    coverage   = df_info.get("coverage", None)
    if df_type == "VECTOR" and "VECTOR" not in config["operators"]:
        config["operators"].append("VECTOR")
    coverage_str = ""
    if coverage is not None:
        coverage_pct = round(float(coverage) * 100, 1) if float(coverage) <= 1 else round(float(coverage), 1)
        coverage_str = f", coverage={coverage_pct}%"
        if coverage_pct < 50:
            coverage_str += " [LOW - use ts_backfill(x, 10)]"
    system_instruction_datafield += f"\n{df_id} ({df_type}{coverage_str}): {description}"

if "Group" in config["operators"]:
    system_instruction_datafield += "\nGrouping Fields:\n"
    for group in config["groups"]:
        if group == "currency" and simulated_alpha["settings"]["delay"] != 1:
            continue
        if group[0] == "!":
            continue
        system_instruction_datafield += group + ", "

console.print("Operator Categories:", style="blue")
system_instruction_operators = "Operators Context:"
for operator_category in config["operators"]:
    if operator_category[0] == "!":
        continue
    system_instruction_operators += f"\n\n{operator_category} Operators:\n"
    with open(f"operators/{operator_category}.txt", "r", encoding="utf-8") as f:
        system_instruction_operators += f.read()
    console.print(operator_category, end=", ", style="blue")
print()

system_instruction_warning = "System Warnings:\n"
with open("system_instructions/warnings.txt", encoding="utf-8") as f:
    system_instruction_warning += f.read()

system_instruction_signals = ""
signals_path = "system_instructions/signal_combinations.md"
if os.path.exists(signals_path):
    with open(signals_path, encoding="utf-8") as f:
        system_instruction_signals = "Signal Combination Patterns:\n" + f.read()

system_instruction_weight = ""
weight_path = "system_instructions/weight_control.md"
if os.path.exists(weight_path):
    with open(weight_path, encoding="utf-8") as f:
        system_instruction_weight = "Weight Control Guidelines:\n" + f.read()

system_instruction_errors = ""
error_messages_path = "system_instructions/error_messages.md"
if os.path.exists(error_messages_path):
    with open(error_messages_path, encoding="utf-8") as f:
        system_instruction_errors = "WorldQuant Brain Error Reference:\n" + f.read()

system_instruction_knowledge = ""
knowledge_base_path = "system_instructions/knowledge_base.md"
if os.path.exists(knowledge_base_path):
    with open(knowledge_base_path, encoding="utf-8") as f:
        system_instruction_knowledge = "Prior Knowledge from Past Alpha Optimizations:\n" + f.read()

schema_keys   = list(model["structured_output"]["schema"].keys())
schema_desc   = model["structured_output"]["schema_description"]
schema_fields = "\n".join(
    f'  "{k}": "{v}"' for k, v in model["structured_output"]["schema"].items()
)
json_format_instruction = (
    "\n\nOUTPUT FORMAT: You must respond with a valid JSON object only. "
    "No markdown, no code blocks, no extra text — just raw JSON.\n"
    f"Schema: {schema_desc}\n"
    f"Required fields:\n{{\n{schema_fields}\n}}"
)

system_instructions = (
    "\n\n".join(filter(None, [
        system_instruction_operators,
        system_instruction_datafield,
        system_instruction_warning,
        system_instruction_signals,
        system_instruction_weight,
        system_instruction_errors,
        system_instruction_knowledge,
    ]))
    + json_format_instruction
)
system_message = {"role": "system", "content": system_instructions}

# ── Initial state ─────────────────────────────────────────────────────────────

iteration_0 = "\n".join([
    "Iteration #0 — BASELINE ALPHA",
    "",
    "This is the STARTING POINT, not a template. Your job is to find a BETTER",
    "alpha, which may share nothing with this one except the objective.",
    "",
    "Alpha Expression:",
    simulated_alpha["regular"]["code"],
    "",
    get_insample_context(simulated_alpha["is"]),
    "",
    baseline_pnl_text,
    "",
    "[HOW TO USE THIS BASELINE]",
    "Read the PnL Curve Analysis above BEFORE the summary stats. The equity curve",
    "tells you WHY this alpha performs as it does; the summary Sharpe only tells",
    "you THAT it does.",
    "",
    "  • If the curve shows decay or breakdown → the hypothesis is the problem.",
    "    Adding operators to a broken hypothesis produces a more complex broken",
    "    alpha. Rebuild from a different economic idea.",
    "  • If the curve is stable → the structure has merit. Recombine its",
    "    components into new structures; do not merely tune its constants.",
    "",
    "You are NOT required to keep this expression's skeleton, its operators, or",
    "even its datafields. You are only required to beat its Fitness.",
])

# Per-agent: verbatim recent messages (sliding window)
agents_recent_msgs: list[list[dict]] = [
    [{"role": "user", "content": iteration_0}]
    for _ in range(NUM_AGENTS)
]

# Per-agent: full iteration records for deterministic compression
agents_iteration_records: list[list[dict]] = [[] for _ in range(NUM_AGENTS)]

print()
for i, m in enumerate(model["models"]):
    console.print(f"Agent {i + 1}: {m}", style="purple")
console.print(f"Temperature: {model['temperature']}", style="purple")
console.print(
    f"Agents: {NUM_AGENTS} | Iterations: {config['iterations']} | "
    f"Context window: {WINDOW_SIZE} recent + compressed summary",
    style="purple",
)
print()
console.print(system_instruction_datafield, style="blue")
print()
console.print(iteration_0, style="green")
print()

# ── Deterministic helpers ─────────────────────────────────────────────────────

def extract_operators(expr: str) -> set:
    return set(re.findall(r'\b([a-z][a-z0-9_]*)\s*\(', expr))


def get_used_families(expr: str) -> set:
    ops = extract_operators(expr)
    families = set()
    for op in ops:
        for family, family_ops in OPERATOR_FAMILIES.items():
            if op in family_ops:
                families.add(family)
    return families


def jaccard_similarity(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def parse_insample_stats(insample: dict) -> dict:
    stats: dict = {}
    for key in ["sharpe", "fitness", "turnover", "returns", "drawdown", "margin",
                "longCount", "shortCount"]:
        if key in insample:
            try:
                stats[key] = round(float(insample[key]), 4)
            except (TypeError, ValueError):
                stats[key] = insample[key]
    checks = insample.get("checks", [])
    stats["failing"] = [c["name"] for c in checks if c.get("result") == "FAIL"]
    stats["passing"] = [c["name"] for c in checks if c.get("result") == "PASS"]
    return stats


def build_stats_block(stats: dict, expression: str) -> str:
    lines = []
    for key in ["sharpe", "fitness", "turnover", "returns", "drawdown",
                "margin", "longCount", "shortCount"]:
        if key in stats:
            lines.append(f"{key}: {stats[key]}")
    if stats.get("failing"):
        lines.append(f"Failing checks: {', '.join(stats['failing'])}")
    if stats.get("passing"):
        lines.append(f"Passing checks: {', '.join(stats['passing'])}")

    sharpe   = float(stats.get("sharpe",   0) or 0)
    returns  = float(stats.get("returns",  0) or 0)
    turnover = float(stats.get("turnover", 0) or 0)

    # Weight check
    weight = None
    for c in stats.get("passing", []) + stats.get("failing", []):
        pass  # weight extracted separately below via checks list
    # Re-extract weight from raw insample if available via stats
    # (weight hint built into feedback below)

    # Sharpe absolute-value hint
    abs_sharpe = abs(sharpe)
    has_minus  = expression.strip().startswith("-")
    if sharpe < 0 and abs_sharpe >= 1.25 and has_minus:
        sharpe_hint = "[STRONG but INVERTED & has '-' — REMOVE the '-' prefix to flip signal back]"
    elif sharpe < 0 and abs_sharpe >= 1.25 and not has_minus:
        sharpe_hint = "[STRONG but INVERTED — ADD '-' prefix before expression to flip signal]"
    elif sharpe < 0 and abs_sharpe < 1.25:
        sharpe_hint = "[WEAK & INVERTED — do NOT just add '-'; improve signal quality first]"
    elif sharpe < 1.25:
        sharpe_hint = "[CRITICAL — improve first, linear effect on Fitness]"
    else:
        sharpe_hint = "[OK]"

    lines += [
        "",
        "Fitness formula: Fitness ∝ Sharpe × √Returns × 1/√max(Turnover, 0.125)",
        "Priority actions:",
    ]
    lines.append(f"  • Sharpe={sharpe} {sharpe_hint}")
    lines.append(
        f"  • Returns={returns} {'[low — increasing helps via √Returns]' if returns < 0.02 else '[OK]'}"
    )
    if turnover > 0.125:
        lines.append(f"  • Turnover={turnover} [>12.5% — apply ts_decay_linear or ts_mean to smooth]")
    else:
        lines.append(f"  • Turnover={turnover} [≤12.5% — reducing further has ZERO effect on fitness]")

    ops_used      = extract_operators(expression)
    families_used = get_used_families(expression)
    lines += [
        "",
        f"Operators used (auto-parsed): {', '.join(sorted(ops_used))}",
        f"Operator families: {', '.join(sorted(families_used))}",
    ]
    return "\n".join(lines)


# ── Context compression ───────────────────────────────────────────────────────

def build_history_summary(records: list[dict]) -> str:
    """
    Deterministically compress old iteration records into a compact summary.
    Called when the sliding window pushes entries out of the verbatim window.
    No LLM call — pure Python.
    """
    if not records:
        return ""

    n         = len(records)
    success   = [r for r in records if r["status"] == "SUCCESS"]
    failed    = [r for r in records if r["status"] == "FAILED"]
    pruned    = [r for r in records if r["status"] == "PRUNED"]

    lines = [f"[COMPRESSED HISTORY — {n} past iterations]"]

    if success:
        best = max(success, key=lambda r: r.get("fitness") or 0)
        lines.append(
            f"Best result so far: Sharpe={best.get('sharpe')}, "
            f"Fitness={best.get('fitness')}, Turnover={best.get('turnover')}"
        )
        lines.append(f"  Expression: {best['expression']}")

        sharpe_vals  = [r.get("sharpe")   or 0 for r in success]
        fitness_vals = [r.get("fitness")  or 0 for r in success]
        turnover_vals = [r.get("turnover") or 0 for r in success]
        lines.append(
            f"Averages over {len(success)} successful sims: "
            f"Sharpe={round(statistics.mean(sharpe_vals), 3)}, "
            f"Fitness={round(statistics.mean(fitness_vals), 3)}, "
            f"Turnover={round(statistics.mean(turnover_vals), 3)}"
        )

        # Bottleneck pattern
        fail_counts: dict[str, int] = {}
        for r in success:
            for c in (r.get("failing_checks") or []):
                fail_counts[c] = fail_counts.get(c, 0) + 1
        if fail_counts:
            dominant = max(fail_counts, key=fail_counts.get)
            lines.append(
                f"Recurring bottleneck: {dominant} fails in "
                f"{fail_counts[dominant]}/{len(success)} iterations"
            )

        high_to = [r for r in success if (r.get("turnover") or 0) > 0.125]
        if len(high_to) > len(success) * 0.5:
            lines.append(f"Turnover > 12.5% in {len(high_to)}/{len(success)} iters — smoothing is a persistent issue")

    # Families explored
    all_families: set[str] = set()
    for r in records:
        all_families.update(r.get("families") or set())
    unexplored = set(FOCUS_ROTATION) - all_families
    lines.append(f"Families explored: {', '.join(sorted(all_families))}")
    if unexplored:
        lines.append(f"Unexplored families: {', '.join(sorted(unexplored))} — consider trying these")

    if failed:
        lines.append(f"Syntax failures: {len(failed)} expressions rejected by platform")
    if pruned:
        lines.append(
            f"Pruned (far below median): {len(pruned)} expressions — "
            f"those approaches are clearly not working, avoid similar logic"
        )

    return "\n".join(lines)


def get_agent_messages(agent_idx: int) -> list[dict]:
    """
    Build the full message list for one agent:
      [initial_msg, <summary of old history if any>, ...recent WINDOW_SIZE iters verbatim]
    Context size stays roughly constant regardless of total iterations.
    """
    recent  = agents_recent_msgs[agent_idx]
    records = agents_iteration_records[agent_idx]

    # Count how many iterations are covered by recent verbatim messages
    # recent = [initial_msg] + pairs of (assistant, user) per recent iter
    n_recent_iters = (len(recent) - 1) // 2
    n_old_records  = max(0, len(records) - n_recent_iters)
    old_records    = records[:n_old_records]

    messages = [recent[0]]  # Initial message always first

    if old_records:
        summary = build_history_summary(old_records)
        messages.append({"role": "user", "content": summary})

    messages.extend(recent[1:])
    return messages


def add_to_agent_context(agent_idx: int, role: str, content: str):
    """
    Add a message to the agent's sliding window.
    When window exceeds WINDOW_SIZE iterations, oldest pair is silently dropped
    (its data is already captured in agents_iteration_records for the summary).
    """
    agents_recent_msgs[agent_idx].append({"role": role, "content": content})

    # max messages = initial + WINDOW_SIZE iterations × 2 messages each
    max_msgs = 1 + WINDOW_SIZE * 2
    if len(agents_recent_msgs[agent_idx]) > max_msgs:
        # Drop oldest iteration pair (index 1 and 2, right after initial msg)
        rm = agents_recent_msgs[agent_idx]
        agents_recent_msgs[agent_idx] = [rm[0]] + rm[3:]


def record_iteration(agent_idx: int, record: dict):
    agents_iteration_records[agent_idx].append(record)


# ── Post-hoc MedianPruner ─────────────────────────────────────────────────────

class MedianPruner:
    """
    Flags results significantly below the running global median.
    WQ Brain does not support mid-simulation cancellation, so pruning is
    post-hoc: the simulation completes normally, but the result is discarded
    and the agent receives strong 'change direction' feedback.
    Mirrors Optuna's MedianPruner / SuccessiveHalving concept.
    """
    def __init__(self, min_trials: int = 4, threshold: float = 0.4):
        self._history: list[tuple[float, float]] = []  # (sharpe, fitness)
        self.min_trials = min_trials
        self.threshold  = threshold   # Prune if value < threshold × median

    def record(self, sharpe: float, fitness: float):
        if sharpe is not None and fitness is not None:
            self._history.append((float(sharpe or 0), float(fitness or 0)))

    def should_prune(self, sharpe: float, fitness: float) -> bool:
        if len(self._history) < self.min_trials:
            return False
        med_sharpe  = statistics.median(h[0] for h in self._history)
        med_fitness = statistics.median(h[1] for h in self._history)
        if med_sharpe == 0 or med_fitness == 0:
            return False
        return (
            float(sharpe or 0) < med_sharpe  * self.threshold and
            float(fitness or 0) < med_fitness * self.threshold
        )

    @property
    def median_sharpe(self) -> float:
        return statistics.median((h[0] for h in self._history), ) if self._history else 0.0

    @property
    def median_fitness(self) -> float:
        return statistics.median((h[1] for h in self._history), ) if self._history else 0.0


pruner = MedianPruner(min_trials=4, threshold=0.4)

# ── Incumbent tracking / anti-template policy ─────────────────────────────────

def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


baseline_fitness = _safe_float(simulated_alpha["is"].get("fitness"))

incumbent = {
    "fitness":    baseline_fitness,
    "sharpe":     _safe_float(simulated_alpha["is"].get("sharpe")),
    "expression": simulated_alpha["regular"]["code"],
    "source":     "baseline",
}

# Consecutive iterations in which each agent failed to beat the incumbent
agent_stagnation = [0] * NUM_AGENTS

# Current seed: starts as the original alpha, updated each iteration to the best performer
current_seed = {
    "expression": simulated_alpha["regular"]["code"],
    "sharpe":     _safe_float(simulated_alpha["is"].get("sharpe")),
    "fitness":    _safe_float(simulated_alpha["is"].get("fitness")),
    "sim_result": simulated_alpha,
}


def update_incumbent(expr: str, sharpe, fitness) -> bool:
    """Return True if this result beats the incumbent by more than IMPROVEMENT_EPS."""
    global incumbent
    f = _safe_float(fitness)
    if f > incumbent["fitness"] + IMPROVEMENT_EPS:
        incumbent = {
            "fitness":    f,
            "sharpe":     _safe_float(sharpe),
            "expression": expr,
            "source":     "agent",
        }
        return True
    return False


def build_rebuild_directive() -> str:
    """Hard directive issued when an agent has stagnated for too long."""
    return (
        f"\n\n[FORCED REBUILD — {STAGNATION_LIMIT} iterations without beating the incumbent]\n"
        f"You have failed to beat Fitness={incumbent['fitness']:.3f} for "
        f"{STAGNATION_LIMIT} consecutive iterations. Incremental edits are exhausted.\n"
        "\n"
        "MANDATORY for your next expression:\n"
        "  1. State a DIFFERENT economic hypothesis than the one you have been testing.\n"
        "  2. Use a DIFFERENT combination mechanism (M1-M9). If you have been\n"
        "     multiplying ranks (M1), you may NOT use M1 again.\n"
        "  3. Drop at least ONE datafield you have used in every prior iteration.\n"
        "  4. Do NOT reuse the baseline's skeleton. Its curve already told you what\n"
        "     it can and cannot do.\n"
        "\n"
        "Optimising within a dead hypothesis cannot produce a live alpha. The colony "
        "needs a new region of the search space, not a better point in this one."
    )


# ── Diversity helpers ─────────────────────────────────────────────────────────

def get_focus_family(iteration: int, agent_idx: int) -> str:
    return FOCUS_ROTATION[(iteration * NUM_AGENTS + agent_idx) % len(FOCUS_ROTATION)]


def get_mod_strategy(agent_idx: int, iteration: int = 0) -> tuple[str, str]:
    """Return (strategy_name, strategy_instructions) for this agent and iteration."""
    return get_mod_strategies_for_iteration(iteration)[agent_idx % NUM_AGENTS]


def build_cross_learning_message(
    iteration_num: int,
    own_summary: dict,
    other_summaries: list,
    focus_family: str,
    similarity_warnings: list,
    is_pruned: bool,
    mod_strategy_name: str = "",
    mod_strategy_desc: str = "",
) -> str:
    if is_pruned:
        own_block = (
            f"YOUR RESULT WAS PRUNED — Sharpe={own_summary.get('sharpe')}, "
            f"Fitness={own_summary.get('fitness')}. "
            f"This is significantly below the median of all past results "
            f"(median Sharpe={pruner.median_sharpe:.3f}, median Fitness={pruner.median_fitness:.3f}). "
            f"This direction is clearly not working. You MUST try a completely different approach."
        )
    elif own_summary["status"] == "FAILED":
        own_block = "Your expression was rejected by the platform (syntax/input error). Fix it."
    else:
        own_block = own_summary["stats_block"]

        # Curve shape drives the next decision more than the summary Sharpe does.
        if own_summary.get("pnl_text"):
            own_block += "\n\n" + own_summary["pnl_text"]

        gap = incumbent["fitness"] - _safe_float(own_summary.get("fitness"))
        if gap > 0:
            own_block += (
                f"\n\n[INCUMBENT] Best Fitness so far = {incumbent['fitness']:.3f}. "
                f"You are {gap:.3f} behind. Beating it requires a different "
                f"structure, not a tuned one."
            )
        else:
            own_block += (
                f"\n\n[INCUMBENT] You ARE the incumbent (Fitness={incumbent['fitness']:.3f}). "
                f"Its curve shape above tells you what to preserve and what to fix."
            )

    peer_blocks = []
    for s in other_summaries:
        if s["status"] == "PRUNED":
            result = f"PRUNED (far below median) — Sharpe={s.get('sharpe')}, Fitness={s.get('fitness')}"
        elif s["status"] == "SUCCESS":
            result = s["stats_block"]
        else:
            result = "SIMULATION FAILED — expression rejected."
        peer_blocks.append(
            f"--- Agent {s['idx'] + 1} ---\n"
            f"Expression: {s['expression']}\n"
            f"Analysis: {s['analysis']}\n"
            f"Refinement Strategy: {s['strategy']}\n"
            f"Metrics & Operators:\n{result}"
        )

    diversity_lines = [
        "",
        "[DIVERSITY DIRECTIVE FOR NEXT ITERATION]",
        f"Your assigned operator focus: {focus_family}.",
        f"You MUST include at least one {focus_family} operator not used by other agents.",
    ]
    for other_idx, sim_score in similarity_warnings:
        diversity_lines.append(
            f"WARNING: Your operators overlap {sim_score:.0%} with Agent {other_idx + 1}. "
            f"Try a completely different family or datafield."
        )

    # Include seed and modification strategy
    seed_block = (
        f"\n[CURRENT SEED — all agents optimize FROM this expression]\n"
        f"Expression: {current_seed['expression']}\n"
        f"Seed Metrics: Sharpe={current_seed['sharpe']:.4f}, Fitness={current_seed['fitness']:.4f}\n"
        f"\n[YOUR ASSIGNED MODIFICATION STRATEGY]\n"
        f"Strategy: {mod_strategy_name}\n"
        f"{mod_strategy_desc}\n"
        f"All 3 agents start from the SAME seed but use DIFFERENT modification strategies. "
        f"Do NOT copy another agent's approach. Do NOT change a different part than your strategy says."
    )

    return (
        f"Iteration #{iteration_num} completed.\n\n"
        "[YOUR RESULT]\n" + own_block + "\n\n"
        "[OTHER AGENTS' RESULTS — Learn from their reasoning; do NOT duplicate]\n"
        + "\n\n".join(peer_blocks)
        + "\n"
        + "\n".join(diversity_lines)
        + seed_block
        + "\n\nNow produce your next alpha expression."
    )


# ── LLM call ──────────────────────────────────────────────────────────────────

def call_llm(agent_idx: int, iteration_num: int):
    agent_model = model["models"][agent_idx % len(model["models"])]
    messages    = [system_message] + get_agent_messages(agent_idx)   # compressed context

    for attempt in range(1, 6):
        try:
            t = perf_counter()
            response = or_client.chat.completions.create(
                model=agent_model,
                messages=messages,
                temperature=model["temperature"],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "alpha_refinement",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {k: {"type": "string"} for k in schema_keys},
                            "required": schema_keys,
                            "additionalProperties": False,
                        },
                    },
                },
            )
            raw    = response.choices[0].message.content.strip()
            parsed = json.loads(raw)
            if all(k in parsed for k in schema_keys):
                ctx_size = sum(len(m["content"]) for m in messages)
                console.log(
                    f"[yellow]Agent {agent_idx + 1} ({agent_model}) | "
                    f"{perf_counter()-t:.1f}s | ctx ~{ctx_size//1000}k chars[/]"
                )
                return parsed
        except Exception as e:
            console.print(f"[red]Agent {agent_idx + 1} attempt {attempt}/5: {e}[/]")
            sleep(3 * attempt)

    console.print(f"[red]Agent {agent_idx + 1} | All retries exhausted.[/]")
    return None


def simulate_alpha(alpha):
    if alpha is None:
        return None
    return simulate_single_alpha(brain_session, alpha)


# ── Main parallel loop ────────────────────────────────────────────────────────

total_iterations = config["iterations"]
successful_iterations = 0
attempt_num = 0

while successful_iterations < total_iterations:
    attempt_num += 1
    console.rule(
        f"[bold cyan]Iteration {successful_iterations + 1}/{total_iterations}  |  "
        f"Attempt #{attempt_num}[/]"
    )

    # ── Step 1: Parallel LLM calls ─────────────────────────────────────────
    console.print(f"[yellow]► {NUM_AGENTS} LLMs generating in parallel...[/]")
    t0 = perf_counter()
    with ThreadPoolExecutor(max_workers=NUM_AGENTS) as ex:
        agent_outputs = list(
            ex.map(call_llm, range(NUM_AGENTS), [successful_iterations] * NUM_AGENTS)
        )
    console.log(f"[yellow]All LLMs done in {perf_counter() - t0:.1f}s[/]")

    MIN_DATAFIELDS = config.get("min_datafields", 2)
    MAX_WEIGHT     = 0.20

    # Fix expressions, validate, register assistant messages in sliding window
    trial_alphas = []
    for idx, output in enumerate(agent_outputs):
        if output is None:
            trial_alphas.append(None)
            continue
        output["Alpha Expression"] = fix_fastexpr(output["Alpha Expression"])
        expr = output["Alpha Expression"]

        # Pre-flight: min datafields check
        n_fields = len(extract_datafields(expr))
        if n_fields < MIN_DATAFIELDS:
            feedback = (
                f"Iteration #{successful_iterations + 1}\n"
                f"REJECTED: Your expression uses only {n_fields} datafield(s). "
                f"Minimum required: {MIN_DATAFIELDS}. Add more datafields to diversify the signal."
            )
            add_to_agent_context(idx, "assistant",
                f"Iteration #{successful_iterations + 1}\n" + "\n".join(f"{k}:\n{v}" for k, v in output.items()))
            add_to_agent_context(idx, "user", feedback)
            console.print(f"[red]Agent {idx + 1} | REJECTED: too few datafields ({n_fields} < {MIN_DATAFIELDS})[/]")
            trial_alphas.append(None)
            continue

        agent_ctx = (
            f"Iteration #{successful_iterations + 1}\n"
            + "\n".join(f"{k}:\n{v}" for k, v in output.items())
        )
        add_to_agent_context(idx, "assistant", agent_ctx)
        console.print(f"\n[cyan bold]Agent {idx + 1}:[/]")
        console.print(agent_ctx, style="cyan", markup=False)
        ta = copy(simulated_alpha)
        ta["regular"] = output["Alpha Expression"]
        # Note: simulation settings come from simulated_alpha; expression is from LLM output
        trial_alphas.append(ta)

    # ── Step 2: Parallel simulations (staggered to avoid 429 bursts) ──────
    SIM_STAGGER_SECS = 5

    def simulate_alpha_staggered(args):
        agent_idx, alpha = args
        if agent_idx > 0:
            _time.sleep(agent_idx * SIM_STAGGER_SECS)
        return simulate_alpha(alpha)

    console.print(f"\n[yellow]► Simulating {NUM_AGENTS} alphas (staggered {SIM_STAGGER_SECS}s apart)...[/]")
    t1 = perf_counter()
    with ThreadPoolExecutor(max_workers=NUM_AGENTS) as ex:
        sim_results = list(ex.map(simulate_alpha_staggered, enumerate(trial_alphas)))
    console.log(f"[yellow]All simulations done in {perf_counter() - t1:.1f}s[/]")

    # ── Step 3: Parse results + pruning decision ────────────────────────────
    agent_summaries  = []
    found_submittable = False
    any_real_success  = False   # True only when at least one non-pruned SUCCESS

    for idx, (output, sim_result) in enumerate(zip(agent_outputs, sim_results)):
        expr = output["Alpha Expression"] if output else "N/A"

        if output is None or not sim_result or not isinstance(sim_result, dict):
            agent_summaries.append({
                "idx": idx, "expression": expr, "status": "FAILED",
                "analysis": output.get("Analysis", "") if output else "",
                "strategy": output.get("Refinement Strategy", "") if output else "",
                "stats_block": "Simulation failed — expression rejected.",
                "pnl_text": "",
                "sharpe": None, "fitness": None, "ops": set(),
                "failing_checks": [],
            })
            agent_stagnation[idx] += 1
            record_iteration(idx, {
                "expression": expr, "status": "FAILED",
                "families": get_used_families(expr),
                "failing_checks": [],
            })
            console.print(f"[red]Agent {idx + 1} | FAILED[/]")
            continue

        insample = sim_result["is"]
        checks   = insample["checks"]
        stats    = parse_insample_stats(insample)
        sharpe   = stats.get("sharpe") or 0
        fitness  = stats.get("fitness") or 0
        ops_used = extract_operators(expr)

        # Weight hard-reject: if weight > 20%, skip this result
        weight = None
        for c in checks:
            cname = c.get("name", "").upper()
            if any(kw in cname for kw in ("WEIGHT", "MAX_WEIGHT", "CONCENTRATION")):
                try:
                    weight = float(c.get("value") or c.get("result_value") or 0)
                except (TypeError, ValueError):
                    pass
        if weight is not None and weight > MAX_WEIGHT:
            n_ops    = len(extract_operators(expr))
            n_fields = len(extract_datafields(expr))
            is_complex = n_ops > 4 or n_fields > 3
            if is_complex:
                hint = "SIMPLIFY FIRST: remove 1-2 operator layers or swap a datafield for a higher-coverage one. More operators often INCREASE weight."
            else:
                hint = "Apply rank() or zscore() at the outermost level to normalize weight distribution."
            weight_feedback = (
                f"HARD REJECT (weight={weight:.1%} > 20% limit). {hint} "
                f"Current expression: {expr}"
            )
            add_to_agent_context(idx, "user", weight_feedback)
            console.print(f"[red]Agent {idx + 1} | HARD REJECT weight={weight:.1%}[/]")
            record_iteration(idx, {
                "expression": expr, "status": "FAILED",
                "families": get_used_families(expr), "failing_checks": ["WEIGHT"],
            })
            agent_summaries.append({
                "idx": idx, "expression": expr, "status": "FAILED",
                "analysis": output.get("Analysis", ""),
                "strategy": output.get("Refinement Strategy", ""),
                "stats_block": f"HARD REJECT: weight={weight:.2f} > {MAX_WEIGHT:.0%}",
                "pnl_text": "",
                "sharpe": sharpe, "fitness": fitness, "ops": ops_used, "failing_checks": ["WEIGHT"],
            })
            agent_stagnation[idx] += 1
            continue

        # MedianPruner decision (before recording, so history doesn't include current)
        is_pruned = pruner.should_prune(sharpe, fitness)
        pruner.record(sharpe, fitness)    # record after decision

        status = "PRUNED" if is_pruned else "SUCCESS"
        stats_block = build_stats_block(stats, expr)
        agent_pnl_text = ""   # initialised before the branch: both paths read it below

        # Incumbent comparison — drives the forced-rebuild policy
        if not is_pruned and update_incumbent(expr, sharpe, fitness):
            agent_stagnation[idx] = 0
            console.print(
                f"[bold green]Agent {idx + 1} | NEW INCUMBENT Fitness={fitness:.3f} "
                f"(baseline was {baseline_fitness:.3f})[/]"
            )
        else:
            agent_stagnation[idx] += 1

        if is_pruned:
            console.print(
                f"[yellow]Agent {idx + 1} | PRUNED — "
                f"Sharpe={sharpe}, Fitness={fitness} "
                f"(median: {pruner.median_sharpe:.3f} / {pruner.median_fitness:.3f})[/]"
            )
        else:
            any_real_success = True
            console.print(f"\n[green bold]Agent {idx + 1} | Alpha {sim_result['id']}[/]")
            console.print(stats_block, style="green")
            pnl = get_alpha_recordset(brain_session, sim_result["id"], "pnl")
            generate_pnl_chart(config["pnl_chart"], pnl)
            agent_pnl_text = build_pnl_features(pnl, config["pnl_chart"]["test"])
            console.print(agent_pnl_text, style="green", markup=False)
            if strict_submissibility(checks):
                found_submittable = True
                console.print(f"[bold purple]Agent {idx + 1} -> SUBMITTABLE! {sim_result['id']}[/]")

        agent_summaries.append({
            "idx": idx, "expression": expr, "status": status,
            "analysis": output.get("Analysis", ""),
            "strategy": output.get("Refinement Strategy", ""),
            "stats_block": stats_block,
            "pnl_text": agent_pnl_text,
            "sharpe": sharpe, "fitness": fitness,
            "ops": ops_used, "failing_checks": stats.get("failing", []),
        })
        record_iteration(idx, {
            "expression": expr, "status": status,
            "sharpe": sharpe, "fitness": fitness,
            "turnover": stats.get("turnover"),
            "returns": stats.get("returns"),
            "failing_checks": stats.get("failing", []),
            "families": get_used_families(expr),
            "analysis": output.get("Analysis", ""),
            "strategy": output.get("Refinement Strategy", ""),
        })

    # -- Best-performer seed update ----------------------------------------
    # Pick the best non-pruned, non-failed alpha this iteration; make it the new seed
    best_fitness_this_iter = -999.0
    best_seed_candidate = None
    for _idx, (_summary, _sim) in enumerate(zip(agent_summaries, sim_results)):
        if _summary["status"] == "SUCCESS" and _sim and isinstance(_sim, dict):
            _f = _summary.get("fitness") or 0.0
            if _f > best_fitness_this_iter:
                best_fitness_this_iter = _f
                best_seed_candidate = {
                    "expression": _summary["expression"],
                    "sharpe":     _summary.get("sharpe") or 0.0,
                    "fitness":    _f,
                    "sim_result": _sim,
                    "agent_idx":  _summary["idx"],
                }
    if best_seed_candidate and best_fitness_this_iter > current_seed["fitness"]:
        current_seed = best_seed_candidate
        console.print(
            f"[bold green]Seed updated: Agent {current_seed['agent_idx']+1} "
            f"Fitness={current_seed['fitness']:.3f} is now the new seed.[/]"
        )
    elif best_seed_candidate:
        console.print(
            f"[cyan]Seed unchanged (Fitness={current_seed['fitness']:.3f}). "
            f"Best this iter={best_fitness_this_iter:.3f} did not improve.[/]"
        )

    # -- Step 4: Stop or continue -------------------------------------------
    if found_submittable:
        console.print("\n[bold purple]All agents stopping -- submittable alpha found![/]")
        exit()

    all_failed = all(s["status"] == "FAILED" for s in agent_summaries)
    if all_failed:
        console.print(
            f"[red]All {NUM_AGENTS} agents produced invalid expressions -- "
            f"not counting. Budget unchanged at {total_iterations}.[/]"
        )
        for idx in range(NUM_AGENTS):
            add_to_agent_context(idx, "user",
                f"Iteration #{successful_iterations + 1}\n"
                "All agents produced invalid expressions. Fix FastExpr syntax. "
                "Use only operators from the provided list. Try a simpler expression."
            )
        continue

    if not any_real_success:
        console.print(
            "[yellow]All successful simulations were pruned (far below median). "
            "Not counting this iteration -- agents must change approach.[/]"
        )
    else:
        successful_iterations += 1

    # -- Step 5: Pairwise similarity check ----------------------------------
    pairwise_sim: dict[tuple, float] = {}
    ok_summaries = [s for s in agent_summaries if s["status"] in ("SUCCESS", "PRUNED")]
    for i in range(len(ok_summaries)):
        for j in range(i + 1, len(ok_summaries)):
            a, b = ok_summaries[i], ok_summaries[j]
            sim  = jaccard_similarity(a["ops"], b["ops"])
            pairwise_sim[(a["idx"], b["idx"])] = sim
            if sim > 0.6:
                console.print(
                    f"[yellow]Agent {a['idx']+1} & {b['idx']+1} "
                    f"operator overlap: {sim:.0%}[/]"
                )

    # -- Step 6: Cross-learning with diversity pressure ---------------------
    console.print("\n[yellow]Cross-learning across agents...[/]")
    for idx in range(NUM_AGENTS):
        own    = agent_summaries[idx]
        others = [s for s in agent_summaries if s["idx"] != idx]

        sim_warnings = []
        for other in others:
            key = (min(idx, other["idx"]), max(idx, other["idx"]))
            sim = pairwise_sim.get(key, 0.0)
            if sim > 0.6:
                sim_warnings.append((other["idx"], sim))

        focus = get_focus_family(successful_iterations, idx)
        strat_name, strat_desc = get_mod_strategy(idx, successful_iterations)
        cross_msg = build_cross_learning_message(
            successful_iterations,
            own, others, focus, sim_warnings,
            is_pruned=(own["status"] == "PRUNED"),
            mod_strategy_name=strat_name,
            mod_strategy_desc=strat_desc,
        )
        if agent_stagnation[idx] >= STAGNATION_LIMIT:
            cross_msg += build_rebuild_directive()
            console.print(
                f"[bold red]Agent {idx + 1} | FORCED REBUILD "
                f"({agent_stagnation[idx]} iterations without beating incumbent)[/]"
            )
            agent_stagnation[idx] = 0   # reset after firing
        add_to_agent_context(idx, "user", cross_msg)

    if any_real_success:
        console.print(f"\n[bold]✓ Iteration {successful_iterations}/{total_iterations} complete.[/]\n")
    else:
        console.print(f"\n[yellow]All pruned -- retrying (budget: {total_iterations - successful_iterations} remaining).[/]\n")
