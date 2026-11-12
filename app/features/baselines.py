"""Hierarchical baselines: employee -> peer group (role) -> global (plan §7.3)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.config.settings import get_settings
from app.features.registry import FEATURE_NAMES

MAD_FLOOR = 1e-3
EPS = 1e-6


def _median_mad(df: pd.DataFrame) -> dict:
    out = {}
    for col in FEATURE_NAMES:
        s = df[col].astype(float)
        med = float(s.median()) if len(s) else 0.0
        mad = float((s - med).abs().median()) if len(s) else 0.0
        out[col] = {"median": med, "mad": max(mad, MAD_FLOOR)}
    return out


def compute_baselines(windows_df: pd.DataFrame) -> dict:
    """windows_df must contain only training-period windows."""
    settings = get_settings()
    baselines = {"employee": {}, "peer": {}, "global": _median_mad(windows_df)}

    if "role" in windows_df.columns:
        for role, rdf in windows_df.groupby("role"):
            baselines["peer"][role] = _median_mad(rdf)

    counts = windows_df.groupby("employee_id").size()
    for emp_id, edf in windows_df.groupby("employee_id"):
        if int(counts.get(emp_id, 0)) >= settings.min_employee_baseline_windows:
            baselines["employee"][emp_id] = _median_mad(edf)
    return baselines


def baseline_for(baselines: dict, employee_id: str, role: str | None) -> tuple[dict, str]:
    if employee_id in baselines.get("employee", {}):
        return baselines["employee"][employee_id], "employee"
    if role and role in baselines.get("peer", {}):
        return baselines["peer"][role], "peer"
    return baselines["global"], "global"


def robust_z(value: float, stats: dict) -> float:
    mad = max(stats["mad"], MAD_FLOOR)
    return (value - stats["median"]) / (1.4826 * mad + EPS)