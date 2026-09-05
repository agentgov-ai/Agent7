from __future__ import annotations

from typing import Any

from .session import SessionTracker


class EventBuilder:
    """Build governance event dictionaries without writing them."""

    def __init__(
        self,
        *,
        system_id: str,
        deployment_id: str,
        environment: str,
        agent_id: str,
        source: dict[str, Any],
        tracker: SessionTracker,
    ) -> None:
        self.system_id = system_id
        self.deployment_id = deployment_id
        self.environment = environment
        self.agent_id = agent_id
        self.source = source
        self.tracker = tracker

    def build(
        self,
        *,
        event_type: str,
        run_id: Any,
        parent_run_id: Any | None,
        status: str,
        component_kind: str,
        component_name: str | None,
        duration_ms: float | None = None,
        **details: Any,
    ) -> dict[str, Any]:
        final = event_type.endswith(("_end", "_error"))
        trace_id, span_id, parent_span_id = self.tracker.ids(run_id, parent_run_id, final=final)
        callback_context = details.pop("_callback_context", None) or {}
        session_id = self.tracker.session_id(run_id, parent_run_id, callback_context, final=final)
        outcome = {"status": status, "duration_ms": duration_ms}
        outcome.update(details.pop("outcome", None) or {})
        return {
            "system_id": self.system_id,
            "deployment_id": self.deployment_id,
            "environment": self.environment,
            "session_id": session_id,
            "event_type": event_type,
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "source": dict(self.source),
            "actor": {"agent_id": self.agent_id, "identity_type": "logical_agent"},
            "component": {"kind": component_kind, "name": component_name, "version": None},
            "outcome": outcome,
            **details,
        }
