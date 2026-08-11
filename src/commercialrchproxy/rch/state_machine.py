"""Transport/session states, distinct from unconfirmed fiscal success."""

from __future__ import annotations

from enum import StrEnum


class SessionState(StrEnum):
    ACCEPTED = "accepted"
    CONNECTING_PRINTER = "connecting_printer"
    FORWARDING = "forwarding"
    DRAINING_RESPONSE = "draining_response"
    CLOSED = "closed"
    PRINTER_UNREACHABLE = "printer_unreachable"
    TRANSPORT_ERROR = "transport_error"


TERMINAL_STATES = {SessionState.CLOSED, SessionState.PRINTER_UNREACHABLE, SessionState.TRANSPORT_ERROR}
