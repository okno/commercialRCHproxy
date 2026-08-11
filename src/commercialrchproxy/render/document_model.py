"""Traceable intermediate model for explicitly mapped human-visible fields."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from commercialrchproxy.rch.document_types import Classification
    from commercialrchproxy.rch.xml7 import XMLAnalysis


@dataclass(frozen=True, slots=True)
class SourceTrace:
    source_offset: int | None = None
    source_frame: int | None = None
    source_xml_path: str | None = None
    evidence: str = "UNCONFIRMED"


@dataclass(frozen=True, slots=True)
class DocumentLine:
    text: str
    trace: SourceTrace = SourceTrace()
    align: str = "left"
    bold: bool = False
    double_width: bool = False
    double_height: bool = False


@dataclass(slots=True)
class DocumentModel:
    document_type: str | None = None
    observed_variant: str | None = None
    header: list[DocumentLine] = field(default_factory=list)
    lines: list[DocumentLine] = field(default_factory=list)
    footer: list[DocumentLine] = field(default_factory=list)
    items: list[dict[str, object]] = field(default_factory=list)
    quantities: list[object] = field(default_factory=list)
    descriptions: list[str] = field(default_factory=list)
    amounts: list[object] = field(default_factory=list)
    taxes: list[dict[str, object]] = field(default_factory=list)
    payments: list[dict[str, object]] = field(default_factory=list)
    totals: list[dict[str, object]] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    date: str | None = None
    time: str | None = None
    document_number: str | None = None
    fiscal_fields: dict[str, object] = field(default_factory=dict)


def build_document_model(_payload: bytes, xml: XMLAnalysis, classification: Classification) -> DocumentModel:
    """Return an empty human model until an authoritative mapping exists.

    Generic XML leaves and guessed raw-text decoding remain technical evidence;
    neither is proof of what the physical printer rendered.
    """
    return DocumentModel(
        document_type=classification.document_type,
        metadata={
            "human_render_status": "unavailable_unconfirmed_field_mapping",
            "xml_candidate_found": xml.candidate_found,
            "candidate_printed_class": classification.candidate_printed_class,
        },
    )
