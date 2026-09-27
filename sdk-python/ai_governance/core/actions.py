"""Action request and action record models for pre-execution enforcement."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from .fingerprint import fingerprint
from .sanitize import utc_now

# Enforcement modes
MODE_OBSERVE = "observe"
MODE_SHADOW = "shadow"
MODE_ENFORCE = "enforce"

ENFORCEMENT_MODES = frozenset({MODE_OBSERVE, MODE_SHADOW, MODE_ENFORCE})
DEFAULT_ENFORCEMENT_MODE = MODE_OBSERVE

# Execution statuses recorded on an ActionRecord
EXECUTION_ALLOWED_EXECUTED = "allowed_executed"
EXECUTION_DENIED_BLOCKED = "denied_blocked"
EXECUTION_APPROVAL_REQUIRED_BLOCKED = "approval_required_blocked"
EXECUTION_SHADOW_ALLOWED = "shadow_allowed"
EXECUTION_OBSERVE_ONLY = "observe_only"
EXECUTION_ERROR = "error"

EXECUTION_STATUSES = frozenset(
    {
        EXECUTION_ALLOWED_EXECUTED,
        EXECUTION_DENIED_BLOCKED,
        EXECUTION_APPROVAL_REQUIRED_BLOCKED,
        EXECUTION_SHADOW_ALLOWED,
        EXECUTION_OBSERVE_ONLY,
        EXECUTION_ERROR,
    }
)


def new_action_id() -> str:
    return f"ACT-{uuid.uuid4().hex[:16]}"


def new_record_id() -> str:
    return f"REC-{uuid.uuid4().hex[:16]}"


def argument_metadata(arguments: dict[str, Any]) -> dict[str, Any]:
    """Derive privacy-safe metadata from raw call arguments.

    Returns argument *names*, *type names* and coarse counts only. Argument
    values never appear in the result, so this is safe to persist and to send
    to a decision backend.
    """
    names = sorted(str(key) for key in arguments)
    types = {str(key): type(value).__name__ for key, value in arguments.items()}
    return {
        "argument_names": names,
        "argument_types": types,
        "argument_count": len(names),
        "has_str_args": any(isinstance(value, str) for value in arguments.values()),
    }


@dataclass(frozen=True)
class ActionRequest:
    """One consequential action, described before it is allowed to execute."""

    action_id: str
    system_id: str
    deployment_id: str
    environment: str
    agent_id: str
    capability_name: str
    enforcement_mode: str
    capability_id: str | None = None
    capability_status: str | None = None
    module_path: str | None = None
    action_type: str | None = None
    data_classes: list[str] = field(default_factory=list)
    external_side_effect: bool | None = None
    approval_required: bool | None = None
    arguments_hash: str | None = None
    argument_names: list[str] = field(default_factory=list)
    argument_types: dict[str, str] = field(default_factory=dict)
    argument_features: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    trace_id: str | None = None
    parent_span_id: str | None = None
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "system_id": self.system_id,
            "deployment_id": self.deployment_id,
            "environment": self.environment,
            "agent_id": self.agent_id,
            "capability_id": self.capability_id,
            "capability_name": self.capability_name,
            "capability_status": self.capability_status,
            "module_path": self.module_path,
            "action_type": self.action_type,
            "data_classes": list(self.data_classes),
            "external_side_effect": self.external_side_effect,
            "approval_required": self.approval_required,
            "arguments_hash": self.arguments_hash,
            "argument_names": list(self.argument_names),
            "argument_types": dict(self.argument_types),
            "argument_features": dict(self.argument_features),
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "enforcement_mode": self.enforcement_mode,
            "created_at": self.created_at,
        }


@dataclass
class ActionRecord:
    """The durable proof of what Agent7 decided and what then happened."""

    record_id: str
    action_id: str
    decision_id: str | None
    request: dict[str, Any]
    decision: dict[str, Any]
    executed: bool
    execution_status: str
    would_have_blocked: bool = False
    duration_ms: float | None = None
    error_type: str | None = None
    event_ids: list[str] = field(default_factory=list)
    outcome: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    completed_at: str | None = None

    @property
    def system_id(self) -> str | None:
        return self.request.get("system_id")

    def evidence_hash(self) -> str:
        return fingerprint(
            {
                "request": self.request,
                "decision": self.decision,
                "executed": self.executed,
                "execution_status": self.execution_status,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "action_id": self.action_id,
            "decision_id": self.decision_id,
            "system_id": self.system_id,
            "request": dict(self.request),
            "decision": dict(self.decision),
            "executed": self.executed,
            "execution_status": self.execution_status,
            "would_have_blocked": self.would_have_blocked,
            "duration_ms": self.duration_ms,
            "error_type": self.error_type,
            "event_ids": list(self.event_ids),
            "outcome": dict(self.outcome),
            "evidence_hash": self.evidence_hash(),
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }
