"""Pre-execution authorization: build a request, decide, enforce, record.

This module is the decision point Agent7 places *before* a consequential
action runs. Persisted records never carry raw argument values: deny patterns
are matched in-process against live values and only the outcome survives.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from ai_governance.core.actions import (
    DEFAULT_ENFORCEMENT_MODE,
    ENFORCEMENT_MODES,
    EXECUTION_ALLOWED_EXECUTED,
    EXECUTION_APPROVAL_REQUIRED_BLOCKED,
    EXECUTION_DENIED_BLOCKED,
    EXECUTION_OBSERVE_ONLY,
    EXECUTION_SHADOW_ALLOWED,
    MODE_OBSERVE,
    MODE_SHADOW,
    ActionRecord,
    ActionRequest,
    argument_metadata,
    new_action_id,
    new_record_id,
)
from ai_governance.core.decisions import (
    DECIDED_BY_BACKEND,
    DECIDED_BY_LOCAL,
    REASON_ALLOWED_BY_POLICY,
    REASON_APPROVAL_REQUIRED_UNTRUSTED,
    REASON_ARGUMENT_PATTERN_DENIED,
    REASON_CAPABILITY_DENIED,
    REASON_CAPABILITY_NOT_APPROVED,
    REASON_KILL_SWITCH,
    REASON_NO_CAPABILITY_MATCH,
    VERDICT_ALLOW,
    VERDICT_DENY,
    VERDICT_REQUIRE_APPROVAL,
    Decision,
    new_decision_id,
)
from ai_governance.core.sanitize import utc_now

logger = logging.getLogger(__name__)

# Capability statuses that permit execution under policy.
ALLOWED_STATUSES = frozenset({"approved", "approved_for_acap", "edited"})
# Capability statuses a human explicitly refused.
DENIED_STATUSES = frozenset({"denied", "rejected"})

# Approval fields that count as trusted. 'granted' alone is deliberately
# excluded: it is asserted by the caller and is therefore spoofable.
TRUSTED_APPROVAL_FIELDS = ("verified", "trusted", "token_verified")

_EVENTS_SUFFIX = "/evidence/events"


class Agent7Blocked(Exception):
    """Raised instead of executing when on_deny='raise' is configured."""

    def __init__(self, decision: Decision) -> None:
        super().__init__(f"{decision.verdict}: {decision.reason}")
        self.decision = decision
        self.verdict = decision.verdict
        self.reason = decision.reason
        self.reason_code = decision.reason_code
        self.action_id = decision.action_id
        self.decision_id = decision.decision_id


def blocked_result(decision: Decision) -> dict[str, Any]:
    """The structured value a blocked function returns to its caller."""
    return {
        "agent7_blocked": True,
        "verdict": decision.verdict,
        "reason": decision.reason,
        "reason_code": decision.reason_code,
        "action_id": decision.action_id,
        "decision_id": decision.decision_id,
    }


def normalize_mode(mode: str | None) -> str:
    if mode is None:
        return DEFAULT_ENFORCEMENT_MODE
    text = str(mode).strip().lower()
    if text not in ENFORCEMENT_MODES:
        raise ValueError(
            f"enforcement_mode must be one of {sorted(ENFORCEMENT_MODES)}, got {mode!r}"
        )
    return text


# ----------------------------------------------------------------------
# Policy
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityPolicy:
    """The manifest's view of one capability."""

    name: str
    status: str
    capability_id: str | None = None
    module_path: str | None = None
    action_type: str | None = None
    approval_required: bool = False
    external_side_effect: bool | None = None
    data_classes: tuple[str, ...] = ()
    denied_argument_patterns: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class KillSwitch:
    kill_switch_id: str
    enabled: bool = True
    target_capabilities: tuple[str, ...] = ()
    verdict: str = VERDICT_DENY
    reason: str = "Capability disabled by kill switch"

    def targets(self, *, name: str | None, capability_id: str | None) -> bool:
        if not self.enabled or not self.target_capabilities:
            return False
        targets = set(self.target_capabilities)
        return (name is not None and name in targets) or (
            capability_id is not None and capability_id in targets
        )


@dataclass
class EnforcementPolicy:
    """Local policy compiled once from governance.yaml."""

    mode: str = DEFAULT_ENFORCEMENT_MODE
    capabilities: dict[str, CapabilityPolicy] = field(default_factory=dict)
    kill_switches: tuple[KillSwitch, ...] = ()
    acap_version_id: str | None = None
    acap_version_number: int | None = None

    def lookup(self, *, name: str | None, capability_id: str | None) -> CapabilityPolicy | None:
        if capability_id and capability_id in self.capabilities:
            return self.capabilities[capability_id]
        if name and name in self.capabilities:
            return self.capabilities[name]
        return None


def _compile_patterns(raw: Any) -> tuple[tuple[str, str], ...]:
    """Normalise denied_argument_patterns into (pattern_id, regex) pairs."""
    if not raw:
        return ()
    out: list[tuple[str, str]] = []
    for index, item in enumerate(raw):
        if isinstance(item, dict):
            pattern = item.get("pattern")
            pattern_id = str(item.get("id") or f"pattern_{index}")
        else:
            pattern = item
            pattern_id = f"pattern_{index}"
        if not pattern:
            continue
        text = str(pattern)
        # A double-quoted YAML scalar turns a backslash-b into a real
        # backspace, silently producing a deny rule that can never match.
        # A security control must fail loudly, not quietly never fire.
        if any(ord(ch) < 0x20 for ch in text):
            raise ValueError(
                f"denied_argument_patterns entry {pattern_id!r} contains a control "
                "character, which usually means a double-quoted YAML scalar ate a "
                "backslash. Write the regex in single quotes, e.g. "
                r"pattern: '(?i)\bdrop\b'"
            )
        try:
            re.compile(text)
        except re.error as exc:
            raise ValueError(
                f"invalid denied_argument_patterns entry {pattern!r}: {exc}"
            ) from exc
        out.append((pattern_id, text))
    return tuple(out)


def capability_policy_from_manifest(cap: dict[str, Any]) -> CapabilityPolicy:
    data_classes = cap.get("data_classes") or []
    return CapabilityPolicy(
        name=str(cap.get("name") or ""),
        status=str(cap.get("status") or "pending"),
        capability_id=cap.get("capability_id"),
        module_path=cap.get("module_path"),
        action_type=cap.get("action_type"),
        approval_required=bool(cap.get("approval_required") or False),
        external_side_effect=cap.get("external_side_effect"),
        data_classes=tuple(str(item) for item in data_classes),
        denied_argument_patterns=_compile_patterns(cap.get("denied_argument_patterns")),
    )


def build_policy_from_manifest(
    config: dict[str, Any], *, mode: str | None = None
) -> EnforcementPolicy:
    """Compile an EnforcementPolicy from a parsed governance manifest."""
    resolved_mode = normalize_mode(
        mode if mode is not None else config.get("enforcement_mode")
    )

    capabilities: dict[str, CapabilityPolicy] = {}
    for cap in config.get("capabilities", []) or []:
        policy = capability_policy_from_manifest(cap)
        if policy.name:
            capabilities[policy.name] = policy
        if policy.capability_id:
            capabilities[policy.capability_id] = policy

    switches: list[KillSwitch] = []
    for entry in config.get("kill_switches", []) or []:
        targets = entry.get("target_capabilities") or []
        verdict = str(entry.get("verdict") or VERDICT_DENY).upper()
        switches.append(
            KillSwitch(
                kill_switch_id=str(entry.get("id")),
                enabled=bool(entry.get("enabled", True)),
                target_capabilities=tuple(str(item) for item in targets),
                verdict=verdict if verdict in {VERDICT_DENY, VERDICT_REQUIRE_APPROVAL} else VERDICT_DENY,
                reason=str(entry.get("reason") or "Capability disabled by kill switch"),
            )
        )

    generated = config.get("generated_from") or {}
    number = generated.get("acap_version_number")
    return EnforcementPolicy(
        mode=resolved_mode,
        capabilities=capabilities,
        kill_switches=tuple(switches),
        acap_version_id=generated.get("acap_version_id"),
        acap_version_number=int(number) if isinstance(number, int) else None,
    )


# ----------------------------------------------------------------------
# Request construction
# ----------------------------------------------------------------------


def build_action_request(
    *,
    system_id: str,
    deployment_id: str,
    environment: str,
    agent_id: str,
    capability_name: str,
    enforcement_mode: str,
    raw_arguments: dict[str, Any] | None = None,
    arguments_hash: str | None = None,
    capability_id: str | None = None,
    capability_status: str | None = None,
    module_path: str | None = None,
    action_type: str | None = None,
    data_classes: list[str] | tuple[str, ...] | None = None,
    external_side_effect: bool | None = None,
    approval_required: bool | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
) -> ActionRequest:
    """Build an ActionRequest that carries no raw argument values."""
    metadata = argument_metadata(raw_arguments or {})
    return ActionRequest(
        action_id=new_action_id(),
        system_id=system_id,
        deployment_id=deployment_id,
        environment=environment,
        agent_id=agent_id,
        capability_name=capability_name,
        enforcement_mode=enforcement_mode,
        capability_id=capability_id,
        capability_status=capability_status,
        module_path=module_path,
        action_type=action_type,
        data_classes=list(data_classes or []),
        external_side_effect=external_side_effect,
        approval_required=approval_required,
        arguments_hash=arguments_hash,
        argument_names=metadata["argument_names"],
        argument_types=metadata["argument_types"],
        argument_features={
            "argument_count": metadata["argument_count"],
            "has_str_args": metadata["has_str_args"],
        },
        session_id=session_id,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
    )


# ----------------------------------------------------------------------
# Approval
# ----------------------------------------------------------------------


def verify_approval_token(request: ActionRequest, approval: Any) -> bool:
    """Return True only for an approval Agent7 has a reason to trust.

    ``approval.granted`` is intentionally NOT sufficient: it is asserted by the
    very code being governed and can be set by it. Only an explicitly verified
    marker counts. This is the seam where real signature verification belongs;
    today it is a deterministic flag check, not cryptography.
    """
    if not isinstance(approval, dict):
        return False
    return any(approval.get(key) is True for key in TRUSTED_APPROVAL_FIELDS)


# ----------------------------------------------------------------------
# Local decision engine
# ----------------------------------------------------------------------


def _decide(
    request: ActionRequest,
    verdict: str,
    reason: str,
    reason_code: str,
    *,
    policy: EnforcementPolicy | None = None,
    capability: CapabilityPolicy | None = None,
    kill_switch_id: str | None = None,
    matched_pattern_id: str | None = None,
    approval_required: bool = False,
) -> Decision:
    matched_capability_id = (capability.capability_id if capability else None) or request.capability_id
    return Decision(
        decision_id=new_decision_id(),
        action_id=request.action_id,
        verdict=verdict,
        reason=reason,
        reason_code=reason_code,
        decided_by=DECIDED_BY_LOCAL,
        matched_capability_id=matched_capability_id,
        kill_switch_id=kill_switch_id,
        matched_pattern_id=matched_pattern_id,
        acap_version_id=policy.acap_version_id if policy else None,
        acap_version_number=policy.acap_version_number if policy else None,
        approval_required=approval_required,
    )


def _match_denied_pattern(
    capability: CapabilityPolicy, raw_arguments: dict[str, Any] | None
) -> str | None:
    """Match deny patterns against live argument values, returning a pattern id.

    Values are inspected in-process and discarded. Only the returned pattern id
    is ever persisted, never the text that matched.
    """
    if not capability.denied_argument_patterns or not raw_arguments:
        return None
    for pattern_id, pattern in capability.denied_argument_patterns:
        compiled = re.compile(pattern)
        for value in raw_arguments.values():
            if isinstance(value, str) and compiled.search(value):
                return pattern_id
    return None


def authorize_action_local(
    request: ActionRequest,
    policy: EnforcementPolicy | None,
    *,
    raw_arguments: dict[str, Any] | None = None,
    approval: Any = None,
) -> Decision:
    """Deterministic local authorization.

    Priority is fixed and must not be reordered:
    kill switch -> denied/rejected -> not approved -> argument policy ->
    approval required -> allow.
    """
    name = request.capability_name
    capability_id = request.capability_id

    # 1. Kill switch outranks everything, including an approved capability.
    if policy is not None:
        for switch in policy.kill_switches:
            if switch.targets(name=name, capability_id=capability_id):
                return _decide(
                    request,
                    switch.verdict,
                    switch.reason,
                    REASON_KILL_SWITCH,
                    policy=policy,
                    kill_switch_id=switch.kill_switch_id,
                )

    # No capability policy at all: nothing has been governed, so nothing is
    # blocked. A bare @gov.tool() with no manifest keeps working as before.
    if policy is None or not policy.capabilities:
        return _decide(
            request,
            VERDICT_ALLOW,
            "No enforcement policy configured",
            REASON_ALLOWED_BY_POLICY,
            policy=policy,
        )

    capability = policy.lookup(name=name, capability_id=capability_id)
    status = (capability.status if capability else request.capability_status) or None

    # 2. Explicitly refused by a human.
    if status in DENIED_STATUSES:
        return _decide(
            request,
            VERDICT_DENY,
            f"Capability '{name}' is {status} in the governance manifest",
            REASON_CAPABILITY_DENIED,
            policy=policy,
            capability=capability,
        )

    # 3. Unknown capability, or known but not approved.
    if capability is None:
        return _decide(
            request,
            VERDICT_DENY,
            f"Capability '{name}' is not present in the governance manifest",
            REASON_NO_CAPABILITY_MATCH,
            policy=policy,
        )
    if status not in ALLOWED_STATUSES:
        return _decide(
            request,
            VERDICT_DENY,
            f"Capability '{name}' has status '{status}', which is not approved",
            REASON_CAPABILITY_NOT_APPROVED,
            policy=policy,
            capability=capability,
        )

    # 4. Argument policy, evaluated against live values then discarded.
    pattern_id = _match_denied_pattern(capability, raw_arguments)
    if pattern_id is not None:
        return _decide(
            request,
            VERDICT_DENY,
            f"Argument matched denied pattern '{pattern_id}'",
            REASON_ARGUMENT_PATTERN_DENIED,
            policy=policy,
            capability=capability,
            matched_pattern_id=pattern_id,
        )

    # 5. Approval gate.
    needs_approval = bool(capability.approval_required or request.approval_required)
    if needs_approval and not verify_approval_token(request, approval):
        return _decide(
            request,
            VERDICT_REQUIRE_APPROVAL,
            f"Capability '{name}' requires a verified approval before execution",
            REASON_APPROVAL_REQUIRED_UNTRUSTED,
            policy=policy,
            capability=capability,
            approval_required=True,
        )

    # 6. Allowed.
    return _decide(
        request,
        VERDICT_ALLOW,
        f"Capability '{name}' is approved for execution",
        REASON_ALLOWED_BY_POLICY,
        policy=policy,
        capability=capability,
        approval_required=needs_approval,
    )


# ----------------------------------------------------------------------
# Mode semantics
# ----------------------------------------------------------------------


def enforce_decision(decision: Decision, mode: str) -> tuple[bool, str, bool]:
    """Map (verdict, mode) to (should_execute, execution_status, would_have_blocked)."""
    blocking_verdict = decision.verdict in {VERDICT_DENY, VERDICT_REQUIRE_APPROVAL}

    if mode == MODE_OBSERVE:
        return True, EXECUTION_OBSERVE_ONLY, False

    if mode == MODE_SHADOW:
        if blocking_verdict:
            return True, EXECUTION_SHADOW_ALLOWED, True
        return True, EXECUTION_ALLOWED_EXECUTED, False

    if decision.verdict == VERDICT_DENY:
        return False, EXECUTION_DENIED_BLOCKED, True
    if decision.verdict == VERDICT_REQUIRE_APPROVAL:
        return False, EXECUTION_APPROVAL_REQUIRED_BLOCKED, True
    return True, EXECUTION_ALLOWED_EXECUTED, False


def build_action_record(
    request: ActionRequest,
    decision: Decision,
    *,
    executed: bool,
    execution_status: str,
    would_have_blocked: bool = False,
    duration_ms: float | None = None,
    error_type: str | None = None,
    event_ids: list[str] | None = None,
    outcome: dict[str, Any] | None = None,
) -> ActionRecord:
    return ActionRecord(
        record_id=new_record_id(),
        action_id=request.action_id,
        decision_id=decision.decision_id,
        request=request.to_dict(),
        decision=decision.to_dict(),
        executed=executed,
        execution_status=execution_status,
        would_have_blocked=would_have_blocked,
        duration_ms=duration_ms,
        error_type=error_type,
        event_ids=list(event_ids or []),
        outcome=dict(outcome or {}),
        completed_at=utc_now(),
    )


# ----------------------------------------------------------------------
# Backend transport
# ----------------------------------------------------------------------


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float = 1.0,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any] | None:
    """POST JSON and return the decoded response body, if any."""
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    response = (opener or urlopen)(request, timeout=timeout)
    try:
        status = int(getattr(response, "status", getattr(response, "code", 200)))
        if status >= 400:
            raise RuntimeError(f"Agent7 API returned HTTP {status}")
        read = getattr(response, "read", None)
        raw = read() if callable(read) else b""
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


class RemoteDecisionClient:
    """Asks the Agent7 backend to authorize an action.

    Returns None on any failure so the caller falls back to local policy. A
    local DENY is never downgraded just because the backend is unreachable.
    """

    def __init__(
        self,
        api_base: str,
        *,
        timeout_seconds: float = 1.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._opener = opener
        self.failures = 0

    def evaluate(self, request: ActionRequest) -> Decision | None:
        try:
            payload = post_json(
                f"{self.api_base}/actions/evaluate",
                {"action": request.to_dict()},
                timeout=self.timeout_seconds,
                opener=self._opener,
            )
            if not payload:
                return None
            decision_payload = payload.get("decision") or payload
            decision_payload = {**decision_payload, "decided_by": DECIDED_BY_BACKEND}
            return Decision.from_dict(decision_payload, action_id=request.action_id)
        except Exception:
            self.failures += 1
            logger.warning("Agent7 remote decision failed; using local policy", exc_info=True)
            return None


class ActionRecorder:
    """Writes ActionRecords to their own JSONL file and/or the backend.

    Deliberately separate from the evidence event sink: action records must
    never appear in the governance event stream.
    """

    def __init__(
        self,
        *,
        jsonl_path: str | Path | None = None,
        api_base: str | None = None,
        timeout_seconds: float = 1.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.path = Path(jsonl_path) if jsonl_path else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.api_base = api_base.rstrip("/") if api_base else None
        self.timeout_seconds = timeout_seconds
        self._opener = opener
        self._lock = threading.Lock()
        self.dropped_records = 0

    def record(self, record: ActionRecord) -> dict[str, Any]:
        payload = record.to_dict()
        if self.path is not None:
            try:
                line = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
                with self._lock:
                    with self.path.open("a", encoding="utf-8") as handle:
                        handle.write(line + "\n")
            except Exception:
                self.dropped_records += 1
                logger.warning("Agent7 action record write failed", exc_info=True)
        if self.api_base:
            try:
                post_json(
                    f"{self.api_base}/actions/record",
                    {"record": payload},
                    timeout=self.timeout_seconds,
                    opener=self._opener,
                )
            except Exception:
                self.dropped_records += 1
                logger.warning("Agent7 action record export failed", exc_info=True)
        return payload


def resolve_endpoints(api_endpoint: str | None) -> tuple[str | None, str | None]:
    """Split a configured endpoint into (events_url, api_base).

    Accepts both the historical full events URL and a plain base URL::

        http://127.0.0.1:8000/evidence/events -> (that URL, http://127.0.0.1:8000)
        http://127.0.0.1:8000                 -> (.../evidence/events, http://127.0.0.1:8000)
    """
    if not api_endpoint:
        return None, None
    endpoint = api_endpoint.strip()
    if not endpoint:
        return None, None
    trimmed = endpoint.rstrip("/")
    if trimmed.endswith(_EVENTS_SUFFIX):
        return endpoint, trimmed[: -len(_EVENTS_SUFFIX)] or None
    return f"{trimmed}{_EVENTS_SUFFIX}", trimmed


__all__ = [
    "ALLOWED_STATUSES",
    "DENIED_STATUSES",
    "ActionRecorder",
    "Agent7Blocked",
    "CapabilityPolicy",
    "EnforcementPolicy",
    "KillSwitch",
    "RemoteDecisionClient",
    "authorize_action_local",
    "blocked_result",
    "build_action_record",
    "build_action_request",
    "build_policy_from_manifest",
    "capability_policy_from_manifest",
    "enforce_decision",
    "normalize_mode",
    "post_json",
    "resolve_endpoints",
    "verify_approval_token",
]
