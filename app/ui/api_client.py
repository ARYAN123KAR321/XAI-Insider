"""Thin HTTP client used by all Streamlit pages."""
from __future__ import annotations

import time
from pathlib import Path

import requests

from app.config.settings import get_settings


class ApiError(Exception):
    pass


class ApiClient:
    def __init__(self, token: str | None = None):
        self.base = get_settings().api_base_url.rstrip("/")
        self.token = token

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _req(self, method: str, path: str, **kw):
        resp = requests.request(method, f"{self.base}/api/v1{path}",
                                headers=self._headers(), timeout=180, **kw)
        if resp.status_code >= 400:
            try:
                body = resp.json()
                detail = body.get("message") or body.get("detail") or resp.text
            except Exception:  # noqa: BLE001
                detail = resp.text
            raise ApiError(f"HTTP {resp.status_code}: {detail}")
        return resp

    # auth
    def login(self, username: str, password: str) -> dict:
        return self._req("POST", "/auth/login",
                         json={"username": username, "password": password}).json()

    # ingestion
    def generate_dataset(self, seed: int, days: int) -> dict:
        return self._req("POST", "/simulator/generate", json={"seed": seed, "days": days}).json()

    def upload_file(self, path: Path, family: str, dataset_id: str | None,
                    dataset_name: str | None) -> dict:
        with open(path, "rb") as fh:
            return self._req("POST", "/uploads",
                             files={"file": (path.name, fh)},
                             data={"family": family,
                                   "dataset_id": dataset_id or "",
                                   "dataset_name": dataset_name or ""}).json()

    def job(self, job_id: str) -> dict:
        return self._req("GET", f"/jobs/{job_id}").json()

    def validation_report_csv(self, job_id: str) -> str:
        return self._req("GET", f"/jobs/{job_id}/validation-report").text

    def datasets(self) -> list[dict]:
        return self._req("GET", "/datasets").json()["datasets"]

    def dataset_quality(self, dataset_id: str) -> dict:
        return self._req("GET", f"/datasets/{dataset_id}/quality").json()

    def activity_summary(self, dataset_id: str) -> dict:
        return self._req("GET", f"/datasets/{dataset_id}/activity-summary").json()

    # analysis
    def start_analysis(self, dataset_id: str) -> dict:
        return self._req("POST", "/analysis-runs", json={"dataset_id": dataset_id}).json()

    def analysis_run(self, run_id: str) -> dict:
        return self._req("GET", f"/analysis-runs/{run_id}").json()

    def analysis_runs(self) -> list[dict]:
        return self._req("GET", "/analysis-runs").json()["runs"]

    # alerts
    def alerts(self, dataset_id: str | None = None, band: str | None = None,
               page_size: int = 200) -> list[dict]:
        params = {"page_size": page_size}
        if dataset_id:
            params["dataset_id"] = dataset_id
        if band:
            params["priority_band"] = band
        return self._req("GET", "/alerts", params=params).json()["alerts"]

    def alert(self, alert_id: str) -> dict:
        return self._req("GET", f"/alerts/{alert_id}").json()

    def update_alert_status(self, alert_id: str, status: str) -> dict:
        return self._req("PATCH", f"/alerts/{alert_id}/status",
                         json={"status": status}).json()

    def counterfactual(self, alert_id: str) -> dict:
        return self._req("POST", f"/alerts/{alert_id}/counterfactuals").json()

    def timeline(self, dataset_id: str, employee_id: str, start: str | None,
                 end: str | None) -> list[dict]:
        params = {"dataset_id": dataset_id}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return self._req("GET", f"/employees/{employee_id}/timeline", params=params).json()["events"]

    # models
    def models(self) -> list[dict]:
        return self._req("GET", "/models").json()["models"]

    def score_distribution(self, run_id: str) -> dict:
        return self._req("GET", f"/models/runs/{run_id}/score-distribution").json()

    # cases
    def create_case(self, title: str) -> dict:
        return self._req("POST", "/cases", json={"title": title}).json()

    def cases(self) -> list[dict]:
        return self._req("GET", "/cases").json()["cases"]

    def case(self, case_id: str) -> dict:
        return self._req("GET", f"/cases/{case_id}").json()

    def link_alert(self, case_id: str, alert_id: str) -> dict:
        return self._req("POST", f"/cases/{case_id}/alerts", json={"alert_id": alert_id}).json()

    def add_note(self, case_id: str, text: str) -> dict:
        return self._req("POST", f"/cases/{case_id}/notes", json={"text": text}).json()

    def review_case(self, case_id: str, action: str, comment: str = "") -> dict:
        return self._req("POST", f"/cases/{case_id}/review",
                         json={"action": action, "comment": comment}).json()

    def disposition(self, case_id: str, disposition: str, rationale: str) -> dict:
        return self._req("POST", f"/cases/{case_id}/disposition",
                         json={"disposition": disposition, "rationale": rationale}).json()

    def collect_evidence(self, case_id: str) -> dict:
        return self._req("POST", f"/cases/{case_id}/evidence", json={}).json()

    def create_export(self, case_id: str) -> dict:
        return self._req("POST", f"/cases/{case_id}/exports").json()

    def export(self, export_id: str) -> dict:
        return self._req("GET", f"/exports/{export_id}").json()

    # reports
    def list_exports(self) -> list[dict]:
        return self._req("GET", "/reports/exports").json()["exports"]

    def verify_export(self, export_id: str) -> dict:
        return self._req("GET", f"/reports/exports/{export_id}/verify").json()

    def download(self, path: str) -> bytes:
        if path.startswith("/api/v1"):      # tolerate paths that already carry the prefix
            path = path[len("/api/v1"):]
        return self._req("GET", path).content

    # helpers
    def poll_job(self, job_id: str, timeout: int = 120) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            j = self.job(job_id)
            if j["status"] in ("completed", "completed_with_errors", "failed"):
                return j
            time.sleep(1)
        raise ApiError("timed out waiting for job")

    def poll_run(self, run_id: str, timeout: int = 900) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = self.analysis_run(run_id)
            if r["status"] in ("completed", "failed"):
                return r
            time.sleep(2)
        raise ApiError("timed out waiting for analysis run")

    def poll_export(self, export_id: str, timeout: int = 300) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            e = self.export(export_id)
            if e["status"] in ("verified", "failed"):
                return e
            time.sleep(1.5)
        raise ApiError("timed out waiting for export")