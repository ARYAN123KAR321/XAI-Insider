"""Constrained what-if (model sensitivity) analysis - plan §9.4.

This is a model-sensitivity illustration, NOT an evasion recipe and NOT a causal
claim. Only mutable numeric features may change, values are clipped to valid
ranges, timestamps/identity/hashes are never touched.
"""
from __future__ import annotations

import numpy as np

from app.db.models import Counterfactual
from app.detection.model import raw_scores
from app.detection.preprocessing import transform
from app.detection.scoring import normalize_scores
from app.features.baselines import baseline_for, robust_z
from app.features.registry import FEATURE_BY_NAME
from app.util.ids import new_id

DISCLAIMER = ("Hypothetical model-sensitivity result on synthetic data. It does not modify "
              "evidence, does not prove causation, and must not be used as an evasion guide.")


def run_counterfactual(artifact: dict, window, alert, requested_by: str | None) -> Counterfactual:
    names = artifact["feature_names"]
    baselines = artifact["baselines"]
    emp_meta = artifact["employee_meta"].get(window.employee_id) or {}
    base_stats, _ = baseline_for(baselines, window.employee_id, emp_meta.get("role"))

    x = np.array([window.features[n] for n in names], dtype=float)

    def norm_score(vec: np.ndarray) -> float:
        raw = raw_scores(artifact["model"],
                         transform(artifact["preprocessor"], vec.reshape(1, -1)))[0]
        return float(normalize_scores(artifact["calib_sorted"], np.array([raw]))[0])

    original = norm_score(x)

    # candidate features: mutable, observed above baseline, |z| meaningful
    candidates = []
    for i, n in enumerate(names):
        reg = FEATURE_BY_NAME[n]
        if not reg["mutable"]:
            continue
        stats = base_stats[n]
        if x[i] <= stats["median"] or robust_z(x[i], stats) < 1.0:
            continue
        candidates.append((i, n, abs(robust_z(x[i], stats))))
    candidates.sort(key=lambda c: -c[2])
    candidates = candidates[:6]

    best = {"score": original, "changes": []}

    def _clip(i, value):
        reg = FEATURE_BY_NAME[names[i]]
        lo = reg.get("vmin") if reg.get("vmin") is not None else -np.inf
        hi = reg.get("vmax") if reg.get("vmax") is not None else np.inf
        return float(np.clip(value, lo, hi))

    # single-feature candidates
    for i, n, _ in candidates:
        vec = x.copy()
        vec[i] = _clip(i, base_stats[n]["median"])
        s = norm_score(vec)
        if s < best["score"]:
            best = {"score": s, "changes": [(i, x[i], vec[i])]}

    # top-2 combined candidate
    if len(candidates) >= 2:
        vec = x.copy()
        changes = []
        for i, n, _ in candidates[:2]:
            vec[i] = _clip(i, base_stats[n]["median"])
            changes.append((i, x[i], vec[i]))
        s = norm_score(vec)
        if s < best["score"]:
            best = {"score": s, "changes": changes}

    changes_out = [{
        "feature": names[i],
        "original_value": float(orig),
        "hypothetical_value": float(new),
        "unit": FEATURE_BY_NAME[names[i]]["unit"],
    } for (i, orig, new) in best["changes"]]

    return Counterfactual(
        id=new_id("cf"), alert_id=alert.id, original_score=round(original, 2),
        hypothetical_score=round(best["score"], 2), changes=changes_out,
        constraints={
            "policy": "immutable fields (identity, timestamps, hashes, ratios/flags) never modified",
            "mutable_features_considered": [names[i] for i, _, _ in candidates],
            "clip_to_valid_range": True,
            "disclaimer": DISCLAIMER,
        },
        requested_by=requested_by)