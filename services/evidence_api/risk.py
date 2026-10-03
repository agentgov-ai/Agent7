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

# Action types that imply the system can reach outside itself.
SENSITIVITY_RANK = {"low": 0, "medium": 1, "high": 2}

SIDE_EFFECT_ACTION_TYPES = {
    "write", "execute", "external_api_call", "query_execute", "communicate",
}
WRITE_ACTION_TYPES = {"write", "execute", "query_execute", "external_api_call"}

EMPTY_FACTS: dict[str, Any] = {}


def _inputs(inputs: dict[str, Any] | None) -> dict[str, Any]:
    """Human-declared assessment inputs, or an empty dict.

    Inputs state what discovery cannot infer: jurisdiction, use case, high-risk
    classification. They supplement facts and a reviewed ACAP, never override a
    reviewed ACAP.
    """
    return inputs or EMPTY_FACTS


def _facts(facts: dict[str, Any] | None) -> dict[str, Any]:
    """System facts read from the database, or an empty dict.

    Facts *supplement* a reviewed ACAP; they never override it. A system with a
    reviewed ACAP fixture keeps exactly the values it had before facts existed.
    """
    return facts or EMPTY_FACTS


def capabilities_as_tools(facts: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Shape discovered/approved capabilities like reviewed-ACAP tools.

    Lets a discovery-only system reuse the same derivation as a system with a
    hand-reviewed ACAP, instead of duplicating the rules. Capability rows use
    ``suggested_*`` keys; reviewed-ACAP tools use ``proposed_*``.
    """
    tools: list[dict[str, Any]] = []
    for cap in _facts(facts).get("capabilities") or []:
        tools.append({
            "name": cap.get("name"),
            "proposed_action_type": cap.get("suggested_action_type")
            or cap.get("action_type"),
            "proposed_external_side_effect": bool(cap.get("external_side_effect")),
            "proposed_data_classes": cap.get("suggested_data_classes")
            or cap.get("data_classes")
            or [],
            "approval": {
                "required": bool(
                    cap.get("suggested_approval_required")
                    or cap.get("approval_required")
                )
            },
        })
    return tools


def _derived_use_case(system_id: str | None, facts: dict[str, Any] | None) -> str | None:
    """A factual one-line description when no reviewed ACAP states a purpose."""
    data = _facts(facts)
    count = len(data.get("capabilities") or [])
    if system_id and "skyquery" in str(system_id).lower():
        return "SkyQuery governed data/query assistant"
    if count:
        return f"Governed application with {count} discovered capabilities"
    return None


def build_risk_profile(
    acap: dict[str, Any],
    facts: dict[str, Any] | None = None,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive a risk profile from a reviewed ACAP, supplemented by system facts.

    A reviewed ACAP always wins. ``facts`` only fills gaps, so the six demo
    systems that ship a reviewed ACAP fixture are unaffected.
    """
    data = _facts(facts)
    declared = _inputs(inputs)
    system = acap.get("system") or {}
    tools = acap.get("tools") or []
    if not tools:
        tools = capabilities_as_tools(facts)

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

    # Fill only what the reviewed ACAP did not state. Declared inputs outrank
    # derived guesses, because a person stated them.
    if not use_case:
        use_case = declared.get("use_case") or _derived_use_case(
            data.get("system_id"), facts
        )
    if not jurisdiction:
        jurisdiction = declared.get("jurisdiction")
    if not environment:
        environment = data.get("environment") or ("local" if data else None)
    if not has_side_effect:
        has_side_effect = bool(data.get("has_external_side_effect"))
    # A declared sensitivity only raises the derived one, never lowers it.
    declared_sensitivity = declared.get("data_sensitivity")
    if declared_sensitivity in SENSITIVITY_RANK:
        if SENSITIVITY_RANK[declared_sensitivity] > SENSITIVITY_RANK.get(data_sensitivity, 0):
            data_sensitivity = declared_sensitivity

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
    facts: dict[str, Any] | None = None,
    inputs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Determine which governance frameworks apply and why.

    Each entry carries ``why`` / ``why_not`` / ``evidence`` / ``would_change`` so
    the dashboard can explain a result instead of just asserting it. Every value
    is a factual statement about this system's own data -- never a legal claim.
    """
    data = _facts(facts)
    declared = _inputs(inputs)
    tools = acap.get("tools") or []
    tool_count = len(tools)
    agents = acap.get("agents") or []
    framework = _value((acap.get("system") or {}).get("framework")) or {}
    has_langgraph = bool(framework.get("langgraph")) if isinstance(framework, dict) else False

    jurisdiction = risk_profile.get("jurisdiction")
    authority = risk_profile.get("authority_level")
    sensitivity = risk_profile.get("data_sensitivity")
    environment = risk_profile.get("environment")

    acap_version_id = data.get("acap_version_id")
    acap_version_count = int(data.get("acap_version_count") or 0)
    approved = int(data.get("approved_count") or 0)
    denied = int(data.get("denied_count") or 0)
    pending = int(data.get("pending_count") or 0)
    discovered = len(data.get("capabilities") or [])
    action_count = int(data.get("action_count") or 0)
    denied_actions = int(data.get("denied_action_count") or 0)
    kill_switches = int(data.get("kill_switch_count") or 0)
    governed_types = sorted(data.get("action_types") or [])

    frameworks: list[dict[str, Any]] = []

    # --- ACAP -------------------------------------------------------------
    # Applicable when an approved authorization boundary exists in any form: a
    # reviewed ACAP, a generated ACAP version, or approved capabilities.
    acap_applicable = tool_count > 0 or acap_version_count > 0 or approved > 0
    acap_why: list[str] = []
    acap_why_not: list[str] = []
    if tool_count > 0:
        acap_why.append(f"Reviewed ACAP defines {tool_count} tools with authorization boundaries")
    if acap_version_id:
        acap_why.append(f"ACAP version {acap_version_id} exists for this system")
    if approved > 0:
        acap_why.append(f"{approved} approved capabilities in the authorization boundary")
    if denied > 0:
        acap_why.append(f"{denied} capabilities explicitly denied")
    if not acap_applicable:
        acap_why_not.append("No reviewed ACAP, ACAP version, or approved capability exists")
        if discovered:
            acap_why_not.append(f"{discovered} capabilities discovered but none approved yet")

    if tool_count > 0:
        acap_reason = (
            f"System has {tool_count} tools with authorization boundaries "
            "defined in a reviewed ACAP"
        )
    elif acap_applicable:
        boundary = acap_version_id or "a generated ACAP version"
        acap_reason = (
            f"Approved authorization boundary exists for this system: "
            f"{boundary} with {approved} approved capabilities"
        )
    else:
        acap_reason = "No tools or authorization boundaries discovered"

    if not acap_applicable:
        acap_change = [
            "Approve at least one discovered capability",
            "Generate an ACAP version from reviewed capabilities",
        ]
    else:
        acap_change = []
        if pending:
            acap_change.append(f"Review the {pending} pending capabilities to widen the boundary")
        else:
            acap_change.append("Keep the boundary current by rescanning after code changes")
        acap_change.append(
            "Add argument policies so approved capabilities are constrained, not just allowed"
        )

    frameworks.append({
        "framework": "ACAP",
        "applicable": acap_applicable,
        "reason": acap_reason,
        "relevance": "Defines allowed/prohibited actions, approval requirements, and content policy",
        "why": acap_why,
        "why_not": acap_why_not,
        "evidence": [
            {"label": "Latest ACAP version", "value": acap_version_id or "none"},
            {"label": "ACAP versions", "value": acap_version_count},
            {"label": "Approved capabilities", "value": approved},
            {"label": "Denied capabilities", "value": denied},
            {"label": "Pending review", "value": pending},
            {"label": "Reviewed ACAP tools", "value": tool_count},
        ],
        "would_change": acap_change,
    })

    # --- OWASP Agentic ----------------------------------------------------
    # Applicable when the system actually exercises tools or external calls --
    # from the ACAP, from discovery, or from observed runtime decisions.
    is_agentic = (
        tool_count > 0
        or len(agents) > 0
        or discovered > 0
        or action_count > 0
        or bool(set(governed_types) & (WRITE_ACTION_TYPES | {"read"}))
    )
    owasp_why: list[str] = []
    owasp_why_not: list[str] = []
    if tool_count > 0:
        owasp_why.append(f"ACAP declares {tool_count} tools")
    if discovered > 0:
        owasp_why.append(f"{discovered} tool/API capabilities discovered by the scanner")
    if action_count > 0:
        owasp_why.append(f"{action_count} governed actions recorded at runtime")
    if denied_actions > 0:
        owasp_why.append(f"{denied_actions} actions were denied by policy")
    if kill_switches > 0:
        owasp_why.append(f"{kill_switches} kill switches configured")
    if governed_types:
        owasp_why.append("Observed action types: " + ", ".join(governed_types))
    if not is_agentic:
        owasp_why_not.append("No tools, capabilities, or runtime actions observed")

    if tool_count > 0:
        owasp_reason = (
            f"System uses {tool_count} tools with agentic execution"
            + (" via LangGraph" if has_langgraph else "")
        )
    elif is_agentic:
        owasp_reason = (
            "Governed tool/API behavior detected through discovered capabilities "
            "and runtime action decisions"
        )
    else:
        owasp_reason = "No agentic behavior discovered"

    frameworks.append({
        "framework": "OWASP Agentic",
        "applicable": is_agentic,
        "reason": owasp_reason,
        "relevance": "Covers prompt injection, tool misuse, excessive agency, and insecure output handling",
        "why": owasp_why,
        "why_not": owasp_why_not,
        "evidence": [
            {"label": "Discovered capabilities", "value": discovered},
            {"label": "Governed actions", "value": action_count},
            {"label": "Denied actions", "value": denied_actions},
            {"label": "Kill switches", "value": kill_switches},
            {"label": "Action types", "value": ", ".join(governed_types) or "none"},
        ],
        "would_change": (
            ["Run a scan and execute at least one governed action"]
            if not is_agentic
            else [
                "Add argument policies to constrain tool inputs",
                "Exercise an injection scenario to test excessive agency",
            ]
        ),
    })

    # --- NIST AI RMF ------------------------------------------------------
    frameworks.append({
        "framework": "NIST AI RMF",
        "applicable": True,
        "reason": "Applies as general AI risk-management guidance regardless of deployment scope",
        "relevance": "GOVERN, MAP, MEASURE, MANAGE functions for AI risk lifecycle",
        "why": ["Applies to any AI system as general risk-management guidance"],
        "why_not": [],
        "evidence": [
            {"label": "Authority level", "value": authority or "unknown"},
            {"label": "Data sensitivity", "value": sensitivity or "unknown"},
            {"label": "Governed actions", "value": action_count},
        ],
        "would_change": ["Not conditional -- always applicable as guidance"],
    })

    # --- EU AI Act --------------------------------------------------------
    # Applicability is driven by declared context -- jurisdiction and high-risk
    # classification -- never by runtime controls. A kill switch is evidence
    # *within* a review, not a trigger for one.
    eu_jurisdiction = (
        isinstance(jurisdiction, str) and "eu" in jurisdiction.lower() if jurisdiction else False
    )
    declared_high_risk = bool(declared.get("high_risk_category"))
    derived_high_risk = authority == "autonomous" or sensitivity == "high"
    eu_high_risk = declared_high_risk or derived_high_risk
    eu_applicable = eu_jurisdiction and eu_high_risk

    eu_why: list[str] = []
    eu_why_not: list[str] = []
    eu_evidence: list[dict[str, Any]] = [
        {"label": "Jurisdiction", "value": jurisdiction or "not declared"},
        {"label": "High-risk category declared", "value": declared_high_risk},
        {"label": "Environment", "value": environment or "unknown"},
        {"label": "Authority level", "value": authority or "unknown"},
        {"label": "Data sensitivity", "value": sensitivity or "unknown"},
    ]

    if eu_applicable:
        reason = (
            "EU jurisdiction declared and high-risk classification enabled "
            f"for a governed system with {authority} authority"
        )
        eu_why.append("EU jurisdiction declared in assessment inputs")
        if declared_high_risk:
            eu_why.append("High-risk category enabled in assessment inputs")
        if derived_high_risk:
            eu_why.append(
                f"Derived high-risk signal: authority is {authority}, "
                f"data sensitivity is {sensitivity}"
            )
        if declared.get("use_case"):
            eu_why.append(f"Declared use case: {declared['use_case']}")
        if action_count:
            eu_why.append(f"Autonomous/governed actions exist ({action_count} recorded)")
        if acap_version_id or approved:
            eu_why.append("Runtime authorization boundary and evidence exist")

        eu_evidence.extend([
            {"label": "Latest ACAP version", "value": acap_version_id or "none"},
            {"label": "Approved capabilities", "value": approved},
            {"label": "Governed actions", "value": action_count},
            {"label": "Kill switches", "value": kill_switches},
        ])

        # Runtime control evidence, attached only once the framework already
        # applies. This never influenced the decision above.
        control_evidence = list(data.get("runtime_control_evidence") or [])
        eu_entry_extra = {"runtime_control_evidence": control_evidence}
        would_change = [
            "Add a human-reviewed purpose/use-case annotation",
            "Add control mappings for the declared high-risk category",
            "Raise evidence coverage confidence",
            "Add a human approval workflow where approval is required",
        ]
    else:
        parts = []
        if not eu_jurisdiction:
            parts.append(f"{environment or 'unknown'} environment with no EU jurisdiction declared")
            eu_why_not.append(
                f"Jurisdiction is not declared as EU (currently {jurisdiction or 'not set'})"
            )
            if environment:
                eu_why_not.append(f"Environment is {environment}")
        if not eu_high_risk:
            parts.append("not classified as high-risk")
            eu_why_not.append(
                "High-risk category is not enabled, and no high-risk signal was derived "
                f"(authority {authority or 'unknown'}, data sensitivity {sensitivity or 'unknown'})"
            )
        reason = "; ".join(parts).capitalize()
        eu_entry_extra = {}
        would_change = [
            "Set jurisdiction to EU in Assessment Inputs",
            "Enable the high-risk category in Assessment Inputs",
            "Re-run the assessment",
        ]

    frameworks.append({
        "framework": "EU AI Act",
        "applicable": eu_applicable,
        "reason": reason,
        "relevance": "Mandatory requirements for high-risk AI systems deployed in EU jurisdiction",
        "why": eu_why,
        "why_not": eu_why_not,
        "evidence": eu_evidence,
        "would_change": would_change,
        **eu_entry_extra,
    })

    # --- ISO/IEC 42001 ----------------------------------------------------
    frameworks.append({
        "framework": "ISO/IEC 42001",
        "applicable": "informational",
        "reason": "Supporting management-system evidence; does not constitute certification",
        "relevance": "AI management system standard for organizational controls and risk assessment",
        "why": ["Evidence here supports an AI management system, but is not certification"],
        "why_not": [],
        "evidence": [
            {"label": "Assessment evidence", "value": "coverage, findings, ACAP versions"},
        ],
        "would_change": ["Certification requires an external audit, out of scope for this tool"],
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
        elif name == "EU AI Act":
            # Newly applicable through declared inputs: a person must review it.
            status = "needs_review"
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
