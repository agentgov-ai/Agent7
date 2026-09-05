"""Risk classification, framework applicability, and assessment builder.

All outputs are derived from the reviewed ACAP, stored evidence, and
deterministic rules.  Nothing here constitutes a legal compliance claim.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime, timezone
from typing import Any


def _value(obj: Any) -> Any:
    if isinstance(obj, dict) and "value" in obj:
        return obj["value"]
    return obj


HIGH_SENSITIVITY = {"payment", "financial", "health", "biometric"}
MEDIUM_SENSITIVITY = {"contact", "personal", "pii"}


def build_risk_profile(acap: dict[str, Any]) -> dict[str, Any]:
    """Derive a risk profile from a reviewed ACAP."""
    system = acap.get("system") or {}
    tools = acap.get("tools") or []

    # --- use_case / environment / jurisdiction ---
    use_case = _value(system.get("purpose"))
    environment = system.get("environment")
    jurisdiction = _value(system.get("jurisdiction"))

    # --- Collect tool-level signals ---
    has_write = False
    has_side_effect = False
    all_writes_approved = True
    any_approval_required = False
    all_data_classes: set[str] = set()

    for tool in tools:
        action = _value(tool.get("proposed_action_type"))
        side_effect = _value(tool.get("proposed_external_side_effect"))
        approval_obj = (tool.get("approval") or {}).get("required")
        approval_req = _value(approval_obj)
        data_classes = _value(tool.get("proposed_data_classes")) or []

        if action in ("write", "execute"):
            has_write = True
            if approval_req is not True:
                all_writes_approved = False
        if side_effect is True:
            has_side_effect = True
        if approval_req is True:
            any_approval_required = True
        all_data_classes.update(data_classes)

    # --- authority_level ---
    if not has_write:
        authority_level = "advisory"
    elif all_writes_approved:
        authority_level = "delegated"
    else:
        authority_level = "autonomous"

    # --- autonomy_level ---
    if any_approval_required:
        autonomy_level = "human_in_loop"
    elif has_side_effect:
        autonomy_level = "human_on_loop"
    else:
        autonomy_level = "fully_autonomous"

    # --- data_sensitivity ---
    if all_data_classes & HIGH_SENSITIVITY:
        data_sensitivity = "high"
    elif all_data_classes & MEDIUM_SENSITIVITY:
        data_sensitivity = "medium"
    else:
        data_sensitivity = "low"

    # --- human_approval_model ---
    if any_approval_required and has_write and all_writes_approved:
        human_approval_model = "required_for_writes"
    elif any_approval_required:
        human_approval_model = "partial"
    else:
        human_approval_model = "not_required"

    return {
        "use_case": use_case,
        "environment": environment,
        "authority_level": authority_level,
        "autonomy_level": autonomy_level,
        "data_sensitivity": data_sensitivity,
        "external_side_effects": has_side_effect,
        "human_approval_model": human_approval_model,
        "jurisdiction": jurisdiction,
    }


def evaluate_framework_applicability(
    risk_profile: dict[str, Any],
    acap: dict[str, Any],
) -> list[dict[str, Any]]:
    """Determine which governance frameworks apply and why."""
    tools = acap.get("tools") or []
    tool_count = len(tools)
    agents = acap.get("agents") or []
    framework = _value((acap.get("system") or {}).get("framework")) or {}
    has_langgraph = bool(framework.get("langgraph"))

    jurisdiction = risk_profile.get("jurisdiction")
    authority = risk_profile.get("authority_level")
    sensitivity = risk_profile.get("data_sensitivity")
    environment = risk_profile.get("environment")

    frameworks: list[dict[str, Any]] = []

    # --- ACAP ---
    acap_applicable = tool_count > 0
    frameworks.append({
        "framework": "ACAP",
        "applicable": acap_applicable,
        "reason": (
            f"System has {tool_count} tools with authorization boundaries defined in a reviewed ACAP"
            if acap_applicable
            else "No tools or authorization boundaries discovered"
        ),
        "relevance": "Defines allowed/prohibited actions, approval requirements, and content policy",
    })

    # --- OWASP Agentic ---
    is_agentic = tool_count > 0 or len(agents) > 0
    frameworks.append({
        "framework": "OWASP Agentic",
        "applicable": is_agentic,
        "reason": (
            f"System uses {tool_count} tools with agentic execution"
            + (f" via LangGraph" if has_langgraph else "")
            if is_agentic
            else "No agentic behavior discovered"
        ),
        "relevance": "Covers prompt injection, tool misuse, excessive agency, and insecure output handling",
    })

    # --- NIST AI RMF ---
    frameworks.append({
        "framework": "NIST AI RMF",
        "applicable": True,
        "reason": "Applies as general AI risk-management guidance regardless of deployment scope",
        "relevance": "GOVERN, MAP, MEASURE, MANAGE functions for AI risk lifecycle",
    })

    # --- EU AI Act ---
    eu_jurisdiction = isinstance(jurisdiction, str) and "eu" in jurisdiction.lower() if jurisdiction else False
    eu_high_risk = authority == "autonomous" or sensitivity == "high"
    eu_applicable = eu_jurisdiction and eu_high_risk
    if eu_applicable:
        reason = (
            f"EU jurisdiction declared with {authority} authority level "
            f"and {sensitivity} data sensitivity"
        )
    else:
        parts = []
        if not eu_jurisdiction:
            parts.append(f"{environment or 'unknown'} environment with no EU jurisdiction declared")
        if not eu_high_risk:
            parts.append("not classified as high-risk")
        reason = "; ".join(parts).capitalize()
    frameworks.append({
        "framework": "EU AI Act",
        "applicable": eu_applicable,
        "reason": reason,
        "relevance": "Mandatory requirements for high-risk AI systems deployed in EU jurisdiction",
    })

    # --- ISO/IEC 42001 ---
    frameworks.append({
        "framework": "ISO/IEC 42001",
        "applicable": "informational",
        "reason": "Supporting management-system evidence; does not constitute certification",
        "relevance": "AI management system standard for organizational controls and risk assessment",
    })

    return frameworks


def build_assessment(
    system_id: str,
    acap: dict[str, Any],
    findings: list[dict[str, Any]],
    coverage_fields: list[dict[str, Any]],
    event_count: int,
    risk_profile: dict[str, Any],
    applicability: list[dict[str, Any]],
) -> dict[str, Any]:
    """Combine all governance signals into a single assessment."""
    # --- coverage summary ---
    coverage_counts: dict[str, int] = Counter()
    for field in coverage_fields:
        status = field.get("status", "unknown")
        if status in ("captured", "captured_for_new_events", "captured_with_annotation"):
            coverage_counts["captured"] += 1
        elif status == "partial":
            coverage_counts["partial"] += 1
        elif status == "annotation_required":
            coverage_counts["annotation_required"] += 1
        elif status == "missing":
            coverage_counts["missing"] += 1
        else:
            coverage_counts[status] += 1

    # --- findings summary ---
    severity_counts: dict[str, int] = Counter()
    failed_controls: list[str] = []
    for f in findings:
        sev = f.get("severity", "unknown")
        severity_counts[sev] += 1
        ctrl = f.get("failed_control")
        if ctrl and ctrl not in failed_controls:
            failed_controls.append(ctrl)

    return {
        "system_id": system_id,
        "acap_status": acap.get("status"),
        "risk_profile": risk_profile,
        "evidence_summary": {
            "event_count": event_count,
            "coverage": {
                **dict(coverage_counts),
                "total_fields": len(coverage_fields),
            },
        },
        "findings_summary": {
            "total": len(findings),
            "by_severity": dict(severity_counts),
            "failed_controls": failed_controls,
        },
        "framework_applicability": applicability,
    }


def _overall_status(findings: list[dict[str, Any]]) -> str:
    for f in findings:
        if f.get("severity") == "high":
            return "requires_remediation"
    if findings:
        return "needs_review"
    return "satisfactory"


def _evidence_confidence(coverage_fields: list[dict[str, Any]]) -> str:
    has_missing = False
    all_captured = True
    for field in coverage_fields:
        status = field.get("status", "unknown")
        if status == "missing":
            has_missing = True
        if status not in ("captured", "captured_for_new_events", "captured_with_annotation"):
            all_captured = False
    if has_missing:
        return "low"
    if all_captured:
        return "high"
    return "medium"


def _framework_status(
    applicability: list[dict[str, Any]],
    failed_controls: list[str],
    has_findings: bool,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    has_auth_failure = any(c.startswith("AGT-AUTH") for c in failed_controls)
    for fw in applicability:
        name = fw["framework"]
        applicable = fw["applicable"]
        if applicable is False or applicable == "false":
            status = "not_applicable"
        elif name == "ACAP":
            status = "failed" if has_auth_failure else "passed"
        elif name == "ISO/IEC 42001":
            status = "informational"
        elif applicable == "informational":
            status = "informational"
        elif has_findings:
            status = "needs_review"
        else:
            status = "passed"
        result.append({"framework": name, "status": status})
    return result


def _recommended_actions(
    findings: list[dict[str, Any]],
    coverage_fields: list[dict[str, Any]],
    acap: dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    if any(f.get("severity") == "high" for f in findings):
        actions.append("Remediate high-severity findings before next assessment")
    if any(f.get("status") == "missing" for f in coverage_fields):
        actions.append("Add instrumentation for missing evidence fields")
    if any(f.get("status") == "annotation_required" for f in coverage_fields):
        actions.append("Complete manual annotations for annotation-required fields")
    unresolved = [
        t.get("name") for t in (acap.get("tools") or [])
        if t.get("authorization") == "unresolved"
    ]
    if unresolved:
        actions.append("Complete ACAP review for all discovered tools")
    return actions


def build_full_assessment(
    system_id: str,
    acap: dict[str, Any],
    findings: list[dict[str, Any]],
    coverage_fields: list[dict[str, Any]],
    event_count: int,
    risk_profile: dict[str, Any],
    applicability: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a frozen assessment snapshot with status logic."""
    base = build_assessment(
        system_id, acap, findings, coverage_fields,
        event_count, risk_profile, applicability,
    )
    now = datetime.now(timezone.utc).isoformat()
    assessment_id = "A-" + hashlib.sha256(
        (system_id + now).encode()
    ).hexdigest()[:12]
    failed_controls = base["findings_summary"]["failed_controls"]
    has_findings = base["findings_summary"]["total"] > 0

    base["assessment_id"] = assessment_id
    base["assessed_at"] = now
    base["overall_status"] = _overall_status(findings)
    base["evidence_confidence"] = _evidence_confidence(coverage_fields)
    base["framework_status"] = _framework_status(
        applicability, failed_controls, has_findings,
    )
    base["recommended_next_actions"] = _recommended_actions(
        findings, coverage_fields, acap,
    )
    return base
