# Wazuh integration

The application writes one JSON object per line to:

```text
/var/log/commercialrchproxy/commercialrchproxy.jsonl
```

Current events include:

- `service_start`, `service_stop`, `metrics`;
- `session_start`, `device_session_queued`, `stream_local_write_drain`, `session_streams_complete`, `session_end`;
- `printer_unreachable`, `session_error`, `session_task_error`;
- `capture_error`, `capture_segment_archived`, `capture_segment_archive_failed`;
- future `integrity_error`, `disk_low`, and verified `rch_error` events.

The `jobs_completed`/`jobs_failed` metric names are retained as the operational API requested for monitoring. In 0.1.0 they count fallback-bounded capture segments archived or failed, not RCH-confirmed fiscal jobs.

Fields are sanitized to one line and bounded. Payload is not logged unless `DEBUG=true`, `DEBUG_HEXDUMP=true`, and `LOG_PAYLOAD=true`.

Configure the site's Wazuh agent to monitor the file as JSON, then write local rules for endpoint changes, printer failures, job failures, incomplete RAW, disk warnings, and unexpected debug payload logging. This project intentionally does not modify Wazuh configuration.

Avoid forwarding receipt content to a central SIEM. Metadata can itself be sensitive; apply access and retention controls.
