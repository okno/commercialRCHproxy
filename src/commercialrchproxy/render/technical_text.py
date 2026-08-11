"""Directional technical transcript; receive chunks are never called frames."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from commercialrchproxy.rch.protocol import ProtocolAnalysis

MAX_TECHNICAL_PAYLOAD_BYTES = 8 * 1024 * 1024


class ChunkLike(Protocol):
    direction: str
    timestamp: str
    offset: int
    data: bytes
    local_write_drain_completed: bool | None


def _hexdump(data: bytes, base: int = 0) -> Iterable[str]:
    for offset in range(0, len(data), 16):
        block = data[offset : offset + 16]
        hex_part = " ".join(f"{byte:02x}" for byte in block)
        ascii_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in block)
        yield f"{base + offset:08x}  {hex_part:<47}  |{ascii_part}|"


def render_technical_text(chunks: Iterable[ChunkLike], analysis: ProtocolAnalysis) -> str:
    output = [
        "[RCH SESSION COPY]",
        f"implementation_transport={analysis.implementation_transport}",
        "transport_detected=unknown",
        f"transport_evidence={analysis.transport_evidence}",
        "framing_confirmed=false",
        "note=receive chunks below are not asserted to be RCH frames or delivered bytes",
        "",
    ]
    remaining = MAX_TECHNICAL_PAYLOAD_BYTES
    truncated = False
    for index, chunk in enumerate(chunks, 1):
        if remaining <= 0:
            truncated = True
            break
        shown = chunk.data[:remaining]
        if len(shown) != len(chunk.data):
            truncated = True
        drain = chunk.local_write_drain_completed
        output.extend(
            (
                "[STREAM READ CHUNK]",
                f"sequence={index}",
                f"timestamp={chunk.timestamp}",
                f"direction={chunk.direction}",
                f"stream_offset={chunk.offset}",
                f"length={len(chunk.data)}",
                f"shown_length={len(shown)}",
                f"local_write_drain_completed={str(drain).lower() if drain is not None else 'unknown'}",
                "remote_arrival=unknown",
            )
        )
        output.extend(_hexdump(shown, chunk.offset))
        output.append("")
        remaining -= len(shown)
    if truncated:
        output.extend(
            (
                "[TECHNICAL TRANSCRIPT LIMIT]",
                "technical_payload_truncated=true",
                f"max_shown_bytes={MAX_TECHNICAL_PAYLOAD_BYTES}",
                "note=RAW completeness is reported independently in JSON",
                "",
            )
        )
    classification = analysis.classification
    xml = analysis.xml
    output.extend(
        (
            "[PASSIVE ANALYSIS]",
            f"parser_status={analysis.parser_status}",
            "telnet_negotiation_confirmed=false",
            f"telnet_iac_candidate_bytes_observed={str(analysis.telnet_iac_candidate_bytes_observed).lower()}",
            "document_type=unknown",
            f"candidate_printed_class={classification.candidate_printed_class or 'unknown'}",
            f"candidate_observed_variant={classification.candidate_observed_variant or 'unknown'}",
            f"candidate_classification_source={classification.source or 'unknown'}",
            f"candidate_classification_evidence={classification.evidence}",
            f"candidate_classification_confidence={classification.confidence:.2f}",
            f"xml_candidate_found={str(xml.candidate_found).lower()}",
            f"xml_well_formed_generic={str(xml.well_formed_generic).lower()}",
            f"xml7_confirmed={str(xml.xml7_confirmed).lower()}",
        )
    )
    if xml.error:
        output.append(f"xml_error={xml.error}")
    if xml.pretty_reserialized:
        output.extend(
            (
                "",
                "[GENERIC XML CANDIDATE - RESERIALIZED FOR TECHNICAL VIEW]",
                xml.pretty_reserialized,
            )
        )
    output.extend(("", "[RCH RESPONSE SEMANTICS]", "protocol_status=unknown", "application_success=unknown", ""))
    return "\n".join(output)
