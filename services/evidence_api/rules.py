from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

ACAP_ID = "restaurant-agent-local-reviewed"

SYSTEM_RULES: dict[str, list[str]] = {
    "restaurant-agent": ["R1_confirm_without_proposal"],
    "customer-refund-agent": ["R_write_no_approval"],
}

DEFAULT_RULE_IDS = ["R1_confirm_without_proposal"]


def finding_id(rule_id: str, event_ids: list[str]) -> str:
    # R1 uses legacy "R1" prefix for backward-compatible deterministic IDs
    prefix = "R1" if rule_id == "R1_confirm_without_proposal" else rule_id
    digest = hashlib.sha256((prefix + "|" + "|".join(sorted(event_ids))).encode()).hexdigest()[:12]
    return f"F-{digest}"


def run_r1_confirm_without_proposal(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_session[str(event.get("_session_ref") or event.get("session_id") or "session:missing")].append(event)

    findings: list[dict[str, Any]] = []
    for session_ref, session_events in sorted(by_session.items()):
        ordered = sorted(
            session_events,
            key=lambda e: (
                e.get("_jsonl_line") if e.get("_jsonl_line") is not None else 1_000_000_000,
                e.get("timestamp") or "",
                e.get("event_id") or "",
            ),
        )
        prior_place_order = False
        outcomes = {
            e.get("span_id"): e
            for e in ordered
            if e.get("event_type") in {"tool_end", "tool_error"} and e.get("span_id")
        }
        for event in ordered:
            if event.get("event_type") != "tool_start":
                continue
            tool_name = (event.get("tool") or {}).get("name") or (event.get("component") or {}).get("name")
            if tool_name == "place_order":
                prior_place_order = True
            if tool_name != "confirm_order":
                continue
            if prior_place_order:
                continue
            outcome = outcomes.get(event.get("span_id"))
            event_ids = [event["event_id"]]
            findings.append(
                {
                    "finding_id": finding_id("R1_confirm_without_proposal", event_ids),
                    "rule_id": "R1_confirm_without_proposal",
                    "acap_id": ACAP_ID,
                    "violates": "P1",
                    "severity": "high",
                    "session": session_ref,
                    "event_ids": event_ids,
                    "trace_ids": [event["trace_id"]],
                    "outcome_event_id": outcome.get("event_id") if outcome else None,
                    "outcome_status": (outcome.get("outcome") or {}).get("status") if outcome else None,
                    "description": (
                        "confirm_order was invoked with no prior place_order proposal in the same session; "
                        "the model-supplied response argument is not trusted approval evidence."
                    ),
                }
            )
    from .control_library import enrich_finding
    for f in findings:
        enrich_finding(f)
    return findings


def run_write_no_approval(
    events: list[dict[str, Any]],
    acap_id: str = "unknown",
) -> list[dict[str, Any]]:
    """Generic rule: write action with approval.required=true but no approval evidence."""
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_session[str(event.get("_session_ref") or event.get("session_id") or "session:missing")].append(event)

    findings: list[dict[str, Any]] = []
    for session_ref, session_events in sorted(by_session.items()):
        ordered = sorted(
            session_events,
            key=lambda e: (
                e.get("_jsonl_line") if e.get("_jsonl_line") is not None else 1_000_000_000,
                e.get("timestamp") or "",
                e.get("event_id") or "",
            ),
        )
        outcomes = {
            e.get("span_id"): e
            for e in ordered
            if e.get("event_type") in {"tool_end", "tool_error"} and e.get("span_id")
        }
        for event in ordered:
            if event.get("event_type") != "tool_start":
                continue
            tool = event.get("tool") or {}
            approval = event.get("approval") or {}
            if tool.get("action_type") != "write":
                continue
            if approval.get("required") is not True:
                continue
            if approval.get("granted") is True:
                continue
            tool_name = tool.get("name") or (event.get("component") or {}).get("name") or "unknown"
            outcome = outcomes.get(event.get("span_id"))
            event_ids = [event["event_id"]]
            findings.append(
                {
                    "finding_id": finding_id("R_write_no_approval", event_ids),
                    "rule_id": "R_write_no_approval",
                    "acap_id": acap_id,
                    "violates": "P1",
                    "severity": "high",
                    "session": session_ref,
                    "event_ids": event_ids,
                    "trace_ids": [event["trace_id"]],
                    "outcome_event_id": outcome.get("event_id") if outcome else None,
                    "outcome_status": (outcome.get("outcome") or {}).get("status") if outcome else None,
                    "description": (
                        f"{tool_name} was invoked as a write action with approval required "
                        f"but no approval evidence was found in the session."
                    ),
                }
            )
    from .control_library import enrich_finding
    for f in findings:
        enrich_finding(f)
    return findings


def run_rules_for_system(
    events: list[dict[str, Any]],
    system_id: str,
    acap_id: str = "unknown",
) -> list[dict[str, Any]]:
    """Run the appropriate rules for a given system."""
    rule_ids = SYSTEM_RULES.get(system_id, DEFAULT_RULE_IDS)
    all_findings: list[dict[str, Any]] = []
    for rule_id in rule_ids:
        if rule_id == "R1_confirm_without_proposal":
            all_findings.extend(run_r1_confirm_without_proposal(events))
        elif rule_id == "R_write_no_approval":
            all_findings.extend(run_write_no_approval(events, acap_id=acap_id))
    return all_findings


# ---------------------------------------------------------------------------
# ACAP-capability field helpers (resilient to naming variations)
# ---------------------------------------------------------------------------

def _approval_required(cap: dict[str, Any]) -> bool:
    """Return True if the capability declares approval required."""
    if cap.get("approval_required") is True or cap.get("suggested_approval_required") is True:
        return True
    approval = cap.get("approval") or {}
    if isinstance(approval, dict):
        req = approval.get("required")
        if isinstance(req, dict):
            return bool(req.get("value"))
        return bool(req)
    return False


def _data_classes(cap: dict[str, Any]) -> set[str]:
    """Return the set of allowed data classes for a capability."""
    raw = cap.get("data_classes") or cap.get("suggested_data_classes") or []
    if isinstance(raw, list):
        return set(raw)
    return set()


def _action_type(cap: dict[str, Any]) -> str:
    """Return the action type for a capability."""
    return cap.get("action_type") or cap.get("suggested_action_type") or "unknown"


def _tool_name_from_event(event: dict[str, Any]) -> str | None:
    """Extract the tool name from a runtime event."""
    name = (event.get("tool") or {}).get("name")
    if name:
        return name
    return (event.get("component") or {}).get("name")


def _has_trusted_approval(event: dict[str, Any]) -> bool:
    """Check for a verifiable/trusted approval marker.

    ``approval.granted`` alone is NOT trusted — it is set by the same
    application we are auditing and can be forged.  We require an explicit
    ``approval.verified``, ``approval.trusted``, or ``approval.token_verified``
    flag to consider the approval evidence trustworthy.
    """
    approval = event.get("approval") or {}
    return bool(
        approval.get("verified") is True
        or approval.get("trusted") is True
        or approval.get("token_verified") is True
    )


def _session_ref(event: dict[str, Any]) -> str:
    return str(event.get("_session_ref") or event.get("session_id") or "session:missing")


# ---------------------------------------------------------------------------
# ACAP lookup builder
# ---------------------------------------------------------------------------

def _build_acap_lookup(acap_version: dict[str, Any]) -> dict[str, Any]:
    """Build name→capability maps from an ACAP version."""
    allowed: dict[str, dict[str, Any]] = {}
    for c in acap_version.get("allowed_capabilities", []):
        allowed[c["name"]] = c
    denied: dict[str, dict[str, Any]] = {}
    for c in acap_version.get("denied_capabilities", []):
        denied[c["name"]] = c
    return {"allowed": allowed, "denied": denied}


ACAP_RULE_IDS = [
    "R_ACAP_unapproved_observed",
    "R_ACAP_denied_observed",
    "R_ACAP_approval_required_missing",
    "R_ACAP_data_class_mismatch",
]


# ---------------------------------------------------------------------------
# ACAP-based rules
# ---------------------------------------------------------------------------

def run_acap_unapproved_observed(
    events: list[dict[str, Any]],
    acap_version: dict[str, Any],
) -> list[dict[str, Any]]:
    """Runtime tool observed but no matching allowed capability in ACAP."""
    lookup = _build_acap_lookup(acap_version)
    vid = acap_version.get("acap_version_id", "unknown")
    vnum = acap_version.get("version_number", 0)
    findings: list[dict[str, Any]] = []
    for event in events:
        if event.get("event_type") != "tool_start":
            continue
        name = _tool_name_from_event(event)
        if not name:
            continue
        # If in denied, R_ACAP_denied_observed handles it — no duplicate
        if name in lookup["denied"]:
            continue
        if name in lookup["allowed"]:
            continue
        eids = [event["event_id"]]
        findings.append({
            "finding_id": finding_id("R_ACAP_unapproved_observed", eids),
            "rule_id": "R_ACAP_unapproved_observed",
            "acap_id": vid,
            "acap_version_id": vid,
            "acap_version_number": vnum,
            "violates": "ACAP_authorization",
            "severity": "medium",
            "session": _session_ref(event),
            "event_ids": eids,
            "trace_ids": [event.get("trace_id", "")],
            "capability_id": None,
            "capability_name": name,
            "description": (
                f"Tool '{name}' was observed at runtime but has no matching "
                f"allowed capability in ACAP v{vnum} ({vid})."
            ),
        })
    return findings


def run_acap_denied_observed(
    events: list[dict[str, Any]],
    acap_version: dict[str, Any],
) -> list[dict[str, Any]]:
    """Runtime tool observed and matching capability exists in denied_capabilities."""
    lookup = _build_acap_lookup(acap_version)
    vid = acap_version.get("acap_version_id", "unknown")
    vnum = acap_version.get("version_number", 0)
    findings: list[dict[str, Any]] = []
    for event in events:
        if event.get("event_type") != "tool_start":
            continue
        name = _tool_name_from_event(event)
        if not name or name not in lookup["denied"]:
            continue
        cap = lookup["denied"][name]
        eids = [event["event_id"]]
        findings.append({
            "finding_id": finding_id("R_ACAP_denied_observed", eids),
            "rule_id": "R_ACAP_denied_observed",
            "acap_id": vid,
            "acap_version_id": vid,
            "acap_version_number": vnum,
            "violates": "ACAP_authorization",
            "severity": "high",
            "session": _session_ref(event),
            "event_ids": eids,
            "trace_ids": [event.get("trace_id", "")],
            "capability_id": cap.get("capability_id"),
            "capability_name": name,
            "description": (
                f"Tool '{name}' was observed at runtime but is explicitly "
                f"denied in ACAP v{vnum} ({vid})."
            ),
        })
    return findings


def run_acap_approval_required_missing(
    events: list[dict[str, Any]],
    acap_version: dict[str, Any],
) -> list[dict[str, Any]]:
    """Allowed capability requires approval but no trusted approval evidence present."""
    lookup = _build_acap_lookup(acap_version)
    vid = acap_version.get("acap_version_id", "unknown")
    vnum = acap_version.get("version_number", 0)
    findings: list[dict[str, Any]] = []
    for event in events:
        if event.get("event_type") != "tool_start":
            continue
        name = _tool_name_from_event(event)
        if not name or name not in lookup["allowed"]:
            continue
        cap = lookup["allowed"][name]
        if not _approval_required(cap):
            continue
        if _has_trusted_approval(event):
            continue
        eids = [event["event_id"]]
        findings.append({
            "finding_id": finding_id("R_ACAP_approval_required_missing", eids),
            "rule_id": "R_ACAP_approval_required_missing",
            "acap_id": vid,
            "acap_version_id": vid,
            "acap_version_number": vnum,
            "violates": "ACAP_authorization",
            "severity": "high",
            "session": _session_ref(event),
            "event_ids": eids,
            "trace_ids": [event.get("trace_id", "")],
            "capability_id": cap.get("capability_id"),
            "capability_name": name,
            "description": (
                f"Tool '{name}' requires approval per ACAP v{vnum}, but no "
                f"trusted approval evidence was observed. "
                f"approval.granted alone is not trusted."
            ),
        })
    return findings


def run_acap_data_class_mismatch(
    events: list[dict[str, Any]],
    acap_version: dict[str, Any],
) -> list[dict[str, Any]]:
    """Runtime data classes exceed or conflict with ACAP allowed data classes."""
    lookup = _build_acap_lookup(acap_version)
    vid = acap_version.get("acap_version_id", "unknown")
    vnum = acap_version.get("version_number", 0)
    findings: list[dict[str, Any]] = []
    for event in events:
        if event.get("event_type") != "tool_start":
            continue
        name = _tool_name_from_event(event)
        if not name or name not in lookup["allowed"]:
            continue
        cap = lookup["allowed"][name]
        allowed_classes = _data_classes(cap)
        if not allowed_classes:
            continue  # no data class constraints declared
        event_data = event.get("data") or {}
        event_classes = set(event_data.get("classifications") or [])
        if not event_classes:
            continue
        excess = event_classes - allowed_classes
        if not excess:
            continue
        eids = [event["event_id"]]
        findings.append({
            "finding_id": finding_id("R_ACAP_data_class_mismatch", eids),
            "rule_id": "R_ACAP_data_class_mismatch",
            "acap_id": vid,
            "acap_version_id": vid,
            "acap_version_number": vnum,
            "violates": "ACAP_data_boundary",
            "severity": "medium",
            "session": _session_ref(event),
            "event_ids": eids,
            "trace_ids": [event.get("trace_id", "")],
            "capability_id": cap.get("capability_id"),
            "capability_name": name,
            "description": (
                f"Tool '{name}' runtime data classes {sorted(excess)} "
                f"exceed ACAP v{vnum} allowed classes {sorted(allowed_classes)}."
            ),
        })
    return findings


def run_all_acap_rules(
    events: list[dict[str, Any]],
    acap_version: dict[str, Any],
) -> list[dict[str, Any]]:
    """Run all four ACAP comparison rules."""
    findings: list[dict[str, Any]] = []
    findings.extend(run_acap_denied_observed(events, acap_version))
    findings.extend(run_acap_unapproved_observed(events, acap_version))
    findings.extend(run_acap_approval_required_missing(events, acap_version))
    findings.extend(run_acap_data_class_mismatch(events, acap_version))
    return findings

