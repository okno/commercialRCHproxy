"""RCH framing gate.

The authentication-gated packet definition and a real packet capture are not currently
available.  Consequently this release deliberately exposes no RCH frame
decoder.  A TCP recv() chunk is never mislabeled as an application frame.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FramingAssessment:
    confirmed: bool = False
    frame_count: int | None = None
    evidence: str = "UNCONFIRMED"
    reason: str = "RCH packet fields require authenticated documentation or observed capture"


def assess_framing(_payload: bytes) -> FramingAssessment:
    return FramingAssessment()
