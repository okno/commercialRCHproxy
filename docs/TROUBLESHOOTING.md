# Troubleshooting

## IP not assigned

Symptom:

```text
Cannot bind 192.0.2.231:23. The IP address is not assigned to this host.
```

Check `ip -4 address`, the configured interface/prefix, and duplicate-address policy. The proxy never adds the IP automatically.

## Permission denied on port 23

Confirm the systemd unit has only `CAP_NET_BIND_SERVICE`, is started through systemd, and has not been replaced by an unrestricted manual root process.

```bash
systemctl cat commercialrchproxy
systemctl show commercialrchproxy -p AmbientCapabilities -p CapabilityBoundingSet
```

## Listener already used

```bash
sudo ss -ltnp 'sport = :23'
```

Do not kill an unknown process until ownership and business impact are established.

## Printer unreachable

Check addressing, VLAN/firewall, cabling/Wi-Fi, switch state, and the physical device using approved infrastructure telemetry and passive capture. The health/config checks do not connect to the fiscal port, and no live connect probe is provided. Do not use `telnet`, `nc`, an empty connection, or guessed commands during business operation: the safety of even a payload-free session is `UNCONFIRMED`.

## Management timeout or missing response tail

Capture direct and proxy baselines. Compare request/response timing, FIN/RST, retransmission, and late response delay. Adjust `RESPONSE_TIMEOUT_SEC` only from observed evidence. Do not synthesize a reply.

## Too many/few job files

Idle boundaries are fallback behavior. Inspect the directional technical transcript and PCAP. Never treat archive segmentation as proof of the physical printer's document boundary.

## Empty PULITO/PDF

This is expected in production 0.1.0: no authoritative RCH field mapping exists, so PULITO/PDF human content is intentionally empty/unavailable. Check `xml_candidate_found`, `xml_well_formed_generic`, `xml7_confirmed` (which must remain false), `parser_status`, `candidate_printed_class`, `candidate_observed_variant`, and `render_errors`. Photo-derived fixtures test layout only. Do not add guessed fiscal fields merely to make the output attractive.

## Disk/archive failure

Forwarding may continue while sidecars fail. Treat missing/partial evidence seriously, inspect `capture_segment_archive_failed` logs, free protected disk space, and verify filesystem ownership/mount health. Do not replay an unknown-state job.

## Logs

```bash
journalctl -u commercialrchproxy --since today
tail -f /var/log/commercialrchproxy/commercialrchproxy.jsonl
```

Payload is absent by default.
