"""Authorization verdicts produced before an action executes."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from .sanitize import utc_now

# Verdicts. This milestone deliberately ships only these three -- no
# MODIFY / REDACT / ESCALATE until the enforcement path is proven.
VERDICT_ALLOW = "ALLOW"
VERDICT_DENY = "DENY"
VERDICT_REQUIRE_APPROVAL = "REQUIRE_APPROVAL"

VERDICTS = frozenset({VERDICT_ALLOW, VERDICT_DENY, VERDICT_REQUIRE_APPROVAL})

# Reason codes, ordered by the priority in which they are evaluated.
REASON_KILL_SWITCH = "kill_switch"
REASON_CAPABILITY_DENIED = "capability_denied"
REASON_CAPABILITY_NOT_APPROVED = "capability_not_approved"
REASON_NO_CAPABILITY_MATCH = "no_capability_match"
REASON_ARGUMENT_PATTERN_DENIED = "argument_pattern_denied"
REASON_APPROVAL_REQUIRED_UNTRUSTED = "approval_required_untrusted"
REASON_ALLOWED_BY_POLICY = "allowed_by_policy"

# Who produced the decision.
DECIDED_BY_LOCAL = "sdk_local"
DECIDED_BY_BACKEND = "backend"


def new_decision_id() -> str:
    return f"DEC-{uuid.uuid4().hex[:16]}"


@dataclass(frozen=True)
class Decision:
    """An authorization verdict for exactly one :class:`ActionRequest`."""

    decision_id: str
    action_id: str
    verdict: str
    reason: str
    reason_code: str
    decided_by: str = DECIDED_BY_LOCAL
    matched_capability_id: str | None = None
    kill_switch_id: str | None = None
    matched_pattern_id: str | None = None
    acap_version_id: str | None = None
    acap_version_number: int | None = None
    policy_version_id: str | None = None
    approval_required: bool = False
    created_at: str = field(default_factory=utc_now)

    @property
    def allowed(self) -> bool:
        return self.verdict == VERDICT_ALLOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "action_id": self.action_id,
            "verdict": self.verdict,
            "reason": self.reason,
            "reason_code": self.reason_code,
            "decided_by": self.decided_by,
            "matched_capability_id": self.matched_capability_id,
            "kill_switch_id": self.kill_switch_id,
            "matched_pattern_id": self.matched_pattern_id,
            "acap_version_id": self.acap_version_id,
            "acap_version_number": self.acap_version_number,
            "policy_version_id": self.policy_version_id,
            "approval_required": self.approval_required,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, action_id: str | None = None) -> "Decision":
        """Parse a decision returned by the backend. Raises ValueError if unusable."""
        verdict = str(payload.get("verdict") or "").upper()
        if verdict not in VERDICTS:
            raise ValueError(f"unknown verdict: {payload.get('verdict')!r}")
        resolved_action_id = payload.get("action_id") or action_id
        if not resolved_action_id:
            raise ValueError("decision is missing action_id")
        number = payload.get("acap_version_number")
        return cls(
            decision_id=str(payload.get("decision_id") or new_decision_id()),
            action_id=str(resolved_action_id),
            verdict=verdict,
            reason=str(payload.get("reason") or ""),
            reason_code=str(payload.get("reason_code") or ""),
            decided_by=str(payload.get("decided_by") or DECIDED_BY_BACKEND),
            matched_capability_id=payload.get("matched_capability_id"),
            kill_switch_id=payload.get("kill_switch_id"),
            matched_pattern_id=payload.get("matched_pattern_id"),
            acap_version_id=payload.get("acap_version_id"),
            acap_version_number=int(number) if isinstance(number, int) else None,
            policy_version_id=payload.get("policy_version_id"),
            approval_required=bool(payload.get("approval_required", False)),
            created_at=str(payload.get("created_at") or utc_now()),
        )
