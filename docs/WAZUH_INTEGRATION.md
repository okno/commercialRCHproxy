# Wazuh integration

0.3.0 writes separate JSONL component logs:

```text
/var/log/commercialrchproxy/commercialrchproxy-dumper.jsonl
/var/log/commercialrchproxy/commercialrchproxy-parser.jsonl
```

The same records also go to distinct journald identifiers. Calls enqueue to a
bounded non-blocking in-process logger; a slow sink cannot hold a relay pump,
but prolonged saturation can discard older queued operational records.

Dumper events include service/session lifecycle, queued device access, local
writer-drain progress, connect retries/failure, stream results, connection
limits, capture ready/failure, abandoned partials, and metrics.

Parser events include watcher mode/fallback and per-job result status such as
parsed, already parsed, busy, retry pending, terminal parse failure, or claim
error.

`jobs_completed` means capture directories atomically published to the spool;
it is not a count of fiscal success. `.parsed` counts/alerts should likewise be
described as parser completion, not device acceptance.

Component JSONL files use internal size rotation (10 MiB, seven backups).
Journald/Wazuh rotation and retention are host policy. Fields are one-line and
bounded. Payload is absent by default. It can enter debug
logs only when `DEBUG=true`, `DEBUG_HEXDUMP=true`, and `LOG_PAYLOAD=true`; alert
on that configuration/event in production.

Suggested metadata alerts:

- Dumper/Parser service restart loops or one real unit unexpectedly inactive;
- `printer_unreachable`, `session_error`, or transport-incomplete status;
- `capture_spool_failed` or `capture_partial_recovery_required`;
- ready backlog age/count growth;
- `.processing` older than policy or repeated retry/`.parse_failed`;
- hash/manifest validation errors;
- disk/inode pressure and counter-state access errors;
- unexpected endpoint/config/service-unit changes;
- payload debug logging enabled.

Avoid forwarding receipt content to a central SIEM. Endpoint/code/path/time
metadata can itself be sensitive; apply least access and retention. This
project does not modify the Wazuh agent configuration.
