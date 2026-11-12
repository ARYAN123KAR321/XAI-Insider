# Data Dictionary

## Canonical event envelope (Appendix A)
event_id, dataset_id, employee_id (pseudonym), host_id, timestamp_utc (ISO-8601 UTC),
event_type ∈ {login, file_access, usb, process, print, email_metadata}, session_id?,
process_guid?/parent_process_guid? (process family), source_file_id, source_record_id,
raw_record_hash (SHA-256), ingested_at_utc, metadata JSON (family payload).

Prohibited anywhere: email bodies/subjects/addresses, file contents, command lines,
keystrokes, direct personal identifiers (§13.1).

## Family payloads (required fields)
- login: result ∈ {success, failure}, auth_method
- file_access: file_id, action ∈ {read, write, delete, rename}, bytes ≥ 0, sensitivity
- usb: device_id, action ∈ {mount, read, write, eject}, bytes_transferred ≥ 0
- process: process_guid, image_name (optional: parent_guid, command_category, signer_status)
- print: print_job_id, pages ≥ 0 (optional: printer_id, document_label)
- email_metadata: message_id, recipient_count ≥ 0 (optional: external_recipient_count,
  attachment_count, attachment_bytes)

## Feature registry (schema v1.0) — 29 features over 60-min windows / 15-min stride
| Group | Features |
|---|---|
| authentication | login_attempts, failed_login_count, distinct_hosts, off_hours_login_ratio, session_count |
| file_activity | files_read, files_written, distinct_file_ids, sensitive_tag_reads, bytes_read, bytes_written |
| removable_media | usb_mount_count, usb_write_bytes, usb_read_bytes, distinct_usb_devices, first_seen_device_flag |
| process | process_count, rare_process_ratio, archive_tool_count |
| print | print_jobs, pages_printed, off_hours_print_jobs |
| email_metadata | messages_sent, external_recipient_count, attachment_count, attachment_bytes |
| sequence | file_to_usb_lag_sec, file_usb_sequence_flag, off_hours_activity_ratio |

Mutable-in-counterfactual: counts and bytes only. Immutable: identities, timestamps,
hashes, ratios/flags/lags (see `app/features/registry.py`).