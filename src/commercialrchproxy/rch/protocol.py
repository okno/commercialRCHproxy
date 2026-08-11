"""Protocol evidence types and passive analysis facade."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from commercialrchproxy.rch.document_types import Classification, classify_document
from commercialrchproxy.rch.responses import ResponseAnalysis, analyze_response
from commercialrchproxy.rch.xml7 import XMLAnalysis, analyze_xml_copy
from commercialrchproxy.render.document_model import DocumentModel, build_document_model


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
    parser_status: str


def analyze_copies(request: bytes, response: bytes) -> ProtocolAnalysis:
    """Analyze copies of a job; callers must never feed output back inline."""
    xml = analyze_xml_copy(request)
    classification = classify_document(request)
    response_analysis = analyze_response(response)
    document = build_document_model(request, xml, classification)
    # Port 23 does not establish Telnet.  This merely records candidate IAC
    # command bytes followed by an option byte; it is not stateful negotiation
    # detection and the relay never interprets or consumes them.
    iac_candidate = any(
        any(
            payload[index] == 255 and payload[index + 1] == command
            for payload in (request, response)
            for index in range(max(0, len(payload) - 2))
        )
        for command in (251, 252, 253, 254)
    )
    return ProtocolAnalysis(
        implementation_transport="tcp_stream",
        detected_transport=None,
        transport_evidence="UNCONFIRMED",
        framing_confirmed=False,
        telnet_iac_candidate_bytes_observed=iac_candidate,
        xml=xml,
        classification=classification,
        response=response_analysis,
        document=document,
        parser_status="best_effort_unconfirmed_framing",
    )
