from __future__ import annotations

import random
from pathlib import Path

from commercialrchproxy.rch.receipt_parser import parse_protocol_chunks, parse_protocol_copies

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> bytes:
    return bytes.fromhex((FIXTURES / name).read_text(encoding="ascii"))


def _random_chunks(data: bytes) -> list[bytes]:
    rng = random.Random(314159)
    chunks: list[bytes] = []
    offset = 0
    while offset < len(data):
        width = rng.randint(1, 17)
        chunks.append(data[offset : offset + width])
        offset += width
    return chunks


def test_sanitized_private_shape_remains_partial_and_chunk_invariant() -> None:
    request = _fixture("rch_synthetic_partial_transaction.request.hex")
    response = _fixture("rch_synthetic_partial_transaction.response.hex")

    assert (len(request), len(response)) == (235, 202)
    whole = parse_protocol_copies(request, response)
    fragmented = parse_protocol_chunks(_random_chunks(request), _random_chunks(response))

    assert len(whole.request_framing.frames) == 10
    assert len(whole.response_framing.frames) == 9
    assert len(whole.response_framing.acks) == 10
    assert all(frame.bcc_valid for frame in [*whole.request_framing.frames, *whole.response_framing.frames])
    assert whole.to_dict() == fragmented.to_dict()
    assert len(whole.documents) == 1
    document = whole.documents[0]
    assert document.document_type == "commerciale"
    assert document.complete is False
    assert [item["amount_cents"] for item in document.model.items] == [300, 400, 200]
    assert document.model.totals[0]["amount_cents"] == 900
    issue_codes = {issue.code for issue in whole.issues}
    assert {"incomplete_document", "missing_response_frame_candidate"} <= issue_codes
