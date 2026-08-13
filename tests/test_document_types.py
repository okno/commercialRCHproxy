from commercialrchproxy.rch.document_types import classify_document
from commercialrchproxy.rch.xml7 import analyze_xml_copy


def classify(payload: bytes):
    return classify_document(payload, analyze_xml_copy(payload))


def test_photo_commercial_phrase_is_only_a_content_fallback() -> None:
    result = classify(b"DOCUMENTO COMMERCIALE\r\ndi vendita o prestazione\r\nDOCUMENTO N. 0001-0001")
    assert result.document_type is None
    assert result.candidate_printed_class == "documento_commerciale"
    assert result.candidate_observed_variant == "sale_or_service"
    assert result.source == "content_keyword_fallback"
    assert result.evidence == "INFERRED"
    assert result.confidence < 0.7


def test_management_variants_are_descriptive_not_official_protocol_types() -> None:
    compact = classify(b"DOCUMENTO GESTIONALE\nTavolo: 00-X\nDOC.GESTIONALE N. 0001-0003")
    detail = classify(b"DOCUMENTO GESTIONALE\nContanti\nRESTO\nAliquota IVA\nImponibile")
    assert compact.document_type is None
    assert detail.document_type is None
    assert compact.candidate_printed_class == detail.candidate_printed_class == "documento_gestionale"
    assert compact.candidate_observed_variant == "compact_table_summary"
    assert detail.candidate_observed_variant == "payment_vat_detail"
    assert compact.evidence == detail.evidence == "INFERRED"
    assert compact.confidence == 0.35
    assert detail.confidence == 0.40


def test_management_heading_alone_never_infers_a_photo_subtype() -> None:
    result = classify(b"DOCUMENTO GESTIONALE\nProdotto di esempio")
    assert result.document_type is None
    assert result.candidate_printed_class == "documento_gestionale"
    assert result.candidate_observed_variant is None
    assert result.source == "content_keyword_fallback"
    assert result.evidence == "INFERRED"


def test_compact_variant_requires_both_photo_markers() -> None:
    table_only = classify(b"DOCUMENTO GESTIONALE\nTavolo: 00-X")
    number_only = classify(b"DOCUMENTO GESTIONALE\nDOC.GESTIONALE N. 0001-0003")
    assert table_only.candidate_observed_variant is None
    assert number_only.candidate_observed_variant is None


def test_unknown_binary_stays_unknown() -> None:
    result = classify(b"\x00\xff\x13\x37")
    assert result.document_type is None
    assert result.candidate_printed_class is None
    assert result.candidate_observed_variant is None
    assert result.evidence == "UNCONFIRMED"
    assert result.confidence == 0.0


def test_invalid_utf8_fallback_is_lossless_and_never_invents_a_marker() -> None:
    result = classify(b"\xff\x80DOCUMENTO GESTIONAL\xc8")
    assert result.document_type is None
    assert result.candidate_printed_class is None
    assert result.evidence == "UNCONFIRMED"
