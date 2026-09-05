"""Generate a Markdown governance assessment report.

Assembles existing data into a structured document.
Does not expose raw prompts, responses, or adversarial text.
Does not constitute legal certification.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _val(obj: Any) -> Any:
    if isinstance(obj, dict) and "value" in obj:
        return obj["value"]
    return obj


def generate_report(
    system_id: str,
    acap: dict[str, Any],
    assessment: dict[str, Any] | None,
    coverage_fields: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    risk_profile: dict[str, Any],
    applicability: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    system = acap.get("system") or {}
    acap_id = acap.get("acap_id", "unknown")
    acap_status = acap.get("status", "unknown")

    # ── Title ──
    lines.append(f"# AI Governance Assessment Report")
    lines.append("")
    lines.append(f"**System:** {system_id}  ")
    lines.append(f"**Generated:** {now}  ")
    if assessment:
        lines.append(f"**Assessment ID:** {assessment.get('assessment_id', '-')}  ")
        lines.append(f"**Overall Status:** {assessment.get('overall_status', '-')}  ")
    lines.append("")

    # ── Executive Summary ──
    lines.append("## Executive Summary")
    lines.append("")
    finding_count = len(findings)
    high_count = sum(1 for f in findings if f.get("severity") == "high")
    failed_controls = []
    for f in findings:
        ctrl = f.get("failed_control")
        if ctrl and ctrl not in failed_controls:
            failed_controls.append(ctrl)
    if assessment:
        confidence = assessment.get("evidence_confidence", "unknown")
        status = assessment.get("overall_status", "unknown")
        lines.append(
            f"This assessment evaluated **{system_id}** and determined an overall governance status "
            f"of **{status}**. Evidence confidence is **{confidence}**. "
            f"There {'is' if finding_count == 1 else 'are'} **{finding_count}** open finding{'s' if finding_count != 1 else ''}"
            f"{f', including **{high_count}** high-severity' if high_count else ''}"
            f", and **{len(failed_controls)}** failed control{'s' if len(failed_controls) != 1 else ''}."
        )
    else:
        lines.append(f"No assessment has been run for {system_id}. Run an assessment to generate findings.")
    lines.append("")

    # ── System Profile ──
    lines.append("## System Profile")
    lines.append("")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| System ID | {system_id} |")
    lines.append(f"| Deployment | {system.get('deployment_id', '-')} |")
    lines.append(f"| Environment | {system.get('environment', '-')} |")
    lines.append(f"| Purpose | {_val(system.get('purpose')) or '-'} |")
    lines.append(f"| Owner | {_val(system.get('owner')) or '-'} |")
    lines.append("")

    # ── Risk Profile ──
    lines.append("## Risk Profile")
    lines.append("")
    lines.append(f"| Dimension | Value |")
    lines.append(f"|-----------|-------|")
    for key in ["use_case", "environment", "authority_level", "autonomy_level",
                 "data_sensitivity", "external_side_effects", "human_approval_model", "jurisdiction"]:
        val = risk_profile.get(key)
        display = str(val) if val is not None else "none"
        label = key.replace("_", " ").title()
        lines.append(f"| {label} | {display} |")
    lines.append("")

    # ── ACAP Summary ──
    lines.append("## Reviewed ACAP Summary")
    lines.append("")
    lines.append(f"- **ACAP ID:** {acap_id}")
    lines.append(f"- **Status:** {acap_status}")
    reviewed_by = _val(acap.get("reviewed_by"))
    if reviewed_by:
        lines.append(f"- **Reviewed by:** {reviewed_by}")
    reviewed_at = acap.get("reviewed_at")
    if reviewed_at:
        lines.append(f"- **Reviewed at:** {reviewed_at}")
    content_policy = acap.get("content_policy") or {}
    lines.append(f"- **Raw prompts captured:** {content_policy.get('raw_prompts', False)}")
    lines.append(f"- **Raw outputs captured:** {content_policy.get('raw_outputs', False)}")
    tools = acap.get("tools") or []
    approval_tools = [
        t.get("name") for t in tools
        if _val((t.get("approval") or {}).get("required")) is True
    ]
    if approval_tools:
        lines.append(f"- **Approval-required tools:** {', '.join(t for t in approval_tools if t)}")
    prohibited = (acap.get("prohibited_actions") or {}).get("items") or []
    if prohibited:
        lines.append(f"- **Prohibited actions:** {len(prohibited)}")
    lines.append("")

    # ── Evidence Coverage ──
    lines.append("## Evidence Coverage")
    lines.append("")
    if coverage_fields:
        lines.append("| Field | Status | Presence |")
        lines.append("|-------|--------|----------|")
        for field in coverage_fields:
            presence = f"{field['presence'] * 100:.1f}%" if field.get("presence") is not None else "-"
            lines.append(f"| {field['field']} | {field['status']} | {presence} |")
    else:
        lines.append("No evidence coverage data available.")
    lines.append("")

    # ── Findings ──
    lines.append("## Findings")
    lines.append("")
    if not findings:
        lines.append("No findings.")
    else:
        for i, finding in enumerate(findings, 1):
            lines.append(f"### Finding {i}: {finding.get('finding_id', '-')}")
            lines.append("")
            lines.append(f"- **Severity:** {finding.get('severity', '-')}")
            lines.append(f"- **Rule:** {finding.get('rule_id', '-')}")
            if finding.get("violates"):
                lines.append(f"- **Violates:** {finding['violates']}")
            lines.append(f"- **Session:** {finding.get('session', '-')}")
            lines.append("")
            desc = finding.get("description", "")
            if desc:
                lines.append(f"**What happened:** {desc}")
                lines.append("")

            # Failed control
            ctrl = finding.get("failed_control")
            ctrl_title = finding.get("failed_control_title")
            if ctrl:
                lines.append(f"**Failed Control:** {ctrl}")
                if ctrl_title:
                    lines.append(f"  {ctrl_title}")
                lines.append("")

            # Framework mappings
            mappings = finding.get("framework_mappings") or {}
            if mappings:
                lines.append("**Framework Mappings:**")
                lines.append("")
                fw_labels = {"ACAP": "ACAP", "NIST_AI_RMF": "NIST AI RMF",
                             "EU_AI_Act": "EU AI Act", "ISO_42001": "ISO/IEC 42001"}
                for key, mapping in mappings.items():
                    label = fw_labels.get(key, key)
                    parts = [f"{k}: {v}" for k, v in mapping.items() if k != "note"]
                    lines.append(f"- **{label}:** {'; '.join(parts)}")
                    if mapping.get("note"):
                        lines.append(f"  *{mapping['note']}*")
                lines.append("")

            # Linked event IDs
            event_ids = finding.get("event_ids") or []
            if event_ids:
                lines.append(f"**Linked Evidence:** {', '.join(f'`{eid}`' for eid in event_ids)}")
                lines.append("")
    lines.append("")

    # ── Framework Applicability ──
    lines.append("## Framework Applicability")
    lines.append("")
    if applicability:
        lines.append("| Framework | Applicable | Reason |")
        lines.append("|-----------|------------|--------|")
        for fw in applicability:
            applicable = fw.get("applicable")
            display = "Yes" if applicable is True else "No" if applicable is False else str(applicable)
            lines.append(f"| {fw['framework']} | {display} | {fw.get('reason', '-')} |")
    lines.append("")

    # ── Framework Status ──
    if assessment and assessment.get("framework_status"):
        lines.append("## Framework Status")
        lines.append("")
        lines.append("| Framework | Status |")
        lines.append("|-----------|--------|")
        for fw in assessment["framework_status"]:
            lines.append(f"| {fw['framework']} | {fw['status']} |")
        lines.append("")

    # ── Recommended Actions ──
    if assessment and assessment.get("recommended_next_actions"):
        lines.append("## Recommended Actions")
        lines.append("")
        for action in assessment["recommended_next_actions"]:
            lines.append(f"- {action}")
        lines.append("")

    # ── Limitations ──
    lines.append("## Limitations")
    lines.append("")
    lines.append("- This report is generated from automated evidence collection and deterministic rule evaluation.")
    lines.append("- It does not constitute legal compliance certification.")
    lines.append("- Framework references are informational and require human review for applicability determination.")
    lines.append("- EU AI Act references note potential relevance only; applicability depends on jurisdiction and risk classification.")
    lines.append("- ISO/IEC 42001 references are supporting management-system evidence, not certification.")
    lines.append("- Raw prompts, responses, and sensitive data are not included in this report.")
    lines.append("")
    lines.append("---")
    lines.append(f"*Report generated by AI Governance Command Center at {now}*")
    lines.append("")

    return "\n".join(lines)
