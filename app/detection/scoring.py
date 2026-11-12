"""Score normalization, corroboration, and triage priority bands (plan §8.3)."""
from __future__ import annotations

import numpy as np

from app.config.settings import get_settings


def normalize_scores(sorted_calib: np.ndarray, raw: np.ndarray) -> np.ndarray:
    if len(sorted_calib) == 0:
        return np.full(len(raw), 50.0)
    ranks = np.searchsorted(sorted_calib, raw, side="right")
    return 100.0 * ranks / len(sorted_calib)


def corroboration_score(feats: dict) -> float:
    """Bounded, transparent corroboration signals (0..1)."""
    s = 0.0
    if feats.get("file_usb_sequence_flag", 0) >= 1.0:
        s += 0.4
    if feats.get("first_seen_device_flag", 0) >= 1.0:
        s += 0.2
    if feats.get("sensitive_tag_reads", 0) > 2:
        s += 0.2
    if feats.get("off_hours_activity_ratio", 0) > 0.5:
        s += 0.2
    return min(s, 1.0)


def priority_score(normalized: float, feats: dict) -> float:
    settings = get_settings()
    return (settings.priority_model_weight * normalized
            + settings.priority_corroboration_weight * corroboration_score(feats) * 100.0)


def priority_band(pscore: float) -> str:
    settings = get_settings()
    if pscore >= settings.high_band:
        return "high"
    if pscore >= settings.medium_band:
        return "medium"
    return "low"