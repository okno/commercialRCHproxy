"""Response preservation with deliberately disabled semantic guessing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResponseAnalysis:
    protocol_status: str | None
    printer_status: str | None
    application_success: bool | None
    error_code: str | None
    error_description: str | None
    evidence: str


def analyze_response(_payload: bytes) -> ResponseAnalysis:
    return ResponseAnalysis(
        protocol_status=None,
        printer_status=None,
        application_success=None,
        error_code=None,
        error_description=None,
        evidence="UNCONFIRMED",
    )
