"""Employee-session rolling windows and feature computation (plan §7)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.features.registry import FEATURE_NAMES
from app.util.ids import new_id

SEQUENCE_LAG_LIMIT_SEC = 3600.0


@dataclass
class WindowResult:
    window_id: str
    employee_id: str
    start: datetime
    end: datetime
    features: dict
    event_ids: list


def _events_to_frame(events: list[dict]) -> pd.DataFrame:
    """events: rows with keys event_id, employee_id, host_id, event_type, ts, metadata, session_id."""
    rows = []
    for e in events:
        m = e["metadata"]
        rows.append({
            "event_id": e["event_id"],
            "internal_id": e["id"],
            "employee_id": e["employee_id"],
            "host_id": e["host_id"],
            "event_type": e["event_type"],
            "ts": e["ts"],
            "session_id": e.get("session_id"),
            "result": m.get("result"),
            "action": m.get("action"),
            "sensitivity": m.get("sensitivity"),
            "file_id": m.get("file_id"),
            "bytes": float(m.get("bytes") or 0),
            "device_id": m.get("device_id"),
            "bytes_transferred": float(m.get("bytes_transferred") or 0),
            "image_name": m.get("image_name"),
            "pages": float(m.get("pages") or 0),
            "recipient_count": float(m.get("recipient_count") or 0),
            "external_recipient_count": float(m.get("external_recipient_count") or 0),
            "attachment_count": float(m.get("attachment_count") or 0),
            "attachment_bytes": float(m.get("attachment_bytes") or 0),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("ts").reset_index(drop=True)
    return df


def _off_minutes(emp_meta: dict | None) -> tuple[int, int]:
    if emp_meta:
        return int(emp_meta.get("work_start", 9 * 60)), int(emp_meta.get("work_end", 17 * 60))
    return 9 * 60, 17 * 60


def _is_off_hour(ts: pd.Series, start_min: int, end_min: int) -> pd.Series:
    minutes = ts.dt.hour * 60 + ts.dt.minute
    return (minutes < start_min) | (minutes >= end_min)


def build_windows(events: list[dict], employee_meta: dict,
                  known_devices: dict, known_processes: dict,
                  window_minutes: int = 60, stride_minutes: int = 15) -> list[WindowResult]:
    """Build rolling windows per employee-day and compute the feature vector."""
    df = _events_to_frame(events)
    if df.empty:
        return []

    results: list[WindowResult] = []
    w = timedelta(minutes=window_minutes)
    stride = timedelta(minutes=stride_minutes)

    for emp_id, edf in df.groupby("employee_id"):
        meta = employee_meta.get(emp_id)
        start_min, end_min = _off_minutes(meta)
        edf = edf.copy()
        edf["off_hour"] = _is_off_hour(edf["ts"], start_min, end_min)
        emp_devices = set(known_devices.get(emp_id, []))
        emp_procs = set(known_processes.get(emp_id, []))

        for day, ddf in edf.groupby(edf["ts"].dt.floor("D")):
            day_start = ddf["ts"].min().floor("h")
            day_end = ddf["ts"].max().ceil("h")
            t = day_start
            while t + w <= day_end + stride:
                win_end = t + w
                mask = (ddf["ts"] >= t) & (ddf["ts"] < win_end)
                wdf = ddf[mask]
                if len(wdf) > 0:
                    feats = _window_features(wdf, emp_devices, emp_procs, window_minutes)
                    results.append(WindowResult(
                        window_id=new_id("win"), employee_id=emp_id, start=t, end=win_end,
                        features=feats, event_ids=wdf["internal_id"].tolist()))
                t += stride
    return results


def _window_features(wdf: pd.DataFrame, emp_devices: set, emp_procs: set,
                     window_minutes: int) -> dict:
    f = dict.fromkeys(FEATURE_NAMES, 0.0)

    login = wdf[wdf["event_type"] == "login"]
    f["login_attempts"] = len(login)
    f["failed_login_count"] = int((login["result"] == "failure").sum())
    f["distinct_hosts"] = login["host_id"].nunique()
    f["off_hours_login_ratio"] = float(login["off_hour"].mean()) if len(login) else 0.0
    f["session_count"] = login["session_id"].nunique()

    files = wdf[wdf["event_type"] == "file_access"]
    f["files_read"] = int((files["action"] == "read").sum())
    f["files_written"] = int((files["action"] == "write").sum())
    f["distinct_file_ids"] = files["file_id"].nunique()
    sens = files[(files["action"] == "read") & (files["sensitivity"] == "synthetic-confidential")]
    f["sensitive_tag_reads"] = len(sens)
    f["bytes_read"] = float(files.loc[files["action"] == "read", "bytes"].sum())
    f["bytes_written"] = float(files.loc[files["action"] == "write", "bytes"].sum())

    usb = wdf[wdf["event_type"] == "usb"]
    f["usb_mount_count"] = int((usb["action"] == "mount").sum())
    f["usb_write_bytes"] = float(usb.loc[usb["action"] == "write", "bytes_transferred"].sum())
    f["usb_read_bytes"] = float(usb.loc[usb["action"] == "read", "bytes_transferred"].sum())
    f["distinct_usb_devices"] = usb["device_id"].nunique()
    f["first_seen_device_flag"] = 1.0 if (len(usb) and
                                          not set(usb["device_id"].dropna()).issubset(emp_devices)) else 0.0

    proc = wdf[wdf["event_type"] == "process"]
    f["process_count"] = len(proc)
    if len(proc):
        rare = ~proc["image_name"].isin(emp_procs) if emp_procs else proc["image_name"].notna()
        f["rare_process_ratio"] = float(rare.mean())
    f["archive_tool_count"] = int(proc["image_name"].isin(["archive_tool", "disk_imager"]).sum())

    prn = wdf[wdf["event_type"] == "print"]
    f["print_jobs"] = len(prn)
    f["pages_printed"] = float(prn["pages"].sum())
    f["off_hours_print_jobs"] = int(prn["off_hour"].sum())

    mail = wdf[wdf["event_type"] == "email_metadata"]
    f["messages_sent"] = len(mail)
    f["external_recipient_count"] = float(mail["external_recipient_count"].sum())
    f["attachment_count"] = float(mail["attachment_count"].sum())
    f["attachment_bytes"] = float(mail["attachment_bytes"].sum())

    # file -> USB sequence
    reads = files[files["action"] == "read"].sort_values("ts")
    writes = usb[usb["action"] == "write"].sort_values("ts")
    lag = float(window_minutes * 60)
    seq = 0.0
    if len(reads) and len(writes):
        for _, wrow in writes.iterrows():
            prior = reads[reads["ts"] <= wrow["ts"]]
            if len(prior):
                this_lag = (wrow["ts"] - prior["ts"].max()).total_seconds()
                lag = min(lag, this_lag)
                if this_lag <= SEQUENCE_LAG_LIMIT_SEC:
                    seq = 1.0
    f["file_to_usb_lag_sec"] = lag
    f["file_usb_sequence_flag"] = seq

    f["off_hours_activity_ratio"] = float(wdf["off_hour"].mean())
    return f