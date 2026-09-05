"""Removable governance-evidence instrumentation for the restaurant agent.

Activated only when the GOVERNANCE_EVIDENCE=1 environment variable is set at
startup (see bootstrap.init_governance). Passive: attaches a LangChain
callback handler through the invocation config and writes privacy-safe JSONL
events under artifacts/governance/. Never captures raw prompts or responses.
"""

from .client import GovernanceClient
from .core import EventBuilder, SessionTracker, fingerprint, sanitize, utc_now, validate_event
from .discovery import discover_tools, write_tool_discovery
from .sinks import HttpSink, JsonlSink
from .writer import EvidenceApiSink, GovernanceEventWriter

try:
    from .callback import GovernanceCallback
except ModuleNotFoundError as exc:
    if exc.name != "langchain_core":
        raise
    _callback_import_error = exc

    class GovernanceCallback:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise ImportError("GovernanceCallback requires langchain-core") from _callback_import_error

__all__ = [
    "EventBuilder",
    "EvidenceApiSink",
    "GovernanceClient",
    "GovernanceCallback",
    "GovernanceEventWriter",
    "HttpSink",
    "JsonlSink",
    "SessionTracker",
    "discover_tools",
    "fingerprint",
    "sanitize",
    "utc_now",
    "validate_event",
    "write_tool_discovery",
]
