"""Local explanations: robust-z feature deviations + ablation deltas + evidence links.

We deliberately avoid claiming exact SHAP contributions for Isolation Forest;
ablation against the fitted pipeline is used as a labelled approximation (plan §9.2).
"""
from __future__ import annotations

import numpy as np

from app.config.settings import get_settings
from app.db.models import Explanation
from app.detection.model import raw_scores
from app.detection.preprocessing import transform
from app.features.baselines import baseline_for, robust_z
from app.features.registry import EVIDENCE_FAMILY_MAP, FEATURE_BY_NAME
from app.util.ids import new_id

METHOD = "robust-z deviation + single-feature ablation (approximation)"
CAVEATS = ("This explanation approximates the anomaly model's sensitivity; it is not proof of "
           "intent or misconduct. Rare behaviour can have legitimate explanations (travel, role "
           "change, emergency work). Verify against authorizations and assignment context.")


def explain_window(artifact: dict, window, events: list[dict], alert_id: str) -> Explanation:
    settings = get_settings()
    names = artifact["feature_names"]
    baselines = artifact["baselines"]
    emp_meta = artifact["employee_meta"].get(window.employee_id) or {}
    base_stats, base_used = baseline_for(baselines, window.employee_id, emp_meta.get("role"))

    x = np.array([[window.features[n] for n in names]], dtype=float)
    base_raw = raw_scores(artifact["model"], transform(artifact["preprocessor"], x))[0]

    scored = []
    for i, n in enumerate(names):
        stats = base_stats[n]
        z = robust_z(window.features[n], stats)
        if abs(z) < 1.0:
            continue
        # ablation: replace this feature with its baseline median and re-score
        x_mod = x.copy()
        x_mod[0, i] = stats["median"]
        mod_raw = raw_scores(artifact["model"], transform(artifact["preprocessor"], x_mod))[0]
        scored.append({
            "feature": n,
            "group": FEATURE_BY_NAME[n]["group"],
            "observed": float(window.features[n]),
            "baseline_median": round(stats["median"], 4),
            "robust_z": round(float(z), 2),
            "ablation_delta_score": round(float(mod_raw - base_raw), 4),  # negative => feature raised the score
            "description": FEATURE_BY_NAME[n]["description"],
        })

    scored.sort(key=lambda r: (-abs(r["ablation_delta_score"]), -abs(r["robust_z"])))
    top = scored[: settings.explanation_top_k]

    # attach evidence events for the top reasons
    evidence_ids: list[str] = []
    window_events = [e for e in events if e["id"] in set(window.event_ids)]
    for reason in top:
        fam = EVIDENCE_FAMILY_MAP.get(reason["feature"])
        fams = fam if isinstance(fam, list) else ([fam] if fam else [])
        matched = [e["event_id"] for e in window_events if e["event_type"] in fams][:6]
        reason["evidence_event_ids"] = matched
        for eid in matched:
            if eid not in evidence_ids:
                evidence_ids.append(eid)

    return Explanation(
        id=new_id("exp"), alert_id=alert_id, method=METHOD, baseline_used=base_used,
        feature_reasons=top, evidence_event_ids=evidence_ids[:24], caveats=CAVEATS)