from __future__ import annotations

from ai_governance.core import fingerprint, sanitize, utc_now
from ai_governance.sinks.http import HttpSink
from ai_governance.sinks.jsonl import JsonlSink

EvidenceApiSink = HttpSink
GovernanceEventWriter = JsonlSink

__all__ = [
    "EvidenceApiSink",
    "GovernanceEventWriter",
    "fingerprint",
    "sanitize",
    "utc_now",
]
