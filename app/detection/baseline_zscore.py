"""Robust z-score / percentile baseline detector (plan §8.4 — always implement).

Serves as an interpretable sanity-check model evaluated alongside Isolation Forest.
"""
from __future__ import annotations

import numpy as np

from app.features.baselines import baseline_for, robust_z
from app.features.registry import FEATURE_NAMES


def composite_scores(windows: list, baselines: dict, employee_meta: dict) -> np.ndarray:
    """Per-window anomaly indicator: max |robust-z| across all features."""
    out = np.zeros(len(windows))
    for i, w in enumerate(windows):
        meta = employee_meta.get(w.employee_id) or {}
        stats, _ = baseline_for(baselines, w.employee_id, meta.get("role"))
        out[i] = max(abs(robust_z(w.features[n], stats[n])) for n in FEATURE_NAMES)
    return out