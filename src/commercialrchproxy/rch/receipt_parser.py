"""Evidence-labelled reconstruction of printable RCH command streams.

Framing and literal command bytes are capture-confirmed.  The command roles in
this module are inferred from their position and their correlation with the
supplied printed documents; they are intentionally labelled ``INFERRED``.
Unknown commands remain messages and missing receipt fields remain ``None``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from commercialrchproxy.rch.framing import (
    AckEvent,
    FramingIssue,
    FramingResult,
    RCHFrame,
    RCHStreamFramer,
    frame_stream,
)
from commercialrchproxy.render.clean_text import render_clean_text
from commercialrchproxy.render.document_model import DocumentLine, DocumentModel, SourceTrace

CONFIRMED = "CONFIRMED"
INFERRED = "INFERRED"
UNKNOWN = "UNKNOWN"
_DEFAULT_MAX_EVENTS = 8192
_DEFAULT_MAX_RESULT_ISSUES = 1024
_DEFAULT_MAX_DOCUMENTS = 256
_DEFAULT_MAX_MESSAGES = 8192
_DEFAULT_MAX_ANALYZED_BYTES = 8 * 1024 * 1024
_DEFAULT_MAX_SEMANTIC_FIELDS = 32768


class DocumentAssemblyState(StrEnum):
    """Inferred document lifecycle; frame boundaries remain CONFIRMED."""

    IDLE = "idle"
    COMMERCIAL_BODY = "commercial_body"
    COMMERCIAL_PAYMENT = "commercial_payment"
    COMMERCIAL_POSTLUDE = "commercial_postlude"
    MANAGEMENT_BODY = "management_body"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"

_MANAGEMENT_LINE_RE = re.compile(r'^="/\((?P<text>.*)\)(?:/\*(?P<style>\d+))?$')
_COMMERCIAL_TEXT_RE = re.compile(r'^="/\?A/\((?P<text>.*)\)(?:/\*(?P<style>\d+))?$')
_COMMERCIAL_ITEM_RE = re.compile(
    r"^=R(?P<code>[^/]+)/\$(?P<amount>[+-]?\d+)"
    r"(?:/\*(?P<quantity>[+-]?\d+))?/\((?P<description>.*)\)$"
)
_COMMERCIAL_TOTAL_RE = re.compile(r"^=T(?P<code>[^/]+)/\$(?P<amount>[+-]?\d+)$")
_DISPLAY_RE = re.compile(r"^=D(?P<line>\d+)/\((?P<text>.*)\)$")
_RESPONSE_COUNTER_RE = re.compile(r"^s\d{6}RE(?P<counter>\d{4})$")
_ORDER_RE = re.compile(r"^\s*(?:Ordine|Order)\s*:\s*(?P<value>.*?)\s*$", re.IGNORECASE)
_PRINTED_AMOUNT_RE = re.compile(r"(?<!\d)(?P<amount>[+-]?\d{1,3}(?:\.\d{3})*,\d{2})(?!\d)")
_PRINTED_ITEM_RE = re.compile(
    r"^(?P<description>.*?\S)\s+"
    r"(?P<amount>[+-]?\d{1,3}(?:\.\d{3})*,\d{2})"
    r"(?:\s+(?P<tax_class>[A-Z]))?\s*$"
)
_REFERENCE_RE = re.compile(
    r"(?P<date>\d{2}[\\/-]\d{2}[\\/-]\d{2,4})\s+"
    r"(?P<time>\d{2}:\d{2}).*?\bN\.\s*(?P<number>[0-9-]+)",
    re.IGNORECASE,
)


def _latin1(payload: bytes) -> str:
    """Return a lossless byte-to-codepoint view without claiming an encoding."""

    return payload.decode("latin-1")


def _source(frame: RCHFrame, *, evidence: str = CONFIRMED) -> dict[str, object]:
    return {
        "direction": "request",
        "frame_id": frame.frame_id,
        "stream_offset": frame.stream_offset,
        "end_offset": frame.end_offset,
        "evidence": evidence,
    }


def _trace(frame: RCHFrame, *, evidence: str = CONFIRMED) -> SourceTrace:
    return SourceTrace(source_offset=frame.stream_offset, source_frame=frame.frame_id, evidence=evidence)


def _format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    return f"{sign}{absolute // 100},{absolute % 100:02d}"


def parse_printed_amount(value: str) -> int | None:
    """Parse an observed Italian-style printed amount into minor units."""

    candidate = value.strip().replace(".", "")
    if not re.fullmatch(r"[+-]?\d+,\d{2}", candidate):
        return None
    sign = -1 if candidate.startswith("-") else 1
    unsigned = candidate.lstrip("+-")
    whole, fraction = unsigned.split(",", 1)
    return sign * (int(whole) * 100 + int(fraction))


@dataclass(frozen=True, slots=True)
class ReceiptIssue:
    code: str
    detail: str
    direction: str | None = None
    stream_offset: int | None = None
    frame_id: int | None = None
    raw: bytes = b""
    evidence: str = CONFIRMED

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "detail": self.detail,
            "direction": self.direction,
            "stream_offset": self.stream_offset,
            "frame_id": self.frame_id,
            "raw_hex": self.raw.hex(),
            "evidence": self.evidence,
        }


@dataclass(slots=True)
class _SemanticBudget:
    """Bound attacker-amplifiable semantic records across one parse.

    Frames, messages and immutable RAW evidence have their own independent
    limits.  This budget covers the derived collections used for human output
    (lines, amounts, items, descriptions, quantities, taxes, payments and
    totals), where one short input line can otherwise expand into many Python
    objects.
    """

    limit: int
    used: int = 0
    issue: ReceiptIssue | None = None

    def reserve(self, count: int, frame: RCHFrame, *, direction: str = "request") -> bool:
        if count < 0:
            raise ValueError("semantic reservation cannot be negative")
        if self.used + count <= self.limit:
            self.used += count
            return True
        if self.issue is None:
            self.issue = ReceiptIssue(
                code="semantic_field_limit_exceeded",
                detail=(
                    f"derived semantic records exceeded the global {self.limit}-field limit; "
                    "additional human-readable fields were omitted while RAW and framed messages remain available"
                ),
                direction=direction,
                stream_offset=frame.stream_offset,
                frame_id=frame.frame_id,
                evidence=CONFIRMED,
            )
        return False


@dataclass(frozen=True, slots=True)
class ProtocolMessage:
    message_id: int
    direction: str
    kind: str
    role: str
    evidence: str
    stream_offset: int
    end_offset: int
    frame_id: int | None = None
    frame_class: str | None = None
    data: bytes = b""
    raw: bytes = b""
    fields: dict[str, object] = field(default_factory=dict)

    @property
    def data_text(self) -> str:
        return _latin1(self.data)

    def to_dict(self) -> dict[str, object]:
        return {
            "message_id": self.message_id,
            "direction": self.direction,
            "kind": self.kind,
            "role": self.role,
            "evidence": self.evidence,
            "stream_offset": self.stream_offset,
            "end_offset": self.end_offset,
            "frame_id": self.frame_id,
            "class": self.frame_class,
            "data_hex": self.data.hex(),
            "data_text_latin1": self.data_text,
            # Framed message bytes are already represented once in
            # request_framing/response_framing and linked by frame_id.
            "raw_hex": self.raw.hex() if self.frame_id is None else None,
            "fields": self.fields,
        }


def _line_to_dict(line: DocumentLine) -> dict[str, object]:
    return {
        "text": line.text,
        "align": line.align,
        "bold": line.bold,
        "double_width": line.double_width,
        "double_height": line.double_height,
        "source": {
            "stream_offset": line.trace.source_offset,
            "frame_id": line.trace.source_frame,
            "xml_path": line.trace.source_xml_path,
            "evidence": line.trace.evidence,
        },
    }


@dataclass(frozen=True, slots=True)
class ParsedReceipt:
    document_id: str
    document_type: str
    evidence: str
    complete: bool
    model: DocumentModel
    frame_ids: tuple[int, ...]
    start_offset: int
    end_offset: int
    issues: tuple[ReceiptIssue, ...] = ()

    @property
    def receipt_text(self) -> str:
        return render_clean_text(self.model)

    @property
    def text(self) -> str:
        return self.receipt_text

    @property
    def printed_class(self) -> str | None:
        value = self.model.metadata.get("printed_class")
        return str(value) if value is not None else self.model.document_type

    @property
    def parsed_dict(self) -> dict[str, object]:
        return receipt_to_dict(self)

    def to_dict(self) -> dict[str, object]:
        return receipt_to_dict(self)


@dataclass(frozen=True, slots=True)
class RequestResponseCorrelation:
    """Ordinal request/response association supported by the observed sequence relation."""

    request_frame_id: int
    request_stream_offset: int
    request_sequence: str
    ack_event_id: int | None
    ack_stream_offset: int | None
    response_frame_id: int | None
    response_stream_offset: int | None
    expected_response_sequence: str | None
    observed_response_sequence: str | None
    sequence_matches: bool | None
    evidence: str = INFERRED

    def to_dict(self) -> dict[str, object]:
        return {
            "request": {
                "frame_id": self.request_frame_id,
                "stream_offset": self.request_stream_offset,
                "sequence": self.request_sequence,
            },
            "ack": {
                "event_id": self.ack_event_id,
                "stream_offset": self.ack_stream_offset,
                "observed": self.ack_event_id is not None,
            },
            "response": {
                "frame_id": self.response_frame_id,
                "stream_offset": self.response_stream_offset,
                "sequence": self.observed_response_sequence,
            },
            "expected_response_sequence": self.expected_response_sequence,
            "sequence_matches": self.sequence_matches,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class ProtocolCopiesResult:
    request_framing: FramingResult
    response_framing: FramingResult
    documents: tuple[ParsedReceipt, ...]
    messages: tuple[ProtocolMessage, ...]
    correlations: tuple[RequestResponseCorrelation, ...]
    issues: tuple[ReceiptIssue, ...]

    @property
    def receipt_texts(self) -> tuple[str, ...]:
        return tuple(document.receipt_text for document in self.documents)

    @property
    def parsed_documents(self) -> tuple[dict[str, object], ...]:
        return tuple(document.parsed_dict for document in self.documents)

    def to_dict(self) -> dict[str, object]:
        return {
            "documents": [document.to_dict() for document in self.documents],
            "messages": [message.to_dict() for message in self.messages],
            "correlations": [correlation.to_dict() for correlation in self.correlations],
            "issues": [issue.to_dict() for issue in self.issues],
            "request_framing": self.request_framing.to_dict(),
            "response_framing": self.response_framing.to_dict(),
            "evidence_policy": {
                "framing_and_literal_payload": CONFIRMED,
                "command_semantics": INFERRED,
                "unobserved_fields": UNKNOWN,
            },
        }


def receipt_to_text(document: ParsedReceipt) -> str:
    return document.receipt_text


def receipt_to_dict(document: ParsedReceipt) -> dict[str, object]:
    model = document.model
    return {
        "document_id": document.document_id,
        "document_type": document.document_type,
        "printed_class": document.printed_class,
        "evidence": document.evidence,
        "complete": document.complete,
        "source": {
            "direction": "request",
            "frame_ids": list(document.frame_ids),
            "start_offset": document.start_offset,
            "end_offset": document.end_offset,
        },
        "receipt_text": document.receipt_text,
        "lines": [_line_to_dict(line) for line in [*model.header, *model.lines, *model.footer]],
        "parsed": {
            "items": model.items,
            "quantities": model.quantities,
            "descriptions": model.descriptions,
            "amounts": model.amounts,
            "taxes": model.taxes,
            "payments": model.payments,
            "totals": model.totals,
            "date": model.date,
            "time": model.time,
            "document_number": model.document_number,
            "fiscal_fields": model.fiscal_fields,
            "metadata": model.metadata,
        },
        "issues": [issue.to_dict() for issue in document.issues],
    }


@dataclass(slots=True)
class _ReceiptBuilder:
    kind: str
    start_frame: RCHFrame
    model: DocumentModel
    frames: list[RCHFrame] = field(default_factory=list)
    issues: list[ReceiptIssue] = field(default_factory=list)
    seen_primary_total: bool = False
    state: DocumentAssemblyState = DocumentAssemblyState.IDLE
    state_transitions: list[dict[str, object]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.frames:
            self.frames.append(self.start_frame)

    def add_frame(self, frame: RCHFrame) -> None:
        if not self.frames or self.frames[-1].frame_id != frame.frame_id:
            self.frames.append(frame)


def _new_builder(kind: str, frame: RCHFrame) -> _ReceiptBuilder:
    canonical_type = {
        "documento_commerciale": "commerciale",
        "documento_gestionale": "gestionale",
    }[kind]
    builder = _ReceiptBuilder(
        kind=kind,
        start_frame=frame,
        model=DocumentModel(
            document_type=kind,
            observed_variant=None,
            metadata={
                "framing_evidence": CONFIRMED,
                "literal_payload_evidence": CONFIRMED,
                "command_semantics_evidence": INFERRED,
                "unobserved_fields": None,
                "legal_or_fiscal_status": UNKNOWN,
                "encoding": "latin-1_lossless_byte_view",
                "canonical_type": canonical_type,
                "printed_class": kind,
            },
        ),
    )
    target = (
        DocumentAssemblyState.COMMERCIAL_BODY
        if kind == "documento_commerciale"
        else DocumentAssemblyState.MANAGEMENT_BODY
    )
    _transition(builder, target, frame)
    return builder


def _transition(builder: _ReceiptBuilder, target: DocumentAssemblyState, frame: RCHFrame) -> None:
    if builder.state == target:
        return
    builder.state_transitions.append(
        {
            "from": builder.state.value,
            "to": target.value,
            "frame_id": frame.frame_id,
            "stream_offset": frame.stream_offset,
            "evidence": INFERRED,
        }
    )
    builder.state = target


def _finish_builder(builder: _ReceiptBuilder, document_number: int, *, complete: bool) -> ParsedReceipt:
    if not complete:
        issue = ReceiptIssue(
            code="incomplete_document",
            detail="capture ended before the inferred closing command",
            direction="request",
            stream_offset=builder.frames[-1].end_offset,
            frame_id=builder.frames[-1].frame_id,
            evidence=INFERRED,
        )
        builder.issues.append(issue)
    _transition(
        builder,
        DocumentAssemblyState.COMPLETE if complete else DocumentAssemblyState.INCOMPLETE,
        builder.frames[-1],
    )
    builder.model.metadata["complete"] = complete
    builder.model.metadata["document_state_transitions"] = builder.state_transitions
    builder.model.metadata["final_document_state"] = builder.state.value
    builder.model.metadata["source_frame_ids"] = [frame.frame_id for frame in builder.frames]
    last = builder.frames[-1]
    return ParsedReceipt(
        document_id=f"document-{document_number:04d}",
        document_type=str(builder.model.metadata["canonical_type"]),
        evidence=INFERRED,
        complete=complete,
        model=builder.model,
        frame_ids=tuple(frame.frame_id for frame in builder.frames),
        start_offset=builder.start_frame.stream_offset,
        end_offset=last.end_offset,
        issues=tuple(builder.issues),
    )


def _amount_fields(
    line: str,
    frame: RCHFrame,
    semantic_budget: _SemanticBudget,
) -> list[dict[str, object]]:
    amounts: list[dict[str, object]] = []
    for match in _PRINTED_AMOUNT_RE.finditer(line):
        if semantic_budget.used >= semantic_budget.limit:
            semantic_budget.reserve(1, frame)
            break
        cents = parse_printed_amount(match.group("amount"))
        if cents is not None and semantic_budget.reserve(1, frame):
            amounts.append(
                {
                    "raw": match.group("amount"),
                    "cents": cents,
                    "source": _source(frame, evidence=INFERRED),
                }
            )
    return amounts


def _apply_management_line(
    builder: _ReceiptBuilder,
    frame: RCHFrame,
    text: str,
    style: str | None,
    semantic_budget: _SemanticBudget,
) -> None:
    model = builder.model
    inferred_style = style == "2"
    if semantic_budget.reserve(1, frame):
        model.lines.append(
            DocumentLine(
                text=text,
                trace=_trace(frame, evidence=INFERRED),
                bold=inferred_style,
                double_width=inferred_style,
                double_height=inferred_style,
            )
        )
    amounts = _amount_fields(text, frame, semantic_budget)
    model.amounts.extend(amounts)

    stripped = text.strip()
    if stripped.upper() == "EURO":
        model.metadata["observed_currency_label"] = "EURO"

    order_match = _ORDER_RE.match(stripped)
    if order_match:
        model.metadata["order_text"] = stripped
        model.metadata["order_value"] = order_match.group("value") or None
        model.metadata["order_source"] = _source(frame, evidence=INFERRED)

    reference_match = _REFERENCE_RE.search(stripped)
    if reference_match:
        model.date = reference_match.group("date")
        model.time = reference_match.group("time")
        model.document_number = reference_match.group("number")
        model.metadata["printed_reference_source"] = _source(frame, evidence=INFERRED)

    upper = stripped.upper()
    if upper.startswith("RESTO") and amounts:
        model.metadata["change"] = amounts[-1]
        return
    if upper.startswith("CONTANTI") and amounts:
        if semantic_budget.reserve(1, frame):
            model.payments.append(
                {
                    "method_text": stripped.split(maxsplit=1)[0],
                    "amount_cents": amounts[-1]["cents"],
                    "amount_raw": amounts[-1]["raw"],
                    "amount": amounts[-1],
                    "source": _source(frame, evidence=INFERRED),
                }
            )
        return
    if upper.startswith("TOT") and amounts:
        if semantic_budget.reserve(1, frame):
            model.totals.append(
                {
                    "label": stripped[:3],
                    "amount_cents": amounts[-1]["cents"] if len(amounts) == 1 else None,
                    "amounts": amounts,
                    "source": _source(frame, evidence=INFERRED),
                }
            )
        builder.seen_primary_total = True
        return
    if "%" in stripped and len(amounts) >= 2:
        if semantic_budget.reserve(1, frame):
            model.taxes.append(
                {
                    "raw_text": stripped,
                    "taxable_amount_cents": amounts[-2]["cents"],
                    "tax_amount_cents": amounts[-1]["cents"],
                    "taxable_amount": amounts[-2],
                    "tax_amount": amounts[-1],
                    "source": _source(frame, evidence=INFERRED),
                }
            )
        return

    item_match = _PRINTED_ITEM_RE.match(stripped)
    if item_match and not builder.seen_primary_total:
        cents = parse_printed_amount(item_match.group("amount"))
        description = item_match.group("description")
        if semantic_budget.reserve(2, frame):
            item = {
                "description": description,
                "amount_cents": cents,
                "amount_raw": item_match.group("amount"),
                "quantity": None,
                "tax_class": item_match.group("tax_class"),
                "source": _source(frame, evidence=INFERRED),
            }
            model.items.append(item)
            model.descriptions.append(description)


def _apply_commercial_item(
    builder: _ReceiptBuilder,
    frame: RCHFrame,
    match: re.Match[str],
    semantic_budget: _SemanticBudget,
) -> dict[str, object] | None:
    amount_cents = int(match.group("amount"))
    quantity_text = match.group("quantity")
    quantity = int(quantity_text) if quantity_text is not None else None
    description = match.group("description")
    field_count = 4 + (1 if quantity is not None else 0)
    if not semantic_budget.reserve(field_count, frame):
        return None
    source = _source(frame, evidence=INFERRED)
    item = {
        "description": description,
        "amount_cents": amount_cents,
        "quantity": quantity,
        "command_code": match.group("code"),
        "source": source,
    }
    builder.model.items.append(item)
    builder.model.descriptions.append(description)
    builder.model.amounts.append({"cents": amount_cents, "raw": match.group("amount"), "source": source})
    if quantity is not None:
        builder.model.quantities.append(quantity)
    builder.model.lines.append(
        DocumentLine(
            f"{description} {_format_cents(amount_cents)}" if description else _format_cents(amount_cents),
            trace=_trace(frame, evidence=INFERRED),
        )
    )
    return item


def _apply_commercial_total(
    builder: _ReceiptBuilder,
    frame: RCHFrame,
    match: re.Match[str],
    semantic_budget: _SemanticBudget,
) -> dict[str, object] | None:
    amount_cents = int(match.group("amount"))
    total: dict[str, object] | None = None
    if semantic_budget.reserve(5, frame):
        total = {
            "amount_cents": amount_cents,
            "command_code": match.group("code"),
            "source": _source(frame, evidence=INFERRED),
        }
        builder.model.totals.append(total)
        builder.model.payments.append(
            {
                "method": None,
                "amount_cents": amount_cents,
                "source_code": f"T{match.group('code')}",
                "source": _source(frame, evidence=INFERRED),
            }
        )
        builder.model.amounts.append(
            {"cents": amount_cents, "raw": match.group("amount"), "source": _source(frame, evidence=INFERRED)}
        )
        builder.model.lines.append(
            DocumentLine(
                f"TOTALE {_format_cents(amount_cents)}",
                trace=_trace(frame, evidence=INFERRED),
                bold=True,
            )
        )
        builder.model.lines.append(
            DocumentLine(
                f"IMPORTO PAGAMENTO {_format_cents(amount_cents)}",
                trace=_trace(frame, evidence=INFERRED),
            )
        )
    builder.model.metadata["close_candidate_frame_id"] = frame.frame_id
    builder.model.metadata["close_candidate_evidence"] = INFERRED
    _transition(builder, DocumentAssemblyState.COMMERCIAL_PAYMENT, frame)
    return total


def _framing_issue(issue: FramingIssue, direction: str) -> ReceiptIssue:
    return ReceiptIssue(
        code=issue.code,
        detail=issue.detail,
        direction=direction,
        stream_offset=issue.stream_offset,
        raw=issue.raw,
        evidence=issue.evidence,
    )


def _request_role(data_text: str) -> tuple[str, dict[str, object]]:
    management = _MANAGEMENT_LINE_RE.match(data_text)
    if data_text == "=o":
        return "management_boundary", {}
    if management:
        return "management_printable_line", {"text": management.group("text"), "style": management.group("style")}
    commercial_text = _COMMERCIAL_TEXT_RE.match(data_text)
    if commercial_text:
        return "commercial_printable_text", {
            "text": commercial_text.group("text"),
            "style": commercial_text.group("style"),
        }
    item = _COMMERCIAL_ITEM_RE.match(data_text)
    if item:
        return "commercial_item", {
            "description": item.group("description"),
            "amount_cents": int(item.group("amount")),
            "quantity": int(item.group("quantity")) if item.group("quantity") is not None else None,
            "command_code": item.group("code"),
        }
    total = _COMMERCIAL_TOTAL_RE.match(data_text)
    if total:
        return "commercial_total", {
            "amount_cents": int(total.group("amount")),
            "command_code": total.group("code"),
        }
    display = _DISPLAY_RE.match(data_text)
    if display:
        return "auxiliary_display", {"display_line": int(display.group("line")), "text": display.group("text")}
    if data_text == "=K":
        return "commercial_start_candidate", {}
    if data_text.startswith("<</?"):
        return "commercial_control_candidate", {"command": data_text}
    return "unknown_request_command", {}


def _message_from_frame(message_id: int, direction: str, frame: RCHFrame) -> ProtocolMessage:
    data_text = frame.data_text
    if direction == "request":
        if frame.bcc_valid and frame.address == "00" and frame.frame_class == "z":
            role, fields = _request_role(data_text)
            evidence = INFERRED if role != "unknown_request_command" else UNKNOWN
        else:
            role = "unexpected_request_profile"
            fields = {}
            evidence = UNKNOWN
    else:
        expected_profile = frame.bcc_valid and frame.address == "01" and frame.frame_class == "N"
        counter = _RESPONSE_COUNTER_RE.match(data_text) if expected_profile else None
        if counter:
            role = "response_counter_candidate"
            fields = {"counter_raw": counter.group("counter"), "counter": int(counter.group("counter"))}
            evidence = INFERRED
        else:
            role = "response_frame" if expected_profile else "unexpected_response_profile"
            fields = {}
            evidence = UNKNOWN
    fields = {
        **fields,
        "aa": frame.aa,
        "address": frame.address,
        "sequence": frame.sequence,
        "bcc_valid": frame.bcc_valid,
        "framing_evidence": CONFIRMED,
    }
    return ProtocolMessage(
        message_id=message_id,
        direction=direction,
        kind="frame",
        role=role,
        evidence=evidence,
        stream_offset=frame.stream_offset,
        end_offset=frame.end_offset,
        frame_id=frame.frame_id,
        frame_class=frame.frame_class,
        data=frame.data,
        raw=frame.raw,
        fields=fields,
    )


def _message_from_ack(message_id: int, direction: str, ack: AckEvent) -> ProtocolMessage:
    return ProtocolMessage(
        message_id=message_id,
        direction=direction,
        kind="ack",
        role="standalone_ack",
        evidence=CONFIRMED,
        stream_offset=ack.stream_offset,
        end_offset=ack.end_offset,
        raw=ack.raw,
    )


def _parse_documents(
    request_framing: FramingResult,
    *,
    max_documents: int,
    semantic_budget: _SemanticBudget,
) -> tuple[list[ParsedReceipt], list[ReceiptIssue]]:
    documents: list[ParsedReceipt] = []
    issues: list[ReceiptIssue] = []
    active: _ReceiptBuilder | None = None
    pending_start: RCHFrame | None = None
    document_limit_reported = False

    def finish_active(*, complete: bool) -> None:
        nonlocal active, document_limit_reported
        if active is None:
            return
        if len(documents) < max_documents:
            document = _finish_builder(active, len(documents) + 1, complete=complete)
            documents.append(document)
            issues.extend(document.issues)
        elif not document_limit_reported:
            document_limit_reported = True
            issues.append(
                ReceiptIssue(
                    code="document_limit_exceeded",
                    detail=f"more than {max_documents} candidate documents observed; additional documents omitted",
                    direction="request",
                    stream_offset=active.start_frame.stream_offset,
                    frame_id=active.start_frame.frame_id,
                    evidence=CONFIRMED,
                )
            )
        active = None

    for frame in request_framing.frames:
        if (
            not frame.bcc_valid
            or frame.address != "00"
            or frame.frame_class != "z"
        ):
            continue
        data_text = frame.data_text

        if data_text.startswith("<</?"):
            if active is not None and active.kind == "documento_commerciale":
                active.add_frame(frame)
                # In the observed complete sequence the final control payload
                # is ``<</?7``; ``<</?s`` occurs both before and near the end
                # and is therefore not sufficient by itself to close a copy.
                if data_text == "<</?" or re.fullmatch(r"<</\?\d", data_text):
                    finish_active(complete=True)
                elif active.state == DocumentAssemblyState.COMMERCIAL_PAYMENT:
                    _transition(active, DocumentAssemblyState.COMMERCIAL_POSTLUDE, frame)
            else:
                pending_start = frame if data_text == "<</?s" else None
            continue

        if data_text == "=K":
            if active is not None:
                finish_active(complete=False)
            active = _new_builder("documento_commerciale", pending_start or frame)
            active.add_frame(frame)
            pending_start = None
            continue

        if data_text == "=o":
            if active is not None and active.kind == "documento_gestionale":
                active.add_frame(frame)
                finish_active(complete=True)
            else:
                if active is not None:
                    finish_active(complete=False)
                active = _new_builder("documento_gestionale", frame)
            pending_start = None
            continue

        management_line = _MANAGEMENT_LINE_RE.match(data_text)
        if management_line:
            if active is None:
                active = _new_builder("documento_gestionale", frame)
                active.issues.append(
                    ReceiptIssue(
                        code="missing_open_boundary",
                        detail="printable management line observed before an inferred =o opening boundary",
                        direction="request",
                        stream_offset=frame.stream_offset,
                        frame_id=frame.frame_id,
                        evidence=INFERRED,
                    )
                )
            elif active.kind != "documento_gestionale":
                finish_active(complete=False)
                active = _new_builder("documento_gestionale", frame)
            active.add_frame(frame)
            _apply_management_line(
                active,
                frame,
                management_line.group("text"),
                management_line.group("style"),
                semantic_budget,
            )
            continue

        commercial_item = _COMMERCIAL_ITEM_RE.match(data_text)
        if commercial_item:
            if active is None or active.kind != "documento_commerciale":
                if active is not None:
                    finish_active(complete=False)
                active = _new_builder("documento_commerciale", frame)
                active.issues.append(
                    ReceiptIssue(
                        code="missing_commercial_start",
                        detail="item command observed without a preceding inferred =K start command",
                        direction="request",
                        stream_offset=frame.stream_offset,
                        frame_id=frame.frame_id,
                        evidence=INFERRED,
                    )
                )
            active.add_frame(frame)
            _apply_commercial_item(active, frame, commercial_item, semantic_budget)
            continue

        commercial_text = _COMMERCIAL_TEXT_RE.match(data_text)
        if commercial_text and active is not None and active.kind == "documento_commerciale":
            active.add_frame(frame)
            literal_text = commercial_text.group("text")
            style_is_double = commercial_text.group("style") == "2"
            # The physical document correlation shows this command family as
            # hash-prefixed free text.  The hash is not present in DATA, so the
            # added prefix and style flags remain explicitly inferred.
            if semantic_budget.reserve(1, frame):
                active.model.lines.append(
                    DocumentLine(
                        f"#{literal_text}",
                        trace=_trace(frame, evidence=INFERRED),
                        bold=style_is_double,
                        double_width=style_is_double,
                        double_height=style_is_double,
                    )
                )
            order_match = _ORDER_RE.match(literal_text)
            if order_match:
                active.model.metadata["order_text"] = literal_text
                active.model.metadata["rendered_order_text"] = f"#{literal_text}"
                active.model.metadata["order_value"] = order_match.group("value") or None
                active.model.metadata["order_source"] = _source(frame, evidence=INFERRED)
            continue

        commercial_total = _COMMERCIAL_TOTAL_RE.match(data_text)
        if commercial_total:
            if active is None or active.kind != "documento_commerciale":
                if active is not None:
                    finish_active(complete=False)
                active = _new_builder("documento_commerciale", frame)
                active.issues.append(
                    ReceiptIssue(
                        code="missing_commercial_start",
                        detail="total command observed without a preceding inferred =K start command",
                        direction="request",
                        stream_offset=frame.stream_offset,
                        frame_id=frame.frame_id,
                        evidence=INFERRED,
                    )
                )
            active.add_frame(frame)
            _apply_commercial_total(active, frame, commercial_total, semantic_budget)
            continue

        # Display commands are capture-confirmed but auxiliary: they never
        # become receipt lines.  Other commands remain in ``messages`` only.
        if active is not None and not _DISPLAY_RE.match(data_text):
            active.add_frame(frame)

    finish_active(complete=False)
    return documents, issues


def _expected_response_sequence(request_sequence: str) -> str | None:
    if len(request_sequence) != 1 or not request_sequence.isdecimal():
        return None
    return str((int(request_sequence) + 8) % 10)


def _correlate_directions(
    request_framing: FramingResult,
    response_framing: FramingResult,
    *,
    max_issues: int,
) -> tuple[list[RequestResponseCorrelation], list[ReceiptIssue]]:
    """Associate frames by stream order, then independently test sequence evidence."""

    correlations: list[RequestResponseCorrelation] = []
    issues: list[ReceiptIssue] = []
    request_frames = request_framing.frames
    response_frames = response_framing.frames
    acknowledgements = response_framing.acks

    def add_issue(issue: ReceiptIssue) -> None:
        if len(issues) < max_issues:
            issues.append(issue)
    for index, request_frame in enumerate(request_frames):
        response_frame = response_frames[index] if index < len(response_frames) else None
        ack = acknowledgements[index] if index < len(acknowledgements) else None
        expected = _expected_response_sequence(request_frame.sequence)
        observed = response_frame.sequence if response_frame is not None else None
        sequence_matches = expected == observed if expected is not None and observed is not None else None
        correlations.append(
            RequestResponseCorrelation(
                request_frame_id=request_frame.frame_id,
                request_stream_offset=request_frame.stream_offset,
                request_sequence=request_frame.sequence,
                ack_event_id=ack.event_id if ack is not None else None,
                ack_stream_offset=ack.stream_offset if ack is not None else None,
                response_frame_id=response_frame.frame_id if response_frame is not None else None,
                response_stream_offset=response_frame.stream_offset if response_frame is not None else None,
                expected_response_sequence=expected,
                observed_response_sequence=observed,
                sequence_matches=sequence_matches,
            )
        )
        if ack is None:
            add_issue(
                ReceiptIssue(
                    code="missing_ack_candidate",
                    detail="no standalone ACK was available at the same ordinal position as this request",
                    direction="request_response",
                    stream_offset=request_frame.stream_offset,
                    frame_id=request_frame.frame_id,
                    evidence=INFERRED,
                )
            )
        if response_frame is None:
            add_issue(
                ReceiptIssue(
                    code="missing_response_frame_candidate",
                    detail="no response frame was available at the same ordinal position as this request",
                    direction="request_response",
                    stream_offset=request_frame.stream_offset,
                    frame_id=request_frame.frame_id,
                    evidence=INFERRED,
                )
            )
        elif sequence_matches is False:
            add_issue(
                ReceiptIssue(
                    code="response_sequence_mismatch",
                    detail=f"expected response sequence {expected}, observed {observed}",
                    direction="request_response",
                    stream_offset=response_frame.stream_offset,
                    frame_id=response_frame.frame_id,
                    evidence=INFERRED,
                )
            )

    for response_frame in response_frames[len(request_frames) :]:
        add_issue(
            ReceiptIssue(
                code="unmatched_response_frame",
                detail="response frame has no request frame at the same ordinal position",
                direction="response",
                stream_offset=response_frame.stream_offset,
                frame_id=response_frame.frame_id,
                evidence=INFERRED,
            )
        )
    for ack in acknowledgements[len(request_frames) :]:
        add_issue(
            ReceiptIssue(
                code="unmatched_ack",
                detail="standalone ACK has no request frame at the same ordinal position",
                direction="response",
                stream_offset=ack.stream_offset,
                evidence=INFERRED,
            )
        )
    return correlations, issues


def _attach_response_counters(
    documents: list[ParsedReceipt],
    correlations: list[RequestResponseCorrelation],
    request_framing: FramingResult,
    response_framing: FramingResult,
    semantic_budget: _SemanticBudget,
) -> None:
    request_by_id = {frame.frame_id: frame for frame in request_framing.frames}
    response_by_id = {frame.frame_id: frame for frame in response_framing.frames}
    correlation_by_request = {correlation.request_frame_id: correlation for correlation in correlations}
    for document in documents:
        if document.document_type != "commerciale" or not document.complete:
            continue
        candidates: list[tuple[RCHFrame, re.Match[str]]] = []
        payment_seen = False
        for request_frame_id in document.frame_ids:
            request_frame = request_by_id.get(request_frame_id)
            if (
                request_frame is None
                or not request_frame.bcc_valid
                or request_frame.address != "00"
                or request_frame.frame_class != "z"
            ):
                continue
            if _COMMERCIAL_TOTAL_RE.fullmatch(request_frame.data_text):
                payment_seen = True
                continue
            # The capture contains a counter query both before and after the
            # transaction.  Only the exact post-payment query can support the
            # printed suffix; falling back to the pre-document counter would
            # silently assign the previous receipt number.
            if not payment_seen or request_frame.data != b"<</?s":
                continue
            correlation = correlation_by_request.get(request_frame_id)
            if (
                correlation is None
                or correlation.response_frame_id is None
                or correlation.sequence_matches is not True
            ):
                continue
            response_frame = response_by_id.get(correlation.response_frame_id)
            if (
                response_frame is None
                or not response_frame.bcc_valid
                or response_frame.address != "01"
                or response_frame.frame_class != "N"
            ):
                continue
            match = _RESPONSE_COUNTER_RE.match(response_frame.data_text)
            if match:
                candidates.append((response_frame, match))
        if not candidates:
            continue
        response_frame, match = candidates[-1]
        if not semantic_budget.reserve(4, response_frame, direction="response"):
            continue
        suffix = match.group("counter")
        document.model.document_number = suffix
        document.model.fiscal_fields["response_counter_suffix"] = suffix
        document.model.metadata["document_number_scope"] = "suffix_only"
        document.model.metadata["document_number_prefix"] = None
        document.model.metadata["document_number_evidence"] = INFERRED
        document.model.metadata["document_number_source"] = {
            "direction": "response",
            "frame_id": response_frame.frame_id,
            "stream_offset": response_frame.stream_offset,
            "end_offset": response_frame.end_offset,
            "evidence": INFERRED,
        }
        document.model.footer.extend(
            (
                DocumentLine("", trace=_trace(response_frame, evidence=INFERRED)),
                DocumentLine(
                    f"DOCUMENTO N. (solo suffisso) {suffix}",
                    trace=_trace(response_frame, evidence=INFERRED),
                ),
            )
        )


def _bounded_result_issues(issues: list[ReceiptIssue], max_issues: int) -> tuple[ReceiptIssue, ...]:
    if len(issues) <= max_issues:
        return tuple(issues)
    capacity = max_issues - 1
    # Limit crossings explain why a semantic result is partial and must not be
    # hidden merely because ordinary missing-response diagnostics arrived
    # first.  Reserve bounded slots for each such issue, then fill remaining
    # capacity in original order.
    selected_indexes = [
        index for index, issue in enumerate(issues) if issue.code.endswith("_limit_exceeded")
    ][:capacity]
    selected = set(selected_indexes)
    for index in range(len(issues)):
        if len(selected_indexes) >= capacity:
            break
        if index not in selected:
            selected_indexes.append(index)
            selected.add(index)
    retained = [issues[index] for index in sorted(selected_indexes)]
    retained.append(
        ReceiptIssue(
            code="result_issue_limit_exceeded",
            detail=f"{len(issues) - len(retained)} additional parser issue(s) omitted",
            evidence=CONFIRMED,
        )
    )
    return tuple(retained)


def _parse_framed_copies(
    request_framing: FramingResult,
    response_framing: FramingResult,
    *,
    max_documents: int,
    max_messages: int,
    max_issues: int,
    max_semantic_fields: int,
    initial_issues: Iterable[ReceiptIssue] = (),
) -> ProtocolCopiesResult:
    issues = list(initial_issues)
    issues.extend(_framing_issue(issue, "request") for issue in request_framing.issues)
    issues.extend(_framing_issue(issue, "response") for issue in response_framing.issues)
    semantic_budget = _SemanticBudget(max_semantic_fields)
    documents, document_issues = _parse_documents(
        request_framing,
        max_documents=max_documents,
        semantic_budget=semantic_budget,
    )
    issues.extend(document_issues)
    correlations, correlation_issues = _correlate_directions(
        request_framing,
        response_framing,
        max_issues=max_issues,
    )
    issues.extend(correlation_issues)
    _attach_response_counters(
        documents,
        correlations,
        request_framing,
        response_framing,
        semantic_budget,
    )
    if semantic_budget.issue is not None:
        issues.append(semantic_budget.issue)

    messages: list[ProtocolMessage] = []
    message_limit_reported = False
    for direction, framing in (("request", request_framing), ("response", response_framing)):
        for event in framing.events:
            if len(messages) >= max_messages:
                if not message_limit_reported:
                    message_limit_reported = True
                    issues.append(
                        ReceiptIssue(
                            code="message_limit_exceeded",
                            detail=f"more than {max_messages} protocol messages observed; additional messages omitted",
                            direction=direction,
                            stream_offset=event.stream_offset,
                            evidence=CONFIRMED,
                        )
                    )
                continue
            message_id = len(messages) + 1
            if isinstance(event, RCHFrame):
                messages.append(_message_from_frame(message_id, direction, event))
            else:
                messages.append(_message_from_ack(message_id, direction, event))

    return ProtocolCopiesResult(
        request_framing=request_framing,
        response_framing=response_framing,
        documents=tuple(documents),
        messages=tuple(messages),
        correlations=tuple(correlations),
        issues=_bounded_result_issues(issues, max_issues),
    )


def parse_protocol_copies(
    request: bytes,
    response: bytes,
    *,
    max_data_length: int = 999,
    max_buffer_bytes: int = 4096,
    max_events: int = _DEFAULT_MAX_EVENTS,
    max_documents: int = _DEFAULT_MAX_DOCUMENTS,
    max_messages: int = _DEFAULT_MAX_MESSAGES,
    max_issues: int = _DEFAULT_MAX_RESULT_ISSUES,
    max_analyzed_bytes: int = _DEFAULT_MAX_ANALYZED_BYTES,
    max_semantic_fields: int = _DEFAULT_MAX_SEMANTIC_FIELDS,
) -> ProtocolCopiesResult:
    """Frame and reconstruct copies without ever modifying inline traffic."""

    if max_documents < 1 or max_messages < 1 or max_analyzed_bytes < 1 or max_semantic_fields < 1:
        raise ValueError(
            "max_documents, max_messages, max_analyzed_bytes and max_semantic_fields must be positive"
        )
    initial_issues: list[ReceiptIssue] = []
    analyzed_request = request[:max_analyzed_bytes]
    analyzed_response = response[:max_analyzed_bytes]
    for direction, original, analyzed in (
        ("request", request, analyzed_request),
        ("response", response, analyzed_response),
    ):
        if len(original) != len(analyzed):
            initial_issues.append(
                ReceiptIssue(
                    code="analysis_byte_limit_exceeded",
                    detail=(
                        f"{direction} contains {len(original)} bytes; semantic analysis was limited "
                        f"to the first {max_analyzed_bytes}; authoritative RAW is unchanged"
                    ),
                    direction=direction,
                    stream_offset=max_analyzed_bytes,
                    evidence=CONFIRMED,
                )
            )

    request_framing = frame_stream(
        analyzed_request,
        max_data_length=max_data_length,
        max_buffer_bytes=max_buffer_bytes,
        max_events=max_events,
        max_issues=max_issues,
    )
    response_framing = frame_stream(
        analyzed_response,
        max_data_length=max_data_length,
        max_buffer_bytes=max_buffer_bytes,
        max_events=max_events,
        max_issues=max_issues,
    )
    return _parse_framed_copies(
        request_framing,
        response_framing,
        max_documents=max_documents,
        max_messages=max_messages,
        max_issues=max_issues,
        max_semantic_fields=max_semantic_fields,
        initial_issues=initial_issues,
    )


def parse_protocol_chunks(
    request_chunks: Iterable[bytes],
    response_chunks: Iterable[bytes],
    **limits: int,
) -> ProtocolCopiesResult:
    """Parse arbitrary receive segmentation without joining chunks first."""

    max_data_length = limits.pop("max_data_length", 999)
    max_buffer_bytes = limits.pop("max_buffer_bytes", 4096)
    max_events = limits.pop("max_events", _DEFAULT_MAX_EVENTS)
    max_documents = limits.pop("max_documents", _DEFAULT_MAX_DOCUMENTS)
    max_messages = limits.pop("max_messages", _DEFAULT_MAX_MESSAGES)
    max_issues = limits.pop("max_issues", _DEFAULT_MAX_RESULT_ISSUES)
    max_analyzed_bytes = limits.pop("max_analyzed_bytes", _DEFAULT_MAX_ANALYZED_BYTES)
    max_semantic_fields = limits.pop("max_semantic_fields", _DEFAULT_MAX_SEMANTIC_FIELDS)
    if limits:
        raise TypeError(f"unexpected parser limit(s): {', '.join(sorted(limits))}")
    request_framer = RCHStreamFramer(
        max_data_length=max_data_length,
        max_buffer_bytes=max_buffer_bytes,
        max_events=max_events,
        max_issues=max_issues,
    )
    response_framer = RCHStreamFramer(
        max_data_length=max_data_length,
        max_buffer_bytes=max_buffer_bytes,
        max_events=max_events,
        max_issues=max_issues,
    )
    initial_issues: list[ReceiptIssue] = []

    def feed_bounded(chunks: Iterable[bytes], framer: RCHStreamFramer, direction: str) -> None:
        seen = 0
        omitted = 0
        for chunk in chunks:
            value = bytes(chunk)
            remaining = max(0, max_analyzed_bytes - seen)
            if remaining:
                accepted = value[:remaining]
                framer.feed(accepted)
                seen += len(accepted)
            omitted += len(value) - min(len(value), remaining)
        if omitted:
            initial_issues.append(
                ReceiptIssue(
                    code="analysis_byte_limit_exceeded",
                    detail=(
                        f"{direction} exceeded the {max_analyzed_bytes}-byte semantic analysis limit; "
                        f"{omitted} byte(s) were not parsed"
                    ),
                    direction=direction,
                    stream_offset=max_analyzed_bytes,
                    evidence=CONFIRMED,
                )
            )

    if max_documents < 1 or max_messages < 1 or max_analyzed_bytes < 1 or max_semantic_fields < 1:
        raise ValueError(
            "max_documents, max_messages, max_analyzed_bytes and max_semantic_fields must be positive"
        )
    feed_bounded(request_chunks, request_framer, "request")
    feed_bounded(response_chunks, response_framer, "response")
    return _parse_framed_copies(
        request_framer.finish(),
        response_framer.finish(),
        max_documents=max_documents,
        max_messages=max_messages,
        max_issues=max_issues,
        max_semantic_fields=max_semantic_fields,
        initial_issues=initial_issues,
    )


def parsed_result_dict(result: ProtocolCopiesResult) -> dict[str, object]:
    """Explicit JSON-ready helper for CLI/storage integrations."""

    return result.to_dict()


# A descriptive alias useful to integrations which call this a forensic parse.
ProtocolParseResult = ProtocolCopiesResult
