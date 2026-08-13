from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from commercialrchproxy.rch.framing import build_frame
from commercialrchproxy.rch.receipt_parser import (
    parse_protocol_chunks,
    parse_protocol_copies,
    receipt_to_dict,
    receipt_to_text,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _hex_fixture(name: str) -> bytes:
    return bytes.fromhex((FIXTURES / name).read_text(encoding="ascii"))


def _expected(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _synthetic_request(*payloads: bytes) -> bytes:
    return b"".join(build_frame(data, sequence=str(index % 10)) for index, data in enumerate(payloads))


def test_commercial_stream_matches_sanitized_golden_output() -> None:
    result = parse_protocol_copies(
        _hex_fixture("rch_synthetic_commercial.request.hex"),
        _hex_fixture("rch_synthetic_commercial.response.hex"),
    )

    assert not result.issues
    assert len(result.documents) == 1
    document = result.documents[0]
    assert document.document_type == "commerciale"
    assert document.printed_class == "documento_commerciale"
    assert document.evidence == "INFERRED"
    assert document.complete
    assert receipt_to_text(document) == _expected("rch_synthetic_commercial.expected.txt")
    assert document.model.items[0]["description"] == "VOCE SINTETICA"
    assert document.model.items[0]["amount_cents"] == 0
    assert document.model.items[0]["quantity"] == 1
    assert document.model.metadata["order_value"] == "XX"
    assert document.model.document_number == "3141"
    assert document.model.metadata["document_number_scope"] == "suffix_only"
    assert document.model.metadata["document_number_prefix"] is None
    assert document.model.payments == [
        {
            "method": None,
            "amount_cents": 0,
            "source_code": "T1",
            "source": document.model.payments[0]["source"],
        }
    ]
    assert all("=D" not in line.text for line in document.model.lines)
    assert all(correlation.sequence_matches for correlation in result.correlations)
    assert [transition["to"] for transition in document.model.metadata["document_state_transitions"]] == [
        "commercial_body",
        "commercial_payment",
        "commercial_postlude",
        "complete",
    ]
    unknown = next(message for message in result.messages if message.role == "unknown_request_command")
    assert unknown.data == b"=C1"
    assert unknown.evidence == "UNKNOWN"


def test_management_stream_matches_sanitized_golden_output() -> None:
    result = parse_protocol_copies(
        _hex_fixture("rch_synthetic_management.request.hex"),
        _hex_fixture("rch_synthetic_management.response.hex"),
    )

    assert len(result.documents) == 1
    document = result.documents[0]
    assert document.document_type == "gestionale"
    assert document.printed_class == "documento_gestionale"
    assert document.complete
    assert receipt_to_text(document) == _expected("rch_synthetic_management.expected.txt")
    assert document.model.items[0]["description"] == "VOCE SINTETICA"
    assert document.model.payments[0]["method_text"] == "Contanti"
    assert document.model.payments[0]["amount_cents"] == 0
    assert document.model.taxes[0]["tax_amount_cents"] == 0
    assert document.model.metadata["order_value"] == "XX"
    assert document.model.date == "00\\00\\00"
    assert document.model.time == "00:00"
    assert document.model.document_number == "0000-0000"
    styled = next(line for line in document.model.lines if line.text.startswith("TOT"))
    assert styled.double_width and styled.double_height
    assert document.model.metadata["final_document_state"] == "complete"
    assert [issue.code for issue in result.issues] == ["missing_response_frame_candidate"]


def test_multiple_documents_in_one_stream_are_not_concatenated() -> None:
    request = _hex_fixture("rch_synthetic_management.request.hex")
    response = _hex_fixture("rch_synthetic_management.response.hex")
    result = parse_protocol_copies(request + request, response + response)

    assert len(result.documents) == 2
    assert all(document.complete for document in result.documents)
    assert result.documents[0].frame_ids[-1] < result.documents[1].frame_ids[0]


def test_incomplete_document_is_preserved_with_null_unobserved_fields() -> None:
    request = build_frame("=K", sequence="0") + build_frame("=R1/$000/*1/(TEST)", sequence="1")
    response = (
        b"\x06" + build_frame("ON00000000", address="01", frame_class="N", sequence="8")
        + b"\x06" + build_frame("ON00000000", address="01", frame_class="N", sequence="9")
    )
    result = parse_protocol_copies(request, response)

    document = result.documents[0]
    assert not document.complete
    assert document.model.date is None
    assert document.model.time is None
    assert document.model.document_number is None
    assert any(issue.code == "incomplete_document" for issue in result.issues)


def test_result_helpers_are_json_ready_and_keep_source_evidence() -> None:
    result = parse_protocol_copies(
        _hex_fixture("rch_synthetic_commercial.request.hex"),
        _hex_fixture("rch_synthetic_commercial.response.hex"),
    )
    parsed = receipt_to_dict(result.documents[0])

    assert parsed["document_type"] == "commerciale"
    assert parsed["printed_class"] == "documento_commerciale"
    assert parsed["parsed"]["items"][0]["source"]["frame_id"] == 4
    assert parsed["parsed"]["items"][0]["source"]["evidence"] == "INFERRED"
    assert result.to_dict()["evidence_policy"]["framing_and_literal_payload"] == "CONFIRMED"
    json.dumps(result.to_dict(), ensure_ascii=False)


def test_response_sequence_mismatch_is_reported_without_losing_documents() -> None:
    request = build_frame("=o", sequence="0") + build_frame("=o", sequence="1")
    response = (
        b"\x06" + build_frame("ON00000000", address="01", frame_class="N", sequence="7")
        + b"\x06" + build_frame("ON00000000", address="01", frame_class="N", sequence="9")
    )
    result = parse_protocol_copies(request, response)

    assert result.documents[0].complete
    assert result.correlations[0].sequence_matches is False
    assert any(issue.code == "response_sequence_mismatch" for issue in result.issues)


def test_counter_is_not_attached_from_mismatched_response() -> None:
    request = (
        build_frame("=K", sequence="0")
        + build_frame("=T1/$000", sequence="1")
        + build_frame("<</?7", sequence="2")
    )
    response = (
        b"\x06" + build_frame("ON00000000", address="01", frame_class="N", sequence="8")
        + b"\x06" + build_frame("ON00000000", address="01", frame_class="N", sequence="9")
        + b"\x06" + build_frame("s000000RE1111", address="01", frame_class="N", sequence="1")
    )

    result = parse_protocol_copies(request, response)

    assert result.documents[0].complete
    assert result.documents[0].model.document_number is None
    assert result.correlations[-1].sequence_matches is False


def test_pre_document_counter_is_not_used_when_post_payment_query_has_no_response() -> None:
    request = (
        build_frame("<</?s", sequence="0")
        + build_frame("=K", sequence="1")
        + build_frame("=T1/$000", sequence="2")
        + build_frame("<</?s", sequence="3")
        + build_frame("<</?7", sequence="4")
    )
    response = (
        b"\x06" + build_frame("s000000RE1111", address="01", frame_class="N", sequence="8")
        + b"\x06" + build_frame("ON00000000", address="01", frame_class="N", sequence="9")
        + b"\x06" + build_frame("ON00000000", address="01", frame_class="N", sequence="0")
    )

    result = parse_protocol_copies(request, response)

    assert result.documents[0].complete
    assert result.documents[0].model.document_number is None


def _split(payload: bytes, mode: str) -> list[bytes]:
    if mode == "whole":
        return [payload]
    if mode in {"one", "seven"}:
        size = 1 if mode == "one" else 7
        return [payload[offset : offset + size] for offset in range(0, len(payload), size)]
    rng = random.Random(5737)
    chunks: list[bytes] = []
    offset = 0
    while offset < len(payload):
        size = rng.randint(1, 23)
        chunks.append(payload[offset : offset + size])
        offset += size
    return chunks


@pytest.mark.parametrize("fixture_stem", ["commercial", "management"])
@pytest.mark.parametrize("mode", ["whole", "one", "seven", "random"])
def test_end_to_end_receipt_is_independent_of_tcp_segmentation(fixture_stem: str, mode: str) -> None:
    request = _hex_fixture(f"rch_synthetic_{fixture_stem}.request.hex")
    response = _hex_fixture(f"rch_synthetic_{fixture_stem}.response.hex")
    expected = parse_protocol_copies(request, response)

    actual = parse_protocol_chunks(_split(request, mode), _split(response, mode))

    assert actual.to_dict() == expected.to_dict()
    assert actual.receipt_texts == expected.receipt_texts


def test_parser_diagnostics_are_bounded_on_hostile_frame_volume() -> None:
    payload = build_frame("", sequence="0") * 20000

    result = parse_protocol_copies(payload, b"", max_events=64, max_messages=32, max_issues=16)

    assert len(result.request_framing.events) == 64
    assert result.request_framing.total_frame_count == 20000
    assert result.request_framing.events_truncated
    assert len(result.messages) == 32
    assert len(result.issues) <= 16
    assert any(issue.code == "result_issue_limit_exceeded" for issue in result.issues)


@pytest.mark.parametrize("chunked", [False, True])
def test_global_semantic_field_budget_bounds_dense_amount_expansion(chunked: bool) -> None:
    dense_amounts = "0,00 " * 160
    request = (
        build_frame("=o", sequence="0")
        + build_frame(f'="/({dense_amounts})', sequence="1")
        + build_frame("=o", sequence="2")
    )

    result = (
        parse_protocol_chunks([request], [], max_semantic_fields=32)
        if chunked
        else parse_protocol_copies(request, b"", max_semantic_fields=32)
    )

    document = result.documents[0]
    model = document.model
    retained_semantic_records = sum(
        len(collection)
        for collection in (
            model.header,
            model.lines,
            model.footer,
            model.items,
            model.quantities,
            model.descriptions,
            model.amounts,
            model.taxes,
            model.payments,
            model.totals,
        )
    )
    assert document.complete
    assert retained_semantic_records == 32
    assert len(model.amounts) == 31
    assert b"".join(frame.raw for frame in result.request_framing.frames) == request
    assert len(result.messages) == 3
    assert [issue.code for issue in result.issues].count("semantic_field_limit_exceeded") == 1


def test_semantic_field_budget_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_semantic_fields"):
        parse_protocol_copies(build_frame("=o"), b"", max_semantic_fields=0)


def test_semantic_limit_issue_survives_other_issue_flood() -> None:
    dense_amounts = "0,00 " * 160
    request = build_frame("=o", sequence="0")
    for sequence in range(20):
        request += build_frame(f'="/({dense_amounts})', sequence=str((sequence + 1) % 10))
    request += build_frame("=o", sequence="1")

    result = parse_protocol_copies(
        request,
        b"",
        max_semantic_fields=32,
        max_issues=16,
    )

    assert len(result.issues) == 16
    assert any(issue.code == "semantic_field_limit_exceeded" for issue in result.issues)
    assert result.issues[-1].code == "result_issue_limit_exceeded"


def test_semantic_byte_limit_is_explicit_and_preserves_prefix_analysis() -> None:
    frame = build_frame("=o", sequence="0")
    result = parse_protocol_copies(frame * 3, b"", max_analyzed_bytes=len(frame))

    assert result.request_framing.bytes_seen == len(frame)
    assert len(result.request_framing.frames) == 1
    assert any(issue.code == "analysis_byte_limit_exceeded" for issue in result.issues)


def test_checksum_valid_but_unexpected_directional_profile_has_no_semantics() -> None:
    request = build_frame("=o", address="99", frame_class="X", sequence="0") + build_frame(
        "=o", address="99", frame_class="X", sequence="1"
    )

    result = parse_protocol_copies(request, b"")

    assert result.documents == ()
    assert {message.role for message in result.messages} == {"unexpected_request_profile"}


def test_malformed_t_prefix_cannot_enable_post_payment_counter() -> None:
    request = (
        build_frame("=K", sequence="0")
        + build_frame("=THIS-IS-NOT-A-TOTAL", sequence="1")
        + build_frame("<</?s", sequence="2")
        + build_frame("<</?7", sequence="3")
    )
    response = (
        b"\x06" + build_frame("ON00000000", address="01", frame_class="N", sequence="8")
        + b"\x06" + build_frame("ON00000000", address="01", frame_class="N", sequence="9")
        + b"\x06" + build_frame("s000000RE1111", address="01", frame_class="N", sequence="0")
        + b"\x06" + build_frame("ON00000000", address="01", frame_class="N", sequence="1")
    )

    result = parse_protocol_copies(request, response)

    assert result.documents[0].complete
    assert result.documents[0].model.document_number is None


def test_price_change_is_isolated_across_precount_commercial_and_conforming_copy() -> None:
    request = _synthetic_request(
        b"=o",
        b'="/(VOCE ALFA 88,00 A)',
        b'="/(TOT 88,00)',
        b"=o",
        b"=K",
        b"=R1/$300/*1/(VOCE ALFA)",
        b"=T1/$300",
        b"<</?7",
        b"=o",
        b'="/(VOCE ALFA 3,00 A)',
        b'="/(TOT 3,00)',
        b'="/(Contanti 3,00)',
        b'="/(RESTO 0,00)',
        b'="/(A 10% 10% 0,91 0,09)',
        b"=o",
    )

    result = parse_protocol_copies(request, b"")

    assert len(result.documents) == 3
    precount, commercial, conforming_copy = result.documents
    assert precount.model.metadata["subtype"] == "PRECONTO"
    assert precount.model.items[0]["amount_cents"] == 8800
    assert precount.model.totals[0]["amounts"][0]["cents"] == 8800
    assert commercial.model.metadata["subtype"] == "DOCUMENTO COMMERCIALE"
    assert commercial.model.items[0]["amount_cents"] == 300
    assert commercial.model.totals[0]["amount_cents"] == 300
    assert conforming_copy.model.metadata["subtype"] == "COPIA CONFORME"
    assert conforming_copy.model.metadata["copy_of"] == commercial.document_id
    assert conforming_copy.model.items[0]["amount_cents"] == 300
    assert conforming_copy.model.totals[0]["amounts"][0]["cents"] == 300


def test_management_command_requires_captured_markers_and_never_invents_prices() -> None:
    request = _synthetic_request(
        b"=o",
        b'="/(Portata: 1)',
        b'="/(VOCE ALFA)',
        b'="/(Coperti: 1)',
        b"=o",
    )

    document = parse_protocol_copies(request, b"").documents[0]

    assert document.document_type == "gestionale"
    assert document.model.metadata["subtype"] == "COMANDA"
    assert document.model.items == []
    assert document.model.amounts == []
