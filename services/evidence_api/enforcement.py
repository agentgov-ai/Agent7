"""Backend authorization engine for governed actions.

Mirrors the SDK's local decision order, but sources truth from the database so
a kill switch toggled in the dashboard takes effect on the next action.

This returns the *policy verdict only*. Enforcement-mode semantics (whether a
DENY actually blocks) stay in the SDK, so one backend can serve clients running
in observe, shadow and enforce at the same time.

What the backend does own is which *mode* is in force for a system, so an
operator can change a running system's posture from the dashboard. It reports
that mode alongside the verdict; the SDK still applies it.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from . import db

# Reuse the SDK's mode constants rather than keeping a second copy in sync.
# validation.py is the existing precedent for importing from the SDK here.
from .validation import SCHEMA_PATH  # noqa: F401  (puts sdk-python on sys.path)
from ai_governance.core.actions import (  # noqa: E402
    DEFAULT_ENFORCEMENT_MODE,
    ENFORCEMENT_MODES,
    MODE_ENFORCE,
    MODE_OBSERVE,
    MODE_SHADOW,
)

VERDICT_ALLOW = "ALLOW"
VERDICT_DENY = "DENY"
VERDICT_REQUIRE_APPROVAL = "REQUIRE_APPROVAL"

REASON_KILL_SWITCH = "kill_switch"
REASON_CAPABILITY_DENIED = "capability_denied"
REASON_CAPABILITY_NOT_APPROVED = "capability_not_approved"
REASON_NO_CAPABILITY_MATCH = "no_capability_match"
REASON_APPROVAL_REQUIRED_UNTRUSTED = "approval_required_untrusted"
REASON_ALLOWED_BY_POLICY = "allowed_by_policy"

DECIDED_BY_BACKEND = "backend"

MODE_RANK = {MODE_OBSERVE: 0, MODE_SHADOW: 1, MODE_ENFORCE: 2}

MODE_SOURCE_SDK = "sdk"
MODE_SOURCE_OVERRIDE = "dashboard_override"
MODE_SOURCE_OVERRIDE_IGNORED = "dashboard_override_ignored"

ALLOWED_REVIEW_STATUSES = frozenset({"approved", "approved_for_acap", "edited"})
DENIED_REVIEW_STATUSES = frozenset({"denied", "rejected"})


def _decision(
    action_id: str,
    verdict: str,
    reason: str,
    reason_code: str,
    *,
    matched_capability_id: str | None = None,
    kill_switch_id: str | None = None,
    acap_version_id: str | None = None,
    acap_version_number: int | None = None,
    approval_required: bool = False,
) -> dict[str, Any]:
    return {
        "decision_id": f"DEC-{uuid.uuid4().hex[:16]}",
        "action_id": action_id,
        "verdict": verdict,
        "reason": reason,
        "reason_code": reason_code,
        "decided_by": DECIDED_BY_BACKEND,
        "matched_capability_id": matched_capability_id,
        "kill_switch_id": kill_switch_id,
        "matched_pattern_id": None,
        "acap_version_id": acap_version_id,
        "acap_version_number": acap_version_number,
        "policy_version_id": acap_version_id,
        "approval_required": approval_required,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _latest_acap(conn: sqlite3.Connection, system_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT acap_version_id, version_number, payload_json
        FROM acap_versions
        WHERE system_id = ?
        ORDER BY version_number DESC
        LIMIT 1
        """,
        (system_id,),
    ).fetchone()
    if row is None:
        return None
    payload = json.loads(row["payload_json"])
    payload.setdefault("acap_version_id", row["acap_version_id"])
    payload.setdefault("version_number", row["version_number"])
    return payload


def _index_acap_capabilities(acap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index an ACAP version's allowed and denied capability lists by name and id."""
    index: dict[str, dict[str, Any]] = {}
    for key, status in (
        ("allowed_capabilities", "approved_for_acap"),
        ("denied_capabilities", "denied"),
    ):
        for cap in acap.get(key) or []:
            entry = {**cap, "_status": cap.get("review_status") or status}
            if cap.get("name"):
                index[str(cap["name"])] = entry
            if cap.get("capability_id"):
                index[str(cap["capability_id"])] = entry
    return index


def _capability_review_status(
    conn: sqlite3.Connection, system_id: str, name: str | None, capability_id: str | None
) -> dict[str, Any] | None:
    """Fall back to the newest scanned capability row when no ACAP exists."""
    if capability_id:
        row = conn.execute(
            """
            SELECT name, capability_id, review_status, suggested_approval_required
            FROM capabilities
            WHERE system_id = ? AND capability_id = ?
            ORDER BY upload_id DESC LIMIT 1
            """,
            (system_id, capability_id),
        ).fetchone()
        if row is not None:
            return dict(row)
    if name:
        row = conn.execute(
            """
            SELECT name, capability_id, review_status, suggested_approval_required
            FROM capabilities
            WHERE system_id = ? AND name = ?
            ORDER BY upload_id DESC LIMIT 1
            """,
            (system_id, name),
        ).fetchone()
        if row is not None:
            return dict(row)
    return None


def evaluate_action(conn: sqlite3.Connection, request: dict[str, Any]) -> dict[str, Any]:
    """Authorize one action request against stored policy.

    Priority is fixed and matches the SDK:
    kill switch -> denied/rejected -> not approved -> approval required -> allow.
    """
    action_id = str(request.get("action_id") or f"ACT-{uuid.uuid4().hex[:16]}")
    system_id = str(request.get("system_id") or "")
    name = request.get("capability_name")
    capability_id = request.get("capability_id")

    # 1. Kill switches outrank everything, including an approved capability.
    for switch in db.active_kill_switches(conn, system_id):
        targets = set(switch.get("target_capabilities") or [])
        if (name and name in targets) or (capability_id and capability_id in targets):
            verdict = switch.get("verdict") or VERDICT_DENY
            if verdict not in {VERDICT_DENY, VERDICT_REQUIRE_APPROVAL}:
                verdict = VERDICT_DENY
            return _decision(
                action_id,
                verdict,
                switch.get("reason") or f"Kill switch '{switch['kill_switch_id']}' is active",
                REASON_KILL_SWITCH,
                matched_capability_id=capability_id,
                kill_switch_id=switch["kill_switch_id"],
            )

    acap = _latest_acap(conn, system_id)
    acap_version_id = acap.get("acap_version_id") if acap else None
    acap_version_number = acap.get("version_number") if acap else None

    capability: dict[str, Any] | None = None
    status: str | None = None
    if acap is not None:
        index = _index_acap_capabilities(acap)
        capability = index.get(str(name)) or (
            index.get(str(capability_id)) if capability_id else None
        )
        status = capability.get("_status") if capability else None

    if capability is None:
        row = _capability_review_status(conn, system_id, name, capability_id)
        if row is not None:
            capability = row
            status = row.get("review_status")

    # No governance record at all for this system: the backend has nothing to
    # say, so it defers to whatever the caller's local manifest decided.
    if capability is None and acap is None:
        return _decision(
            action_id,
            VERDICT_ALLOW,
            "No backend policy recorded for this system; deferring to local manifest",
            REASON_ALLOWED_BY_POLICY,
            matched_capability_id=capability_id,
        )

    matched_id = (capability or {}).get("capability_id") or capability_id

    # 2. Explicitly refused by a human.
    if status in DENIED_REVIEW_STATUSES:
        return _decision(
            action_id,
            VERDICT_DENY,
            f"Capability '{name}' is {status} in ACAP {acap_version_id or 'review'}",
            REASON_CAPABILITY_DENIED,
            matched_capability_id=matched_id,
            acap_version_id=acap_version_id,
            acap_version_number=acap_version_number,
        )

    # 3. Unknown, or known but not approved.
    if capability is None:
        return _decision(
            action_id,
            VERDICT_DENY,
            f"Capability '{name}' is not in ACAP {acap_version_id}",
            REASON_NO_CAPABILITY_MATCH,
            acap_version_id=acap_version_id,
            acap_version_number=acap_version_number,
        )
    if status not in ALLOWED_REVIEW_STATUSES:
        return _decision(
            action_id,
            VERDICT_DENY,
            f"Capability '{name}' has status '{status}', which is not approved",
            REASON_CAPABILITY_NOT_APPROVED,
            matched_capability_id=matched_id,
            acap_version_id=acap_version_id,
            acap_version_number=acap_version_number,
        )

    # 4. Approval gate. The backend never sees an approval token, so an action
    # needing approval is held; the SDK grants it only on verified approval.
    needs_approval = bool(
        capability.get("approval_required")
        or capability.get("suggested_approval_required")
        or request.get("approval_required")
    )
    if needs_approval:
        return _decision(
            action_id,
            VERDICT_REQUIRE_APPROVAL,
            f"Capability '{name}' requires a verified approval before execution",
            REASON_APPROVAL_REQUIRED_UNTRUSTED,
            matched_capability_id=matched_id,
            acap_version_id=acap_version_id,
            acap_version_number=acap_version_number,
            approval_required=True,
        )

    # 5. Allowed.
    return _decision(
        action_id,
        VERDICT_ALLOW,
        f"Capability '{name}' is approved in ACAP {acap_version_id or 'review'}",
        REASON_ALLOWED_BY_POLICY,
        matched_capability_id=matched_id,
        acap_version_id=acap_version_id,
        acap_version_number=acap_version_number,
    )


# ----------------------------------------------------------------------
# Enforcement-mode resolution
# ----------------------------------------------------------------------


def _clean_mode(mode: Any) -> str | None:
    """Normalize a mode string, or None if it is absent or unrecognised."""
    if mode is None:
        return None
    text = str(mode).strip().lower()
    return text if text in ENFORCEMENT_MODES else None


def resolve_enforcement_mode(
    conn: sqlite3.Connection,
    system_id: str,
    requested_mode: Any = None,
) -> dict[str, Any]:
    """Return the effective enforcement mode for a system.

    Strictest wins: the dashboard can tighten a system's posture but never
    loosen it, which mirrors the rule that local policy is a floor. An override
    weaker than what the SDK sent is reported as ignored rather than dropped
    silently, so the dashboard can explain why nothing changed.
    """
    sdk_mode = _clean_mode(requested_mode) or DEFAULT_ENFORCEMENT_MODE
    row = db.get_enforcement_mode_override(conn, system_id)
    override = _clean_mode(row.get("mode")) if row else None

    if override is None:
        effective, source = sdk_mode, MODE_SOURCE_SDK
    elif MODE_RANK[override] > MODE_RANK[sdk_mode]:
        effective, source = override, MODE_SOURCE_OVERRIDE
    elif MODE_RANK[override] == MODE_RANK[sdk_mode]:
        effective, source = override, MODE_SOURCE_OVERRIDE
    else:
        effective, source = sdk_mode, MODE_SOURCE_OVERRIDE_IGNORED

    return {
        "system_id": system_id,
        "mode": effective,
        "source": source,
        "sdk_mode": sdk_mode,
        "override": override,
        "updated_at": row.get("updated_at") if row else None,
        "updated_by": row.get("updated_by") if row else None,
    }
