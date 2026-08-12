from __future__ import annotations

import random
from pathlib import Path

import pytest

from commercialrchproxy.rch.framing import (
    ACK,
    ETX,
    STX,
    AckEvent,
    RCHFrame,
    RCHStreamFramer,
    assess_framing,
    build_frame,
    calculate_bcc,
    frame_stream,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _hex_fixture(name: str) -> bytes:
    return bytes.fromhex((FIXTURES / name).read_text(encoding="ascii"))


def _chunks(payload: bytes, mode: str) -> list[bytes]:
    if mode == "whole":
        return [payload]
    if mode == "one":
        return [payload[index : index + 1] for index in range(len(payload))]
    if mode == "seven":
        return [payload[index : index + 7] for index in range(0, len(payload), 7)]
    rng = random.Random(5737)
    result: list[bytes] = []
    offset = 0
    while offset < len(payload):
        size = rng.randint(1, 19)
        result.append(payload[offset : offset + size])
        offset += size
    return result


@pytest.mark.parametrize("mode", ["whole", "one", "seven", "random"])
@pytest.mark.parametrize(
    "fixture_name",
    [
        "rch_synthetic_commercial.request.hex",
        "rch_synthetic_commercial.response.hex",
        "rch_synthetic_management.request.hex",
        "rch_synthetic_management.response.hex",
        "rch_synthetic_display.request.hex",
        "rch_synthetic_display.response.hex",
    ],
)
def test_incremental_framing_is_independent_of_tcp_segmentation(fixture_name: str, mode: str) -> None:
    payload = _hex_fixture(fixture_name)
    expected = frame_stream(payload)
    framer = RCHStreamFramer()
    emitted = []
    for chunk in _chunks(payload, mode):
        emitted.extend(framer.feed(chunk))
    actual = framer.finish()

    assert tuple(emitted) == actual.events
    assert actual == expected
    assert not actual.issues
    assert all(frame.bcc_valid for frame in actual.frames)


def test_confirmed_frame_fields_and_bcc_cover_stx_through_sequence() -> None:
    raw = build_frame("=o", sequence="4")
    result = frame_stream(raw)

    assert len(raw) == 2 + 11
    assert raw[0] == STX and raw[-1] == ETX
    assert len(result.frames) == 1
    frame = result.frames[0]
    assert frame.address == "00"
    assert frame.data_length == 2
    assert frame.frame_class == "z"
    assert frame.data == b"=o"
    assert frame.sequence == "4"
    assert frame.bcc_valid
    assert int(frame.bcc, 16) == calculate_bcc(raw[:-3])
    assert assess_framing(raw).confirmed


def test_sanitized_corpus_preserves_all_77_observed_frame_shapes() -> None:
    corpus = [
        _hex_fixture("rch_synthetic_commercial.request.hex"),
        _hex_fixture("rch_synthetic_commercial.response.hex"),
        _hex_fixture("rch_synthetic_management.request.hex"),
        _hex_fixture("rch_synthetic_management.response.hex"),
    ]
    display_pair = [
        _hex_fixture("rch_synthetic_display.request.hex"),
        _hex_fixture("rch_synthetic_display.response.hex"),
    ]
    corpus.extend(display_pair * 4)
    results = [frame_stream(payload) for payload in corpus]

    assert sum(len(result.frames) for result in results) == 77
    assert sum(len(result.acks) for result in results) == 39
    assert all(not result.issues for result in results)
    assert all(frame.bcc_valid for result in results for frame in result.frames)
    management_request = corpus[2]
    assert len(management_request) == 826
    assert [len(frame.raw) for frame in results[2].frames] == [
        13,
        61,
        63,
        64,
        16,
        61,
        64,
        16,
        63,
        63,
        63,
        63,
        63,
        16,
        29,
        16,
        63,
        16,
        13,
    ]


def test_ack_is_a_standalone_event() -> None:
    result = frame_stream(bytes((ACK,)) + build_frame("ON00000000", address="01", frame_class="N", sequence="8"))

    assert isinstance(result.events[0], AckEvent)
    assert isinstance(result.events[1], RCHFrame)
    assert result.acks[0].raw == b"\x06"


def test_bad_bcc_is_retained_as_a_frame_and_an_issue() -> None:
    raw = bytearray(build_frame("=K"))
    raw[-2] = ord("0") if raw[-2] != ord("0") else ord("1")
    result = frame_stream(bytes(raw))

    assert len(result.frames) == 1
    assert not result.frames[0].bcc_valid
    assert result.issues[0].code == "invalid_bcc"
    assert result.issues[0].raw == bytes(raw)


def test_truncated_frame_bytes_are_preserved_on_finish() -> None:
    complete = build_frame("=R1/$000/*1/(TEST)")
    truncated = complete[:-4]
    result = frame_stream(truncated)

    assert not result.frames
    assert result.issues[0].code == "truncated_frame"
    assert result.issues[0].raw == truncated


def test_oversize_and_malformed_frames_do_not_hide_a_later_valid_frame() -> None:
    oversize = build_frame(b"X" * 11)
    malformed = b"\x02AA003zBAD0FF\x03"
    valid = build_frame("=o", sequence="9")
    result = frame_stream(oversize + malformed + valid, max_data_length=10)

    assert [issue.code for issue in result.issues[:2]] == ["oversize_frame", "malformed_header"]
    assert result.frames[-1].raw == valid
    assert result.frames[-1].bcc_valid


def test_invalid_terminator_resynchronizes_at_the_next_stx() -> None:
    damaged = bytearray(build_frame("=K"))
    damaged[-1] = 0
    valid = build_frame("=o", sequence="1")
    result = frame_stream(bytes(damaged) + valid)

    assert result.issues[0].code == "invalid_terminator"
    assert result.issues[0].raw == bytes(damaged)
    assert [frame.data for frame in result.frames] == [b"=o"]


def test_framer_rejects_impossible_hard_limits() -> None:
    with pytest.raises(ValueError, match="between 0 and 999"):
        RCHStreamFramer(max_data_length=1000)
    with pytest.raises(ValueError, match="largest accepted frame"):
        RCHStreamFramer(max_data_length=100, max_buffer_bytes=100)


def test_large_feed_of_many_small_frames_is_processed_without_discarding_bytes() -> None:
    frames = [build_frame("=o", sequence=str(index % 9)) for index in range(500)]
    payload = b"".join(frames)
    assert len(payload) > 4096

    result = frame_stream(payload)

    assert len(result.frames) == len(frames)
    assert b"".join(frame.raw for frame in result.frames) == payload
    assert not result.issues


def test_unframed_diagnostic_preview_and_issue_count_are_bounded() -> None:
    payload = b"X" * 100000
    result = frame_stream(payload, max_buffer_bytes=1010, max_issues=4, max_issue_raw_bytes=32)

    assert result.bytes_seen == len(payload)
    assert len(result.issues) == 4
    assert result.omitted_issue_count > 0
    assert result.issues[-1].code == "issue_limit_exceeded"
    assert all(len(issue.raw) <= 32 for issue in result.issues)
    assert any(issue.to_dict()["raw_preview_truncated"] for issue in result.issues[:-1])


def test_nonretaining_framer_keeps_only_partial_carry_between_feeds() -> None:
    framer = RCHStreamFramer(retain_history=False)
    frame = build_frame("=o")

    assert len(framer.feed(frame + frame[:5])) == 1
    assert framer.events == ()
    assert framer.buffered_bytes == frame[:5]
    assert len(framer.feed(frame[5:])) == 1
    assert framer.events == ()
    assert framer.buffered_bytes == b""
