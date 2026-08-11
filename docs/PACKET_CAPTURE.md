# Packet-capture runbook

## Safety

Capture passively during an approved window. Do not inject, replay, alter, or acknowledge fiscal traffic. PCAPs can contain personal, fiscal, and commercial data; store them encrypted with restricted access and never commit them.

The examples use RFC 5737 placeholders `192.0.2.231` and `192.0.2.251`; substitute the approved private site endpoints before capture. The subnet prefix and this workstation's attachment are unconfirmed. A switched/Wi-Fi client normally cannot see another host's unicast exchange. Capture on the management host, proxy host, approved switch mirror, or other legitimate observation point.

## Direct baseline

With the management software still targeting the physical endpoint (shown here as `192.0.2.251:23`):

```bash
sudo tcpdump -i <interface> -s 0 -nn -w rch-direct.pcap \
  'host 192.0.2.251'
```

The first filter is deliberately protocol-neutral. RCH documents Ethernet and port 23 for Print! F, but the accessible sources do not establish TCP or UDP. Record synchronized UTC time, device model/firmware, software action, physical outcome, paper state, and anonymization plan. Capture each of the three photo-observed cases at least three times. Record naturally occurring error behavior; induce an error only through a dealer-approved, non-destructive workflow.

## Proxy baseline

After the proxy and management target change are approved:

```bash
sudo tcpdump -i <interface> -s 0 -nn -w rch-proxy.pcap \
  '(host 192.0.2.231 or host 192.0.2.251)'
```

Do not insert the current TCP implementation until NET-2 has actually observed TCP and the change window is approved. If a different transport is observed, stop: the implementation is not compatible with that evidence.

## Read-only analysis

```bash
tcpdump -nn -tttt -XX -r rch-direct.pcap
tshark -r rch-direct.pcap -q -z io,phs
tshark -r rch-direct.pcap -T fields \
  -e frame.time_epoch -e ip.src -e ip.dst -e ip.proto
```

Determine the IP transport from packet headers, not from the service port. Only if TCP is observed, continue with TCP-specific reconstruction:

```bash
tshark -r rch-direct.pcap -q -z conv,tcp
tshark -r rch-direct.pcap -Y 'tcp.len > 0' \
  -T fields -e frame.time_epoch -e ip.src -e tcp.srcport \
  -e ip.dst -e tcp.dstport -e tcp.len -e tcp.payload
```

Determine from bytes, never from port number:

- IP transport and endpoints before applying any TCP/UDP hypothesis;
- connection reuse/concurrency;
- server-first traffic;
- if TCP was observed, candidate Telnet IAC `ff fb/fc/fd/fe` sequences (presence is evidence to investigate, not proof by itself);
- request/response ordering;
- segmentation versus application boundaries;
- framing fields, escaping, lengths/checksums/sequence numbers;
- charset/XML declaration/root/namespace/envelope;
- final success/error evidence;
- document/job boundaries;
- FIN/RST/retries/timeouts;
- naturally occurring paper-out/error/recovery sequences, or dealer-approved non-destructive test sequences only.

## Comparison

If and only if TCP was observed, compare reconstructed application byte streams, not IP/TCP headers or packet sizes:

```bash
tshark -r rch-direct.pcap -q -z follow,tcp,raw,<stream>
tshark -r rch-proxy.pcap  -q -z follow,tcp,raw,<stream>
```

The acceptance target is equality between management-to-proxy and proxy-to-printer streams, and between printer-to-proxy and proxy-to-management streams, after reconstruction and with direction/capture points verified. Packet boundaries, sequence numbers, source address, and timing will differ. This comparison, together with management-system completion and physical-output checks, is what can satisfy C-4; fixture tests and local writer drains cannot.

## Promotion rule

Only repeatable `OBSERVED` results or authenticated `DOCUMENTED` rules may enable critical framing, status, error, or job logic. Preserve contradictory evidence and firmware scope. Inferred keyword rendering must never feed the forwarding path.
