"""Deterministic synthetic telemetry generator (plan §6.5, Appendix B).

Generates benign baseline activity for all six telemetry families plus labelled
suspicious scenario sequences injected into the final (test) day.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np

SENSITIVE = "synthetic-confidential"
COMMON_PROCESSES = ["browser", "office_suite", "email_client", "terminal", "ide", "vpn_client"]
ARCHIVE_TOOLS = {"archive_tool", "disk_imager"}
ADMIN_TOOLS = {"admin_util"}

ROLE_PROFILES = {
    "engineering": {"count": 8, "start": 9, "end": 18, "files": 40, "email": 8},
    "finance":     {"count": 6, "start": 8, "end": 16, "files": 30, "email": 10},
    "hr":          {"count": 4, "start": 8, "end": 17, "files": 15, "email": 12},
    "operations":  {"count": 4, "start": 10, "end": 19, "files": 22, "email": 6},
}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class GenConfig:
    seed: int = 42
    days: int = 7
    base_date: date = date(2026, 11, 2)   # Monday
    hosts: int = 5
    employees_per_role: dict | None = None


@dataclass
class Generator:
    cfg: GenConfig
    rng: np.random.Generator = field(init=False)
    counters: dict = field(default_factory=dict)
    employees: list = field(default_factory=list)
    host_ids: list = field(default_factory=list)
    events: dict = field(default_factory=lambda: {
        "login": [], "file_access": [], "usb": [], "process": [], "print": [], "email_metadata": [],
    })
    scenarios: list = field(default_factory=list)

    def __post_init__(self):
        self.rng = np.random.default_rng(self.cfg.seed)
        self.host_ids = [f"HOST-{i:02d}" for i in range(1, self.cfg.hosts + 1)]
        self._build_employees()

    # ------------------------------------------------------------------ utils
    def _next_id(self, family: str) -> str:
        n = self.counters.get(family, 0) + 1
        self.counters[family] = n
        prefix = {"login": "LOG", "file_access": "FIL", "usb": "USB",
                  "process": "PRC", "print": "PRT", "email_metadata": "EML"}[family]
        return f"{prefix}-{n:06d}"

    def _add(self, family: str, ts: datetime, emp: dict, host: str, payload: dict,
             session_id: str | None = None, collect: list | None = None) -> str:
        event_id = self._next_id(family)
        row = {
            "event_id": event_id,
            "timestamp": _iso(ts),
            "employee_id": emp["employee_id"],
            "host_id": host,
        }
        if session_id:
            row["session_id"] = session_id
        if family == "process":
            row["process_guid"] = payload.get("process_guid")
            row["parent_guid"] = payload.get("parent_guid")
        row.update(payload)
        self.events[family].append(row)
        if collect is not None:
            collect.append(event_id)
        return event_id

    def _build_employees(self):
        idx = 1
        per_role = self.cfg.employees_per_role or {}
        for role, prof in ROLE_PROFILES.items():
            count = int(per_role.get(role, prof["count"]))
            for _ in range(count):
                jitter_start = int(self.rng.choice([0, 30]))
                emp = {
                    "employee_id": f"EMP-{idx:03d}",
                    "role": role,
                    "work_start": prof["start"] * 60 + jitter_start,   # minutes of day
                    "work_end": prof["end"] * 60,
                    "primary_host": self.host_ids[idx % len(self.host_ids)],
                    "known_devices": [f"USB-K{idx}A", f"USB-K{idx}B"],
                    "file_pool": [f"F-{(idx * 100 + k):04d}" for k in range(40)],
                }
                self.employees.append(emp)
                idx += 1

    def _work_dt(self, day: date, minutes: float) -> datetime:
        hh, mm = divmod(int(minutes), 60)
        return datetime.combine(day, time(0, 0), tzinfo=timezone.utc) + timedelta(hours=hh, minutes=mm)

    # ------------------------------------------------------------ benign activity
    def generate_benign(self):
        for di in range(self.cfg.days):
            day = self.cfg.base_date + timedelta(days=di)
            weekend = day.weekday() >= 5
            for emp in self.employees:
                if weekend and self.rng.random() > 0.15:
                    continue
                scale = 0.4 if weekend else 1.0
                self._benign_employee_day(emp, day, scale)

    def _benign_employee_day(self, emp: dict, day: date, scale: float):
        rng = self.rng
        start_min = emp["work_start"] + float(rng.uniform(0, 25))
        session_id = f"S-{emp['employee_id']}-{day.isoformat()}"
        host = emp["primary_host"]
        ts_login = self._work_dt(day, start_min)

        self._add("login", ts_login, emp, host, {
            "result": "success", "auth_method": "password", "source_ip_class": "known",
        }, session_id)

        if rng.random() < 0.06:
            self._add("login", ts_login - timedelta(minutes=float(rng.uniform(2, 10))), emp, host, {
                "result": "failure", "auth_method": "password", "source_ip_class": "known",
            })

        # processes spawned at login
        init_guid = f"P-{session_id}-init"
        self._add("process", ts_login + timedelta(seconds=5), emp, host, {
            "process_guid": init_guid, "parent_guid": None,
            "image_name": "session_manager", "command_category": "system", "signer_status": "signed",
        }, session_id)
        images = ["browser", "office_suite", "email_client"]
        if emp["role"] == "engineering":
            images.append("ide")
        if rng.random() < 0.4:
            images.append("terminal")
        for i, img in enumerate(images):
            self._add("process", ts_login + timedelta(seconds=10 + i * 7), emp, host, {
                "process_guid": f"P-{session_id}-{i}", "parent_guid": init_guid,
                "image_name": img, "command_category": "user", "signer_status": "signed",
            }, session_id)

        # file access
        n_files = int(rng.poisson(ROLE_PROFILES[emp["role"]]["files"] * scale))
        sensitive_p = 0.08 if emp["role"] in ("finance", "hr") else 0.04
        for _ in range(n_files):
            ts = ts_login + timedelta(minutes=float(rng.uniform(5, emp["work_end"] - emp["work_start"])))
            action = "read" if rng.random() < 0.7 else "write"
            self._add("file_access", ts, emp, host, {
                "file_id": str(rng.choice(emp["file_pool"])),
                "action": action,
                "bytes": int(min(rng.lognormal(8, 2), 50_000_000)),
                "sensitivity": SENSITIVE if rng.random() < sensitive_p else "internal",
            }, session_id)

        # rare benign USB usage
        if rng.random() < 0.05:
            dev = str(rng.choice(emp["known_devices"]))
            ts = ts_login + timedelta(minutes=float(rng.uniform(60, 240)))
            self._add("usb", ts, emp, host, {"device_id": dev, "action": "mount",
                                             "bytes_transferred": 0, "mount_label": "removable"}, session_id)
            self._add("usb", ts + timedelta(seconds=20), emp, host, {
                "device_id": dev, "action": str(rng.choice(["read", "write"])),
                "bytes_transferred": int(rng.lognormal(6, 1.5)), "mount_label": "removable"}, session_id)

        # printing
        if rng.random() < 0.12:
            ts = ts_login + timedelta(minutes=float(rng.uniform(30, 300)))
            self._add("print", ts, emp, host, {
                "print_job_id": f"PR-{day.isoformat()}-{emp['employee_id']}",
                "pages": int(rng.integers(1, 8)),
                "printer_id": f"PRINT-{int(rng.integers(1, 3)):02d}",
                "document_label": "synthetic-report",
            }, session_id)

        # email metadata
        n_mail = int(rng.poisson(ROLE_PROFILES[emp["role"]]["email"] * scale))
        for _ in range(n_mail):
            ts = ts_login + timedelta(minutes=float(rng.uniform(10, emp["work_end"] - emp["work_start"])))
            recipients = int(rng.integers(1, 5))
            external = int(rng.binomial(recipients, 0.2))
            has_att = rng.random() < 0.35
            self._add("email_metadata", ts, emp, host, {
                "message_id": f"M-{self.counters.get('email_metadata', 0) + 1:06d}",
                "recipient_count": recipients,
                "external_recipient_count": external,
                "attachment_count": 1 if has_att else 0,
                "attachment_bytes": int(rng.lognormal(11, 1.5)) if has_att else 0,
            }, session_id)

    # ------------------------------------------------------------- scenarios (test day)
    def inject_scenarios(self):
        test_day = self.cfg.base_date + timedelta(days=self.cfg.days - 1)
        by_role = {}
        for e in self.employees:
            by_role.setdefault(e["role"], []).append(e)

        self._s1_usb_exfiltration(by_role["engineering"][0], test_day)
        self._s2_privilege_misuse(by_role["operations"][0], test_day)
        self._s3_bulk_print(by_role["finance"][0], test_day)
        self._s4_email_anomaly(by_role["hr"][0], test_day)
        if len(by_role["engineering"]) > 1:
            self._s5_credential_misuse(by_role["engineering"][1], test_day)
        if len(by_role["engineering"]) > 2:
            self._benign_confounder(by_role["engineering"][2], test_day)

    def _scenario_meta(self, sid, emp, start, end, event_ids, severity, desc):
        self.scenarios.append({
            "scenario_id": sid, "employee_id": emp["employee_id"], "host_id": emp["primary_host"],
            "start": _iso(start), "end": _iso(end), "severity": severity,
            "event_ids": event_ids, "description": desc,
        })

    def _s1_usb_exfiltration(self, emp, day):
        ev: list = []
        t0 = self._work_dt(day, 22 * 60 + 40)
        sid = f"S-{emp['employee_id']}-{day.isoformat()}-x"
        self._add("login", t0, emp, emp["primary_host"], {
            "result": "success", "auth_method": "password", "source_ip_class": "known"}, sid, ev)
        for i in range(25):
            self._add("file_access", t0 + timedelta(minutes=1 + i * 0.6), emp, emp["primary_host"], {
                "file_id": f"F-X{i:03d}", "action": "read", "bytes": 40_000_000,
                "sensitivity": SENSITIVE}, sid, ev)
        self._add("process", t0 + timedelta(minutes=17), emp, emp["primary_host"], {
            "process_guid": f"P-{sid}-arch", "parent_guid": f"P-{sid}-term",
            "image_name": "archive_tool", "command_category": "user",
            "signer_status": "signed"}, sid, ev)
        dev = "USB-NEW-S1"
        self._add("usb", t0 + timedelta(minutes=19), emp, emp["primary_host"], {
            "device_id": dev, "action": "mount", "bytes_transferred": 0,
            "mount_label": "removable"}, sid, ev)
        for i in range(6):
            self._add("usb", t0 + timedelta(minutes=20 + i), emp, emp["primary_host"], {
                "device_id": dev, "action": "write", "bytes_transferred": 150_000_000,
                "mount_label": "removable"}, sid, ev)
        self._scenario_meta("S1-usb-exfil", emp, t0, t0 + timedelta(minutes=30), ev, "high",
                            "Off-hours login, sensitive file reads, archive tool, first-seen USB write.")

    def _s2_privilege_misuse(self, emp, day):
        ev: list = []
        t0 = self._work_dt(day, 14 * 60)
        new_host = self.host_ids[(self.host_ids.index(emp["primary_host"]) + 1) % len(self.host_ids)]
        sid = f"S-{emp['employee_id']}-{day.isoformat()}-p"
        self._add("login", t0, emp, new_host, {
            "result": "success", "auth_method": "password", "source_ip_class": "known"}, sid, ev)
        self._add("process", t0 + timedelta(minutes=2), emp, new_host, {
            "process_guid": f"P-{sid}-adm", "parent_guid": f"P-{sid}-brow",
            "image_name": "admin_util", "command_category": "admin",
            "signer_status": "signed"}, sid, ev)
        for i in range(15):
            self._add("file_access", t0 + timedelta(minutes=4 + i * 0.5), emp, new_host, {
                "file_id": f"F-SEC{i:03d}", "action": "read", "bytes": 8_000_000,
                "sensitivity": SENSITIVE}, sid, ev)
        self._scenario_meta("S2-privilege-misuse", emp, t0, t0 + timedelta(minutes=15), ev, "high",
                            "Rare admin utility with unusual parent on a new host, followed by sensitive reads.")

    def _s3_bulk_print(self, emp, day):
        ev: list = []
        t0 = self._work_dt(day, 20 * 60 + 30)
        sid = f"S-{emp['employee_id']}-{day.isoformat()}-b"
        self._add("login", t0, emp, emp["primary_host"], {
            "result": "success", "auth_method": "password", "source_ip_class": "known"}, sid, ev)
        for i in range(10):
            self._add("file_access", t0 + timedelta(minutes=i * 0.5), emp, emp["primary_host"], {
                "file_id": f"F-DOC{i:03d}", "action": "read", "bytes": 2_000_000,
                "sensitivity": SENSITIVE}, sid, ev)
        for j, pages in enumerate([30, 25, 40]):
            self._add("print", t0 + timedelta(minutes=8 + j * 4), emp, emp["primary_host"], {
                "print_job_id": f"PR-X{j}", "pages": pages, "printer_id": "PRINT-01",
                "document_label": "synthetic-report"}, sid, ev)
        self._scenario_meta("S3-bulk-print", emp, t0, t0 + timedelta(minutes=22), ev, "medium",
                            "Off-hours rapid file reads followed by unusually large print jobs.")

    def _s4_email_anomaly(self, emp, day):
        ev: list = []
        t0 = self._work_dt(day, 11 * 60)
        sid = f"S-{emp['employee_id']}-{day.isoformat()}-e"
        for i in range(14):
            self._add("email_metadata", t0 + timedelta(minutes=i * 2), emp, emp["primary_host"], {
                "message_id": f"M-X{i:03d}", "recipient_count": 4,
                "external_recipient_count": 3 if i < 10 else 1,
                "attachment_count": 1, "attachment_bytes": 3_000_000}, sid, ev)
        self._scenario_meta("S4-email-anomaly", emp, t0, t0 + timedelta(minutes=30), ev, "medium",
                            "Burst of external-recipient messages with large attachments.")

    def _s5_credential_misuse(self, emp, day):
        ev: list = []
        t0 = self._work_dt(day, 3 * 60 + 15)
        new_host = self.host_ids[-1]
        for i in range(8):
            self._add("login", t0 + timedelta(seconds=i * 25), emp, new_host, {
                "result": "failure", "auth_method": "password", "source_ip_class": "unknown"}, None, ev)
        sid = f"S-{emp['employee_id']}-{day.isoformat()}-c"
        self._add("login", t0 + timedelta(minutes=4), emp, new_host, {
            "result": "success", "auth_method": "password", "source_ip_class": "unknown"}, sid, ev)
        for i in range(5):
            self._add("file_access", t0 + timedelta(minutes=6 + i), emp, new_host, {
                "file_id": f"F-C{i:03d}", "action": "read", "bytes": 1_500_000,
                "sensitivity": SENSITIVE}, sid, ev)
        self._scenario_meta("S5-credential-misuse", emp, t0, t0 + timedelta(minutes=12), ev, "high",
                            "Failed-login burst followed by success from a new host at 03:00.")

    def _benign_confounder(self, emp, day):
        """High-but-legitimate volume during work hours: should NOT be a top alert."""
        t0 = self._work_dt(day, emp["work_start"] + 30)
        sid = f"S-{emp['employee_id']}-{day.isoformat()}-conf"
        self._add("login", t0, emp, emp["primary_host"], {
            "result": "success", "auth_method": "password", "source_ip_class": "known"}, sid)
        for i in range(90):
            self._add("file_access", t0 + timedelta(minutes=i * 0.5), emp, emp["primary_host"], {
                "file_id": str(self.rng.choice(emp["file_pool"])), "action": "read",
                "bytes": 500_000, "sensitivity": "internal"}, sid)

    # ------------------------------------------------------------------- output
    def run(self) -> dict:
        self.generate_benign()
        self.inject_scenarios()
        days = [self.cfg.base_date + timedelta(days=i) for i in range(self.cfg.days)]
        train_end = datetime.combine(days[-2], time(0, 0), tzinfo=timezone.utc)
        test_start = datetime.combine(days[-1], time(0, 0), tzinfo=timezone.utc)
        end = datetime.combine(days[-1] + timedelta(days=1), time(0, 0), tzinfo=timezone.utc)
        manifest = {
            "dataset_name": f"synthetic-{self.cfg.seed}-{self.cfg.days}d",
            "seed": self.cfg.seed,
            "generated_at": _iso(utcnow_local()),
            "date_range": {"start": days[0].isoformat(), "end": days[-1].isoformat()},
            "splits": {
                "train": {"start": days[0].isoformat(), "end": (days[-2]).isoformat()},
                "calibration": {"start": days[-2].isoformat(), "end": days[-1].isoformat()},
                "test": {"start": days[-1].isoformat(), "end": (days[-1] + timedelta(days=1)).isoformat()},
            },
            "employees": [{k: e[k] for k in
                           ("employee_id", "role", "work_start", "work_end", "primary_host")}
                          for e in self.employees],
            "hosts": self.host_ids,
            "scenarios": self.scenarios,
        }
        return {"events": self.events, "manifest": manifest}


def utcnow_local() -> datetime:
    return datetime.now(timezone.utc)


FIELDNAMES = {
    "login": ["event_id", "timestamp", "employee_id", "host_id", "session_id",
              "result", "auth_method", "source_ip_class"],
    "file_access": ["event_id", "timestamp", "employee_id", "host_id", "session_id",
                    "file_id", "action", "bytes", "sensitivity"],
    "usb": ["event_id", "timestamp", "employee_id", "host_id", "session_id",
            "device_id", "action", "bytes_transferred", "mount_label"],
    "process": ["event_id", "timestamp", "employee_id", "host_id", "session_id",
                "process_guid", "parent_guid", "image_name", "command_category", "signer_status"],
    "print": ["event_id", "timestamp", "employee_id", "host_id", "session_id",
              "print_job_id", "pages", "printer_id", "document_label"],
    "email_metadata": ["event_id", "timestamp", "employee_id", "host_id", "session_id",
                       "message_id", "recipient_count", "external_recipient_count",
                       "attachment_count", "attachment_bytes"],
}

FILENAMES = {
    "login": "logins.csv", "file_access": "file_access.csv", "usb": "usb.csv",
    "process": "processes.csv", "print": "prints.csv", "email_metadata": "email_metadata.csv",
}


def write_dataset(out_dir: Path, result: dict) -> dict:
    """Write per-family CSVs + manifest.json. Returns {family_or_manifest: path}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for family, rows in result["events"].items():
        path = out_dir / FILENAMES[family]
        with open(path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDNAMES[family], extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in FIELDNAMES[family]})
        paths[family] = path
    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "w") as fh:
        json.dump(result["manifest"], fh, indent=2)
    paths["manifest"] = manifest_path
    return paths