"""Secure, non-inline inspection of a generic XML candidate.

Nothing in this module establishes the RCH XML v.7 wire envelope or validates
an RCH schema.  It only finds a bounded candidate and asks a hardened generic
XML parser whether that candidate is well formed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from defusedxml import ElementTree as SafeET

_FORBIDDEN = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_STRIP = b"\x00\t\r\n "
MAX_XML_ANALYSIS_BYTES = 4 * 1024 * 1024
MAX_XML_NODES = 10_000
MAX_XML_DEPTH = 128
MAX_XML_FIELD_CHARS = 4096


@dataclass(frozen=True, slots=True)
class XMLField:
    qname_path: str
    value: str


@dataclass(frozen=True, slots=True)
class XMLAnalysis:
    candidate_found: bool
    well_formed_generic: bool
    xml7_confirmed: bool
    candidate_start: int | None = None
    candidate_end: int | None = None
    root_qname: str | None = None
    root_local_name: str | None = None
    pretty_reserialized: str | None = None
    error: str | None = None
    evidence: str = "UNCONFIRMED"
    fields: tuple[XMLField, ...] = ()


def _candidate(payload: bytes) -> tuple[bytes, int, int] | None:
    left_trimmed = payload.lstrip(_STRIP)
    left = len(payload) - len(left_trimmed)
    right_trimmed = payload.rstrip(_STRIP)
    right = len(right_trimmed)
    if left < right and payload[left:right].startswith(b"<") and payload[left:right].endswith(b">"):
        return payload[left:right], left, right
    start = payload.find(b"<?xml")
    if start < 0:
        start = payload.find(b"<")
    end_marker = payload.rfind(b">")
    if start >= 0 and end_marker > start:
        end = end_marker + 1
        return payload[start:end], start, end
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _tree_within_limits(root: Any) -> tuple[bool, str | None]:
    stack: list[tuple[Any, int]] = [(root, 1)]
    nodes = 0
    while stack:
        element, depth = stack.pop()
        nodes += 1
        if nodes > MAX_XML_NODES:
            return False, f"xml_node_limit_exceeded:{MAX_XML_NODES}"
        if depth > MAX_XML_DEPTH:
            return False, f"xml_depth_limit_exceeded:{MAX_XML_DEPTH}"
        stack.extend((child, depth + 1) for child in list(element))
    return True, None


def _fields(element: Any, path: str = "", remaining: list[int] | None = None) -> list[XMLField]:
    if remaining is None:
        remaining = [MAX_XML_NODES]
    if remaining[0] <= 0:
        return []
    qname = str(element.tag)
    current = f"{path}/{qname}"
    children = list(element)
    result: list[XMLField] = []
    text = (element.text or "").strip()
    if text and not children:
        result.append(XMLField(current, text[:MAX_XML_FIELD_CHARS]))
        remaining[0] -= 1
    for child in children:
        if remaining[0] <= 0:
            break
        result.extend(_fields(child, current, remaining))
    return result


def _indent(element: Any, level: int = 0) -> None:
    """Indent a defused, already parsed tree without invoking another parser."""
    children = list(element)
    prefix = "\n" + "  " * level
    if children:
        if not element.text or not element.text.strip():
            element.text = prefix + "  "
        for child in children:
            _indent(child, level + 1)
        if not children[-1].tail or not children[-1].tail.strip():
            children[-1].tail = prefix
    if level and (not element.tail or not element.tail.strip()):
        element.tail = prefix


def analyze_xml_copy(payload: bytes) -> XMLAnalysis:
    if len(payload) > MAX_XML_ANALYSIS_BYTES:
        marker_found = b"<" in payload[:MAX_XML_ANALYSIS_BYTES]
        return XMLAnalysis(
            candidate_found=marker_found,
            well_formed_generic=False,
            xml7_confirmed=False,
            error=f"xml_analysis_limit_exceeded:{MAX_XML_ANALYSIS_BYTES}",
            evidence="INFERRED" if marker_found else "UNCONFIRMED",
        )
    candidate_data = _candidate(payload)
    if candidate_data is None:
        return XMLAnalysis(candidate_found=False, well_formed_generic=False, xml7_confirmed=False)
    candidate, start, end = candidate_data
    if _FORBIDDEN.search(candidate):
        return XMLAnalysis(
            candidate_found=True,
            well_formed_generic=False,
            xml7_confirmed=False,
            candidate_start=start,
            candidate_end=end,
            error="DTD_or_entity_declaration_rejected",
            evidence="OBSERVED",
        )
    try:
        root = SafeET.fromstring(candidate)
    except Exception as exc:  # defusedxml intentionally raises several types
        return XMLAnalysis(
            candidate_found=True,
            well_formed_generic=False,
            xml7_confirmed=False,
            candidate_start=start,
            candidate_end=end,
            error=f"{type(exc).__name__}: {exc}",
            evidence="OBSERVED",
        )
    within_limits, limit_error = _tree_within_limits(root)
    root_qname = str(root.tag)
    if not within_limits:
        return XMLAnalysis(
            candidate_found=True,
            well_formed_generic=True,
            xml7_confirmed=False,
            candidate_start=start,
            candidate_end=end,
            root_qname=root_qname,
            root_local_name=_local_name(root_qname),
            error=limit_error,
            evidence="OBSERVED",
        )
    try:
        _indent(root)
        pretty = SafeET.tostring(root, encoding="unicode")
    except Exception:
        pretty = None
    return XMLAnalysis(
        candidate_found=True,
        well_formed_generic=True,
        xml7_confirmed=False,
        candidate_start=start,
        candidate_end=end,
        root_qname=root_qname,
        root_local_name=_local_name(root_qname),
        pretty_reserialized=pretty,
        evidence="OBSERVED",
        fields=tuple(_fields(root)),
    )
