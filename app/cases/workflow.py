"""Case lifecycle operations with append-only audit logging (plan §10.1)."""
from __future__ import annotations

from app.db.models import AuditLog, Case, CaseNote
from app.util.ids import new_id, utcnow

CASE_TRANSITIONS = {
    "open": {"under_review"},
    "under_review": {"pending_approval", "open"},
    "pending_approval": {"closed", "under_review"},
}


def log_audit(db, actor_id: str | None, action: str, object_type: str, object_id: str,
              details: dict | None = None):
    db.add(AuditLog(id=new_id("aud"), actor_id=actor_id, action=action,
                    object_type=object_type, object_id=object_id, details=details))


def create_case(db, title: str, owner_id: str | None, priority: str = "medium") -> Case:
    case = Case(id=new_id("case"), title=title, owner_id=owner_id, priority=priority,
                status="open")
    db.add(case)
    log_audit(db, owner_id, "case.create", "case", case.id, {"title": title})
    db.commit()
    db.refresh(case)
    return case


def link_alert(db, case: Case, alert_id: str, actor_id: str | None):
    if alert_id not in case.alert_ids:
        case.alert_ids = list(case.alert_ids) + [alert_id]
        case.updated_at = utcnow()
        log_audit(db, actor_id, "case.link_alert", "case", case.id, {"alert_id": alert_id})
        db.commit()


def add_note(db, case: Case, text: str, author_id: str | None) -> CaseNote:
    note = CaseNote(id=new_id("note"), case_id=case.id, author_id=author_id, note_text=text)
    db.add(note)
    case.updated_at = utcnow()
    log_audit(db, author_id, "case.note", "case", case.id)
    db.commit()
    db.refresh(note)
    return note


def set_status(db, case: Case, status: str, actor_id: str | None):
    allowed = CASE_TRANSITIONS.get(case.status, set())
    if status not in allowed and not (status == "closed" and case.status == "pending_approval"):
        raise ValueError(f"invalid case transition {case.status} -> {status}")
    case.status = status
    case.updated_at = utcnow()
    log_audit(db, actor_id, "case.status", "case", case.id, {"status": status})
    db.commit()


def set_disposition(db, case: Case, disposition: str, rationale: str | None, actor_id: str | None):
    case.disposition = disposition
    case.disposition_rationale = rationale
    if disposition in ("benign", "suspicious", "inconclusive"):
        case.status = "closed"
        case.closed_at = utcnow()
    else:
        case.status = "open"
    case.updated_at = utcnow()
    log_audit(db, actor_id, "case.disposition", "case", case.id, {"disposition": disposition})
    db.commit()