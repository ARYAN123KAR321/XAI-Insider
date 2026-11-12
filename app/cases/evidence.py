"""Evidence collection with SHA-256 integrity (plan §10.2)."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.cases.workflow import log_audit
from app.config.settings import get_settings
from app.db.models import Alert, Event, EvidenceItem, Explanation, FeatureWindow, Upload
from app.ingestion.hashing import sha256_bytes, sha256_file
from app.util.ids import new_id


def _case_dir(case_id: str) -> Path:
    d = get_settings().cases_dir / case_id / "evidence"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _add_item(db, case_id, item_type, source_ref, data: bytes, actor_id, suffix=".json") -> EvidenceItem:
    item_id = new_id("evi")
    safe_ref = "".join(c if c.isalnum() or c in "-_:" else "_" for c in source_ref)[:60]
    path = _case_dir(case_id) / f"{item_id}_{safe_ref}{suffix}"
    path.write_bytes(data)
    item = EvidenceItem(id=item_id, case_id=case_id, item_type=item_type,
                        source_reference=source_ref, stored_path=str(path),
                        sha256=sha256_bytes(data), size_bytes=len(data),
                        collected_by=actor_id)
    db.add(item)
    return item


def collect_evidence(db, case, actor_id: str | None) -> int:
    """Snapshot alerts, explanations, window events, and source-file hashes."""
    existing = db.execute(select(EvidenceItem)
                          .where(EvidenceItem.case_id == case.id)).scalars().all()
    existing_refs = {e.source_reference for e in existing}
    added = 0

    for alert_id in case.alert_ids:
        alert = db.get(Alert, alert_id)
        if not alert:
            continue

        ref = f"alert:{alert_id}"
        if ref not in existing_refs:
            data = json.dumps({
                "alert_id": alert.id, "employee_id": alert.employee_id,
                "window_start": alert.window_start.isoformat(),
                "window_end": alert.window_end.isoformat(),
                "raw_score": alert.raw_score, "normalized_score": alert.normalized_score,
                "priority_score": alert.priority_score, "priority_band": alert.priority_band,
                "run_id": alert.run_id,
            }, indent=2).encode()
            _add_item(db, case.id, "alert", ref, data, actor_id)
            existing_refs.add(ref)
            added += 1

        expl = db.execute(select(Explanation)
                          .where(Explanation.alert_id == alert_id)).scalars().first()
        ref = f"explanation:{alert_id}"
        if expl and ref not in existing_refs:
            data = json.dumps({
                "explanation_id": expl.id, "alert_id": alert_id, "method": expl.method,
                "baseline_used": expl.baseline_used, "feature_reasons": expl.feature_reasons,
                "evidence_event_ids": expl.evidence_event_ids, "caveats": expl.caveats,
            }, indent=2).encode()
            _add_item(db, case.id, "explanation", ref, data, actor_id)
            existing_refs.add(ref)
            added += 1

        window = db.get(FeatureWindow, alert.window_id)
        ref = f"events:{alert_id}"
        if window and ref not in existing_refs:
            evs = db.execute(select(Event)
                             .where(Event.id.in_(window.source_event_ids))).scalars().all()
            lines = [json.dumps({
                "event_id": e.event_id, "timestamp_utc": e.timestamp_utc.isoformat(),
                "employee_id": e.employee_id, "host_id": e.host_id,
                "event_type": e.event_type, "metadata": e.metadata_,
                "source_file_id": e.source_file_id, "source_record_id": e.source_record_id,
                "raw_record_hash": e.raw_record_hash,
            }) for e in sorted(evs, key=lambda x: x.timestamp_utc)]
            _add_item(db, case.id, "events", ref, ("\n".join(lines)).encode(),
                      actor_id, suffix=".jsonl")
            existing_refs.add(ref)
            added += 1

            for up_id in sorted({e.source_file_id for e in evs}):
                ref2 = f"source_file:{up_id}"
                if ref2 in existing_refs:
                    continue
                up = db.get(Upload, up_id)
                if up:
                    _add_item(db, case.id, "source_file_ref", ref2, json.dumps({
                        "upload_id": up.id, "original_name": up.original_name,
                        "sha256_at_upload": up.sha256,
                        "sha256_current": sha256_file(up.stored_path),
                    }, indent=2).encode(), actor_id)
                    added += 1
                existing_refs.add(ref2)

    if added:
        log_audit(db, actor_id, "case.collect_evidence", "case", case.id,
                  {"items_added": added})
    db.commit()
    return added