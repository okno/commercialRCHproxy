"""Protocol evidence types and passive analysis facade."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from commercialrchproxy.rch.document_types import Classification, classify_document
from commercialrchproxy.rch.receipt_parser import ProtocolCopiesResult, parse_protocol_copies
from commercialrchproxy.rch.responses import ResponseAnalysis, analyze_response
from commercialrchproxy.rch.xml7 import XMLAnalysis, analyze_xml_copy
from commercialrchproxy.render.document_model import DocumentModel, build_document_model

_TELNET_CANDIDATE_SCAN_BYTES = 8 * 1024 * 1024


class EvidenceLevel(StrEnum):
    DOCUMENTED = "DOCUMENTED"
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    UNCONFIRMED = "UNCONFIRMED"


@dataclass(frozen=True, slots=True)
class ProtocolAnalysis:
    implementation_transport: str
    detected_transport: str | None
    transport_evidence: str
    framing_confirmed: bool
    telnet_iac_candidate_bytes_observed: bool
    xml: XMLAnalysis
    classification: Classification
    response: ResponseAnalysis
    document: DocumentModel
    documents: tuple[DocumentModel, ...]
    protocol: ProtocolCopiesResult | None
    parser_status: str
    parser_error: str | None = None


def _canonical_document_type(value: str | None) -> tuple[str | None, str | None]:
    mapping = {
        "documento_commerciale": ("commerciale", "documento_commerciale"),
        "commerciale": ("commerciale", "documento_commerciale"),
        "documento_gestionale": ("gestionale", "documento_gestionale"),
        "gestionale": ("gestionale", "documento_gestionale"),
    }
    return mapping.get(value, (None, None))


def _framing_confirmed(protocol: ProtocolCopiesResult) -> bool:
    request = protocol.request_framing
    response = protocol.response_framing
    request_profile = (
        bool(request.frames)
        and not request.acks
        and not request.issues
        and all(frame.bcc_valid and frame.address == "00" and frame.frame_class == "z" for frame in request.frames)
    )
    response_profile = (
        not response.issues
        and all(frame.bcc_valid and frame.address == "01" and frame.frame_class == "N" for frame in response.frames)
    )
    return request_profile and response_profile


def _has_bounded_telnet_iac_candidate(request: bytes, response: bytes) -> bool:
    """Look for an IAC verb plus option byte without a Python byte loop.

    This remains only a candidate signal, never a Telnet classification.  The
    bounded C-level searches keep passive sidecar analysis proportional to the
    same finite prefix used by the semantic parser.
    """

    verbs = (b"\xff\xfb", b"\xff\xfc", b"\xff\xfd", b"\xff\xfe")
    for payload in (request, response):
        end = min(len(payload), _TELNET_CANDIDATE_SCAN_BYTES)
        if end < 3:
            continue
        # Stop one byte before ``end`` so a match is accepted only when an
        # option byte also exists inside the bounded prefix.
        if any(payload.find(verb, 0, end - 1) >= 0 for verb in verbs):
            return True
    return False


def analyze_copies(request: bytes, response: bytes) -> ProtocolAnalysis:
    """Analyze copies of a job; callers must never feed output back inline."""
    protocol = parse_protocol_copies(request, response)
    xml = analyze_xml_copy(request)
    fallback_classification = classify_document(request)
    response_analysis = analyze_response(response)
    documents = tuple(parsed.model for parsed in protocol.documents)
    if protocol.documents:
        canonical_type, printed_class = _canonical_document_type(protocol.documents[0].document_type)
        classification = Classification(
            canonical_type,
            "observed_rch_command_sequence",
            0.90,
            "INFERRED",
            printed_class,
            None,
        )
        for model in documents:
            canonical_model_type, candidate = _canonical_document_type(model.document_type)
            model.document_type = canonical_model_type
            model.metadata.setdefault("candidate_printed_class", candidate)
            model.metadata["human_render_status"] = "available_partial_observed_payload_inferred_command_mapping"
        document = documents[0]
    else:
        classification = fallback_classification
        document = build_document_model(request, xml, classification)
    # Port 23 does not establish Telnet.  This merely records candidate IAC
    # command bytes followed by an option byte; it is not stateful negotiation
    # detection and the relay never interprets or consumes them.
    iac_candidate = _has_bounded_telnet_iac_candidate(request, response)
    framing_confirmed = _framing_confirmed(protocol)
    if protocol.documents:
        completeness = "complete" if all(document.complete for document in protocol.documents) else "partial"
        parser_status = f"{completeness}_document_reconstruction_inferred_semantics"
    elif protocol.request_framing.frames:
        parser_status = "framed_stream_no_document_reconstructed"
    else:
        parser_status = "unrecognized_stream"
    if protocol.issues and protocol.request_framing.frames:
        parser_status += "_with_issues"
    return ProtocolAnalysis(
        implementation_transport="tcp_stream",
        detected_transport=None,
        transport_evidence="UNCONFIRMED",
        framing_confirmed=framing_confirmed,
        telnet_iac_candidate_bytes_observed=iac_candidate,
        xml=xml,
        classification=classification,
        response=response_analysis,
        document=document,
        documents=documents,
        protocol=protocol,
        parser_status=parser_status,
    )


def unavailable_analysis(request: bytes, response: bytes, error: Exception) -> ProtocolAnalysis:
    """Return a conservative analysis after an unexpected parser failure.

    Storage calls this only after publishing the immutable RAW copies.  It
    intentionally avoids the RCH parser so the same fault cannot recurse and
    suppress the forensic manifest.
    """
    xml = analyze_xml_copy(request)
    classification = classify_document(request)
    document = build_document_model(request, xml, classification)
    document.metadata["parser_error"] = f"{type(error).__name__}: {error}"
    return ProtocolAnalysis(
        implementation_transport="tcp_stream",
        detected_transport=None,
        transport_evidence="UNCONFIRMED",
        framing_confirmed=False,
        telnet_iac_candidate_bytes_observed=False,
        xml=xml,
        classification=classification,
        response=analyze_response(response),
        document=document,
        documents=(),
        protocol=None,
        parser_status="parser_error_raw_preserved",
        parser_error=f"{type(error).__name__}: {error}",
    )
