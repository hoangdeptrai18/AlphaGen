import ast
import json
from datetime import datetime
from itertools import groupby

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from rich.console import Console

console = Console()


def copy(simulation_result):
    with open("alpha.json") as f:
        alpha = json.load(f)

    alpha["type"] = simulation_result["type"]
    alpha["regular"] = simulation_result["regular"]["code"]
    for key in alpha["settings"].keys() & simulation_result["settings"].keys():
        alpha["settings"][key] = simulation_result["settings"][key]

    return alpha


def extract_datafields(alpha_expression):
    """
    Extract datafield names from a FastExpr alpha expression using regex.
    Avoids ast.parse() which fails on FastExpr keywords like and(...), or(...).

    Strategy:
    - Collect all identifiers (word tokens)
    - Remove known operators (anything followed by '(')
    - Remove assignment left-hand sides (anything before '=')
    - Remove Python/FastExpr reserved words and pure-numeric tokens
    """
    import re as _re

    RESERVED = {
        # Python keywords
        "and", "or", "not", "if", "else", "nan", "None", "True", "False",
        "in", "is", "lambda", "for", "while", "return",
        # FastExpr keywords / constants
        "nan", "inf",
    }

    # All identifiers (letters/digits/underscore, starting with letter or _)
    all_ids = set(_re.findall(r'\b([A-Za-z_]\w*)\b', alpha_expression))

    # Operators = identifiers immediately followed by '(' (function calls)
    operators = set(_re.findall(r'\b([A-Za-z_]\w*)\s*\(', alpha_expression))

    # Assignment targets = identifiers before '='  (but not '==' / '!=' / '<=' / '>=')
    assignments = set(_re.findall(r'\b([A-Za-z_]\w*)\s*(?<![=!<>])=(?!=)', alpha_expression))

    datafields = all_ids - operators - assignments - RESERVED
    return sorted(datafields)


def get_insample_context(insample):
    insample_context = []
    checks = insample["checks"]

    ignore = [
        "checks",
        "bookSize",
        "startDate",
        "investabilityConstrained",
        "riskNeutralized",
        "selfCorrelation",
        "prodCorrelation",
    ]

    for key in insample:
        if key in ignore:
            continue
        insample_context.append(f"{key}: {insample[key]}")

    for check in checks:
        result = check["result"]
        name = check["name"]

        if name in ["MATCHES_PYRAMID", "MATCHES_THEMES"]:
            continue

        if result in ["PENDING", "PASS"]:
            continue

        # check_string = f"{check["name"]}: {check["result"]}"
        check_string = f"{check['name']}: FAIL"
        if "limit" in check:
            check_string += f", limit: {check['limit']}, value: {check['value']}"
        insample_context.append(check_string)

    return "\n".join(insample_context)


def fix_fastexpr(alpha_expression):
    alpha_expression = alpha_expression.replace("\n", "").replace("; ", ";").replace(";", ";\n")
    alpha_expression = alpha_expression.strip()
    return alpha_expression


def reverse_fastexpr(alpha_expression):
    statements = [s.strip() for s in alpha_expression.split(";") if s.strip()]
    last_statement = statements[-1]

    if "=" in last_statement:
        parts = last_statement.split("=", 1)
        var_name = parts[0].strip()
        expr_body = parts[1].strip()
        negated_last = f"{var_name} = -1 * ({expr_body})"
    else:
        negated_last = f"-1 * ({last_statement})"

    statements[-1] = negated_last
    return ";\n".join(statements) + ";"


def generate_pnl_chart(pnl_config, pnl_data):
    def format_y(value, _):
        """Render large values with K/M suffix and preserve sign."""
        v = float(value)
        sign = "-" if v < 0 else ""
        abs_val = abs(v)
        if abs_val >= 1e7:
            val, suffix = abs_val / 1e6, "M"
        elif abs_val >= 1e4:
            val, suffix = abs_val / 1e3, "K"
        else:
            return f"{v:,.0f}" if v.is_integer() else f"{v:,.1f}"
        return (
            f"{sign}{val:,.0f}{suffix}"
            if val.is_integer()
            else f"{sign}{val:,.1f}{suffix}"
        )

    num_series = len(pnl_data[0]) - 1
    cols = [list(col) for col in zip(*pnl_data)]
    dates = [datetime.strptime(d, "%Y-%m-%d") for d in cols[0]]
    series_values = [list(col) for col in cols[1 : num_series + 1]]

    n_points = len(series_values[0])
    test_len = pnl_config["test"]
    highlight_start = max(0, n_points - test_len)

    tick_candidates = []
    for _, group in groupby(dates, key=lambda d: d.year):
        year_dates = list(group)
        tick_candidates.append(year_dates[0])
        tick_candidates.append(year_dates[len(year_dates) // 2])

    endpoints = {dates[0], dates[-1]}
    ticks = sorted({dt for dt in tick_candidates if dt not in endpoints})

    filtered_labels = []
    prev_label = None
    for dt in ticks:
        label = dt.strftime("%b '%y")
        if label != prev_label:
            filtered_labels.append((dt, label))
            prev_label = label

    idx_by_date = {dt: i for i, dt in enumerate(dates)}
    positions = [idx_by_date[dt] for dt, _ in filtered_labels]
    labels = [lbl for _, lbl in filtered_labels]

    train_color = pnl_config["color"]["train"]
    test_color = pnl_config["color"]["test"]

    fig, ax = plt.subplots(figsize=(10, 5), dpi=500, facecolor="white")
    x_full = range(n_points)
    x_train = range(highlight_start)
    lw = 0.7
    ls = "-"

    for idx, svals in enumerate(series_values):
        # First series: split styling (test full, train overlay) — keep existing behavior
        if idx == 0:
            ax.plot(
                x_full, svals, linewidth=lw, linestyle=ls, color=test_color, alpha=1.0
            )
            if highlight_start > 0:
                ax.plot(
                    x_train,
                    svals[:highlight_start],
                    linewidth=lw,
                    linestyle=ls,
                    color=train_color,
                    alpha=1.0,
                )
        # Second series: use secondary_color for the full graph (no train/test split)
        elif idx == 1:
            col = pnl_config["color"]["secondary"]
            ax.plot(x_full, svals, linewidth=lw, linestyle=ls, color=col, alpha=1.0)
        # Third series (if present): use tertiary_color for the full graph
        elif idx == 2:
            col = pnl_config["color"]["tertiary"]
            ax.plot(x_full, svals, linewidth=lw, linestyle=ls, color=col, alpha=1.0)

    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=0, ha="right", color="#7b8292", fontsize=8)
    ax.yaxis.set_major_formatter(FuncFormatter(format_y))
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.5)
    for spine in ["top", "left", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#ccd6eb")
    ax.tick_params(axis="y", colors="#7b8292", labelsize=8)
    ax.set_xlim(left=0)
    plt.tight_layout()
    plt.savefig(pnl_config["name"], dpi=500, bbox_inches="tight")
    plt.close(fig)


def strict_submissibility(checks):
    for check in checks:
        result = check["result"]
        name = check["name"]

        if name in ["MATCHES_PYRAMID", "MATCHES_THEMES"]:
            continue

        if result in ["PENDING", "PASS"]:
            continue

        if result in ["FAIL", "WARNING"]:
            return False

    return True
