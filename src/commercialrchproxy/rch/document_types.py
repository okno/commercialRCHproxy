"""Non-authoritative printed-class candidates from fallback text markers.

Protocol identifiers and validated XML mappings are intentionally absent.  A
candidate produced here never becomes the authoritative ``document_type``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CLASSIFICATION_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Classification:
    document_type: str | None
    source: str | None
    confidence: float
    evidence: str
    candidate_printed_class: str | None
    candidate_observed_variant: str | None


UNKNOWN = Classification(None, None, 0.0, "UNCONFIRMED", None, None)


def _visible_text(payload: bytes) -> str:
    bounded = payload[:MAX_CLASSIFICATION_BYTES]
    try:
        text = bounded.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        # The official character set is unknown.  Latin-1 is used only as a
        # reversible one-byte diagnostic view so no byte is silently replaced
        # or discarded; this fallback never becomes an authoritative type.
        text = bounded.decode("latin-1", errors="strict")
    return re.sub(r"\s+", " ", text).upper()


def classify_document(payload: bytes, _xml: object = None) -> Classification:
    searchable = _visible_text(payload)
    if "DOCUMENTO COMMERCIALE" in searchable and "VENDITA O PRESTAZIONE" in searchable:
        return Classification(
            None,
            "content_keyword_fallback",
            0.50,
            "INFERRED",
            "documento_commerciale",
            "sale_or_service",
        )

    if "DOCUMENTO GESTIONALE" not in searchable:
        return UNKNOWN

    detail_markers = ("RESTO", "ALIQUOTA IVA", "IMPONIBILE")
    if all(marker in searchable for marker in detail_markers):
        return Classification(
            None,
            "content_keyword_fallback",
            0.40,
            "INFERRED",
            "documento_gestionale",
            "payment_vat_detail",
        )

    compact_markers = ("TAVOLO", "DOC.GESTIONALE N.")
    if all(marker in searchable for marker in compact_markers):
        return Classification(
            None,
            "content_keyword_fallback",
            0.35,
            "INFERRED",
            "documento_gestionale",
            "compact_table_summary",
        )

    return Classification(None, "content_keyword_fallback", 0.20, "INFERRED", "documento_gestionale", None)
