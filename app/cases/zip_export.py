"""Evidence ZIP package with manifest + SHA256SUMS + verification (plan §10.4)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from sqlalchemy import select

from app.config.settings import get_settings
from app.db.models import Case, CaseNote, EvidenceItem
from app.ingestion.hashing import sha256_bytes, sha256_file
from app.util.ids import utcnow

_SAFE_PARTS = {"report.pdf", "manifest.json"}


def _safe_arcname(arc: str) -> str:
    """Prevent path traversal when creating or extracting archives (§13.2)."""
    parts = [p for p in arc.replace("\\", "/").split("/") if p and p not in (".", "..")]
    if not parts:
        raise ValueError(f"unsafe archive name: {arc}")
    return "/".join(parts)


def build_evidence_zip(db, case: Case, pdf_path: Path) -> tuple[Path, dict, bool]:
    settings = get_settings()
    out_dir = settings.exports_dir / case.id
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"case_{case.id}_evidence.zip"

    items = db.execute(select(EvidenceItem).where(EvidenceItem.case_id == case.id)).scalars().all()
    notes = db.execute(select(CaseNote).where(CaseNote.case_id == case.id)
                       .order_by(CaseNote.created_at)).scalars().all()

    files: list[tuple[str, bytes, str]] = []
    files.append(("report.pdf", pdf_path.read_bytes(), f"report:{case.id}"))

    for it in items:
        data = Path(it.stored_path).read_bytes()
        safe_ref = "".join(c if c.isalnum() or c in "-_:" else "_" for c in it.source_reference)
        if it.item_type == "events":
            arc = f"normalized_events/{safe_ref}.jsonl"
        elif it.item_type == "explanation":
            arc = f"explanations/{safe_ref}.json"
        elif it.item_type == "alert":
            arc = f"alerts/{safe_ref}.json"
        else:
            arc = f"source_files/{safe_ref}.json"
        files.append((arc, data, it.source_reference))

    notes_text = "\n\n".join(f"[{n.created_at.isoformat()}] {n.note_text}" for n in notes)
    files.append(("notes/investigator_notes.txt", notes_text.encode(), "notes"))

    sums = "\n".join(f"{sha256_bytes(data)}  {_safe_arcname(arc)}" for arc, data, _ in files)
    files.append(("hashes/SHA256SUMS.txt", sums.encode(), "hashes"))

    manifest = {
        "package_version": "1.0",
        "case_id": case.id,
        "generated_at_utc": utcnow().isoformat(),
        "synthetic": True,
        "files": [],
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc, data, ref in files:
            zf.writestr(_safe_arcname(arc), data)
            manifest["files"].append({
                "relative_path": _safe_arcname(arc),
                "size_bytes": len(data),
                "sha256": sha256_bytes(data),
                "source_reference": ref,
                "integrity_status": "verified",
            })

    result = verify_package(zip_path, manifest)
    manifest["verification_at_generation"] = result["integrity_status"]

    manifest_bytes = json.dumps(manifest, indent=2).encode()
    with zipfile.ZipFile(zip_path, "a") as zf:
        zf.writestr("manifest.json", manifest_bytes)
    (out_dir / "manifest.json").write_bytes(manifest_bytes)

    return zip_path, manifest, result["integrity_status"] == "verified"


def verify_package(zip_path: str | Path, manifest: dict) -> dict:
    """Independently re-hash every manifest-listed entry inside the ZIP (T-10)."""
    zip_path = Path(zip_path)
    mismatches: list[str] = []
    checked = 0
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
            for entry in manifest.get("files", []):
                rel = entry.get("relative_path", "")
                if rel in _SAFE_PARTS and rel == "manifest.json":
                    continue
                if rel not in names:
                    mismatches.append(f"missing:{rel}")
                    continue
                checked += 1
                if sha256_bytes(zf.read(rel)) != entry.get("sha256"):
                    mismatches.append(rel)
    except (zipfile.BadZipFile, OSError) as exc:
        return {"integrity_status": "unreadable", "files_checked": 0,
                "mismatches": [str(exc)]}
    return {"integrity_status": "verified" if not mismatches else "mismatch",
            "files_checked": checked, "mismatches": mismatches}