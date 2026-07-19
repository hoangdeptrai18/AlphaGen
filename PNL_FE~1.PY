"""
pnl_features.py — Turn a PnL recordset into text an LLM can reason about.

The chart (pnl_chart.png) is written to disk for the human. The LLM is text-only,
so we extract the *shape* of the equity curve as numbers instead of pixels.

Primary focus: train vs test decay detection.
"""

import statistics
from datetime import datetime


def _to_series(pnl_data):
    """
    pnl_data: list of rows, row[0] = 'YYYY-MM-DD', row[1] = cumulative PnL.
    Returns (dates, cumulative_pnl) with non-parseable rows dropped.
    """
    dates, cum = [], []
    for row in pnl_data:
        if not row or len(row) < 2:
            continue
        try:
            d = datetime.strptime(str(row[0]), "%Y-%m-%d")
            v = float(row[1])
        except (ValueError, TypeError):
            continue
        dates.append(d)
        cum.append(v)
    return dates, cum


def _daily_from_cum(cum):
    """Cumulative PnL -> daily increments."""
    return [cum[i] - cum[i - 1] for i in range(1, len(cum))]


def _sharpe(daily):
    """Annualised Sharpe from daily PnL increments (252 trading days)."""
    if len(daily) < 20:
        return None
    mu = statistics.mean(daily)
    try:
        sd = statistics.stdev(daily)
    except statistics.StatisticsError:
        return None
    if sd == 0:
        return None
    return round(mu / sd * (252 ** 0.5), 3)


def _max_drawdown(cum):
    """
    Max drawdown on a cumulative PnL curve (absolute, not %, since PnL can cross 0).
    Returns (depth, trough_index, peak_index).
    """
    if not cum:
        return 0.0, 0, 0
    peak = cum[0]
    peak_i = 0
    best_dd = 0.0
    best_trough = 0
    best_peak = 0
    for i, v in enumerate(cum):
        if v > peak:
            peak, peak_i = v, i
        dd = peak - v
        if dd > best_dd:
            best_dd, best_trough, best_peak = dd, i, peak_i
    return best_dd, best_trough, best_peak


def _flatness(cum, split):
    """
    Compare the slope of the holdout against the slope of the training period.

    The split MUST be the same one the chart draws (n - test_len), otherwise the
    two periods get mixed and a genuinely flat tail is diluted by the rising part
    that precedes it.

    Returns (holdout_slope_per_day, train_slope_per_day, ratio).
    """
    n = len(cum)
    if n < 60 or split < 20 or split >= n - 5:
        return None, None, None
    train_slope = (cum[split] - cum[0]) / max(1, split)
    late_slope = (cum[-1] - cum[split]) / max(1, n - 1 - split)
    if train_slope == 0:
        return late_slope, train_slope, None
    return late_slope, train_slope, late_slope / train_slope


def build_pnl_features(pnl_data, test_len: int = 252) -> str:
    """
    Build a compact text block describing the PnL curve shape.

    test_len must match config['pnl_chart']['test'] so the split the LLM reads
    is the same one drawn on the chart.
    """
    dates, cum = _to_series(pnl_data)
    if len(cum) < 60:
        return "PnL Curve Analysis: insufficient data to characterise the curve."

    n = len(cum)
    split = max(1, n - test_len)

    daily = _daily_from_cum(cum)
    # daily[i] corresponds to cum[i+1]; train increments end at index split-1
    train_daily = daily[: max(0, split - 1)]
    test_daily = daily[max(0, split - 1):]

    sh_full = _sharpe(daily)
    sh_train = _sharpe(train_daily)
    sh_test = _sharpe(test_daily)

    lines = ["PnL Curve Analysis (derived from the equity curve, not from summary stats):"]
    lines.append(
        f"  Period: {dates[0].strftime('%Y-%m-%d')} to {dates[-1].strftime('%Y-%m-%d')} "
        f"({n} days). Holdout = last {test_len} days "
        f"(from {dates[split].strftime('%Y-%m-%d')})."
    )

    # ── Train vs test decay — the headline diagnostic ─────────────────────
    lines.append("")
    lines.append("  [TRAIN vs TEST]")
    lines.append(f"  Sharpe full sample : {sh_full}")
    lines.append(f"  Sharpe train       : {sh_train}")
    lines.append(f"  Sharpe holdout     : {sh_test}")

    verdict = None
    if sh_train is not None and sh_test is not None:
        if sh_train != 0:
            retention = sh_test / sh_train
            lines.append(f"  Holdout retention  : {retention:.0%} of train Sharpe")
        else:
            retention = None

        if sh_test < 0 <= sh_train:
            verdict = (
                "SIGN BREAKDOWN — the signal made money in-sample and LOSES money "
                "out-of-sample. The relationship did not hold. Do NOT tune this "
                "expression; the hypothesis itself is wrong. Rebuild from a "
                "different economic hypothesis."
            )
        elif retention is not None and retention < 0.3:
            verdict = (
                "SEVERE DECAY — the edge has largely disappeared out-of-sample. "
                "This is the signature of overfitting to the training window, or of "
                "an anomaly that has been arbitraged away. Adding operator layers "
                "will make this WORSE, not better. Change the hypothesis or the "
                "datafield, not the parameters."
            )
        elif retention is not None and retention < 0.6:
            verdict = (
                "MODERATE DECAY — the edge weakens out-of-sample. Suspect mild "
                "overfitting or a crowded signal. Prefer structural simplification "
                "or orthogonalisation (M3) over adding complexity."
            )
        elif retention is not None and retention > 1.5:
            verdict = (
                "HOLDOUT STRONGER THAN TRAIN — unusual. Likely a regime effect "
                "rather than a robust edge; the recent period may simply suit this "
                "signal. Do not over-trust it."
            )
        else:
            verdict = (
                "STABLE — the edge persists out-of-sample. This structure is worth "
                "building on; recombine its components rather than discarding them."
            )
    if verdict:
        lines.append(f"  VERDICT: {verdict}")

    # ── Curve shape: is the recent portion flat? ──────────────────────────
    late, early, ratio = _flatness(cum, split)
    if ratio is not None:
        lines.append("")
        lines.append("  [CURVE SHAPE]")
        lines.append(
            f"  Slope during train   : {early:,.0f} PnL/day"
        )
        lines.append(
            f"  Slope during holdout : {late:,.0f} PnL/day  ({ratio:.0%} of train slope)"
        )
        if ratio < 0.15:
            lines.append(
                "  → The curve has gone FLAT in the holdout: the alpha has essentially "
                "STOPPED generating PnL. The headline Sharpe is propped up by old "
                "history and conceals this. Treat the holdout slope, not the summary "
                "stat, as the alpha's true current quality."
            )
        elif ratio < 0.5:
            lines.append(
                "  → The curve is FLATTENING in the holdout. The edge is fading, even "
                "if the summary Sharpe still looks acceptable."
            )

    # ── Drawdown ─────────────────────────────────────────────────────────
    dd, trough_i, peak_i = _max_drawdown(cum)
    if dd > 0:
        lines.append("")
        lines.append("  [DRAWDOWN]")
        lines.append(
            f"  Max drawdown: {dd:,.0f} PnL, from {dates[peak_i].strftime('%Y-%m')} "
            f"to {dates[trough_i].strftime('%Y-%m')} ({trough_i - peak_i} days)"
        )
        # Did it ever recover?
        peak_val = cum[peak_i]
        recovered = next((i for i in range(trough_i, n) if cum[i] >= peak_val), None)
        if recovered is None:
            lines.append(
                f"  → NEVER RECOVERED to the {dates[peak_i].strftime('%Y-%m')} peak "
                "by the end of the sample."
            )
        else:
            lines.append(
                f"  → Recovered after {recovered - trough_i} days "
                f"({dates[recovered].strftime('%Y-%m')})."
            )

    lines.append("")
    lines.append(
        "  NOTE: These numbers describe the SHAPE of the equity curve over time. "
        "The headline Sharpe/Fitness are single averages over the whole history and "
        "can conceal a dead recent period. When the two disagree, trust the shape."
    )

    return "\n".join(lines)
