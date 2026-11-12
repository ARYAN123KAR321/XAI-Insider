"""Evaluation against synthetic scenario labels (labels never used in training)."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from sklearn.metrics import precision_score, recall_score, roc_auc_score, average_precision_score


def _naive_utc(dt):
    """Normalize any datetime to naive UTC so naive/aware values compare safely."""
    if getattr(dt, "tzinfo", None) is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _parse_iso_utc(s: str) -> datetime:
    return _naive_utc(datetime.fromisoformat(str(s).replace("Z", "+00:00")))


def label_windows(windows: list, scenarios: list) -> np.ndarray:
    """1 if the window belongs to the scenario employee and overlaps the scenario span."""
    y = np.zeros(len(windows), dtype=int)
    spans = {}
    for s in scenarios:
        spans.setdefault(s["employee_id"], []).append(
            (_parse_iso_utc(s["start"]), _parse_iso_utc(s["end"]), s["scenario_id"]))
    for i, w in enumerate(windows):
        ws, we = _naive_utc(w.start), _naive_utc(w.end)
        for start, end, _ in spans.get(w.employee_id, []):
            if ws < end and we > start:
                y[i] = 1
                break
    return y


def evaluate(windows: list, normalized: np.ndarray, alerted: np.ndarray,
             scenarios: list) -> dict:
    y = label_windows(windows, scenarios)
    metrics: dict = {
        "windows_scored": int(len(windows)),
        "positive_windows": int(y.sum()),
        "alerts_raised": int(alerted.sum()),
    }
    if y.sum() == 0:
        metrics["note"] = "no labelled positives in test split"
        return metrics

    metrics["precision"] = round(float(precision_score(y, alerted, zero_division=0)), 4)
    metrics["recall"] = round(float(recall_score(y, alerted, zero_division=0)), 4)
    try:
        metrics["pr_auc"] = round(float(average_precision_score(y, normalized)), 4)
        metrics["roc_auc"] = round(float(roc_auc_score(y, normalized)), 4)
    except ValueError:
        metrics["pr_auc"] = None
        metrics["roc_auc"] = None
    n_neg = int((y == 0).sum())
    fp = int(((alerted == 1) & (y == 0)).sum())
    metrics["false_positive_rate"] = round(fp / n_neg, 4) if n_neg else None
    metrics["false_alerts"] = fp

    # per-scenario recall + detection delay
    per_scenario = []
    for s in scenarios:
        s_start = _parse_iso_utc(s["start"])
        s_end = _parse_iso_utc(s["end"])
        hits = [w for i, w in enumerate(windows)
                if w.employee_id == s["employee_id"]
                and _naive_utc(w.start) < s_end and _naive_utc(w.end) > s_start
                and alerted[i] == 1]
        covered = len(hits) > 0
        delay_min = round((_naive_utc(min(h.start for h in hits)) - s_start).total_seconds() / 60.0, 1) \
            if covered else None
        per_scenario.append({"scenario_id": s["scenario_id"], "employee_id": s["employee_id"],
                             "detected": covered, "detection_delay_minutes": delay_min,
                             "severity": s.get("severity")})
    metrics["scenarios"] = per_scenario
    return metrics