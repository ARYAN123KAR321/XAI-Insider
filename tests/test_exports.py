"""T-10: export hash verification detects a modified package."""
from __future__ import annotations

import json
import zipfile

from app.cases.zip_export import verify_package
from app.ingestion.hashing import sha256_bytes


def _build_zip(tmp_path):
    payload = b"alert payload v1"
    manifest = {"files": [{"relative_path": "alerts/alert_x.json",
                           "size_bytes": len(payload),
                           "sha256": sha256_bytes(payload),
                           "source_reference": "alert:x",
                           "integrity_status": "verified"}]}
    zpath = tmp_path / "case_x_evidence.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("alerts/alert_x.json", payload)
        zf.writestr("manifest.json", json.dumps(manifest))
    return zpath, manifest


def test_verify_passes(tmp_path):
    zpath, manifest = _build_zip(tmp_path)
    result = verify_package(zpath, manifest)
    assert result["integrity_status"] == "verified"
    assert result["files_checked"] == 1


def test_verify_detects_tampering(tmp_path):
    zpath, manifest = _build_zip(tmp_path)
    # attacker modifies a file inside a copy of the package
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(zpath) as src, zipfile.ZipFile(tampered, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "alerts/alert_x.json":
                data = b"alert payload TAMPERED"
            dst.writestr(name, data)
    result = verify_package(tampered, manifest)
    assert result["integrity_status"] == "mismatch"
    assert "alerts/alert_x.json" in result["mismatches"]


def test_verify_detects_missing_file(tmp_path):
    zpath, manifest = _build_zip(tmp_path)
    manifest["files"].append({"relative_path": "notes/extra.txt", "sha256": "0" * 64})
    result = verify_package(zpath, manifest)
    assert result["integrity_status"] == "mismatch"
    assert any(m.startswith("missing:") for m in result["mismatches"])