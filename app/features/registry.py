"""Feature registry (plan §7.5): stable names, units, counterfactual mutability."""
from __future__ import annotations

FEATURE_SCHEMA_VERSION = "1.0"


def _f(name, group, unit, desc, mutable=False, vmin=0.0, vmax=None):
    return {"name": name, "group": group, "unit": unit, "description": desc,
            "mutable": mutable, "vmin": vmin, "vmax": vmax}


FEATURES = [
    # authentication
    _f("login_attempts", "authentication", "count", "Login attempts in window", mutable=True),
    _f("failed_login_count", "authentication", "count", "Failed logins in window", mutable=True),
    _f("distinct_hosts", "authentication", "count", "Distinct hosts used", mutable=True),
    _f("off_hours_login_ratio", "authentication", "ratio", "Share of logins outside schedule"),
    _f("session_count", "authentication", "count", "Distinct sessions", mutable=True),
    # file activity
    _f("files_read", "file_activity", "count", "File read events", mutable=True),
    _f("files_written", "file_activity", "count", "File write events", mutable=True),
    _f("distinct_file_ids", "file_activity", "count", "Distinct files touched", mutable=True),
    _f("sensitive_tag_reads", "file_activity", "count", "Reads of synthetic-confidential files", mutable=True),
    _f("bytes_read", "file_activity", "bytes", "Bytes read", mutable=True),
    _f("bytes_written", "file_activity", "bytes", "Bytes written", mutable=True),
    # removable media
    _f("usb_mount_count", "removable_media", "count", "USB mount events", mutable=True),
    _f("usb_write_bytes", "removable_media", "bytes", "Bytes written to removable media", mutable=True),
    _f("usb_read_bytes", "removable_media", "bytes", "Bytes read from removable media", mutable=True),
    _f("distinct_usb_devices", "removable_media", "count", "Distinct USB devices", mutable=True),
    _f("first_seen_device_flag", "removable_media", "flag", "Device never seen in baseline period"),
    # process behaviour
    _f("process_count", "process", "count", "Process creation events", mutable=True),
    _f("rare_process_ratio", "process", "ratio", "Share of processes unseen in baseline"),
    _f("archive_tool_count", "process", "count", "Archive/copy utility launches", mutable=True),
    # print
    _f("print_jobs", "print", "count", "Print jobs", mutable=True),
    _f("pages_printed", "print", "pages", "Pages printed", mutable=True),
    _f("off_hours_print_jobs", "print", "count", "Off-hours print jobs", mutable=True),
    # email metadata
    _f("messages_sent", "email_metadata", "count", "Email messages sent", mutable=True),
    _f("external_recipient_count", "email_metadata", "count", "External recipients (total)", mutable=True),
    _f("attachment_count", "email_metadata", "count", "Attachments sent", mutable=True),
    _f("attachment_bytes", "email_metadata", "bytes", "Attachment bytes sent", mutable=True),
    # sequence / cross-source
    _f("file_to_usb_lag_sec", "sequence", "seconds", "Min lag between file read and USB write"),
    _f("file_usb_sequence_flag", "sequence", "flag", "File read shortly followed by USB write"),
    _f("off_hours_activity_ratio", "sequence", "ratio", "Share of all events outside schedule"),
]

FEATURE_NAMES = [f["name"] for f in FEATURES]
FEATURE_BY_NAME = {f["name"]: f for f in FEATURES}

EVIDENCE_FAMILY_MAP = {
    "login_attempts": "login", "failed_login_count": "login", "off_hours_login_ratio": "login",
    "session_count": "login", "distinct_hosts": "login",
    "files_read": "file_access", "files_written": "file_access", "distinct_file_ids": "file_access",
    "sensitive_tag_reads": "file_access", "bytes_read": "file_access", "bytes_written": "file_access",
    "usb_mount_count": "usb", "usb_write_bytes": "usb", "usb_read_bytes": "usb",
    "distinct_usb_devices": "usb", "first_seen_device_flag": "usb",
    "process_count": "process", "rare_process_ratio": "process", "archive_tool_count": "process",
    "print_jobs": "print", "pages_printed": "print", "off_hours_print_jobs": "print",
    "messages_sent": "email_metadata", "external_recipient_count": "email_metadata",
    "attachment_count": "email_metadata", "attachment_bytes": "email_metadata",
    "file_to_usb_lag_sec": ["file_access", "usb"], "file_usb_sequence_flag": ["file_access", "usb"],
    "off_hours_activity_ratio": None,
}