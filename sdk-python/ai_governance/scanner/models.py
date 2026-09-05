from __future__ import annotations

from typing import Any

from ai_governance.core.fingerprint import fingerprint

SCANNER_VERSION = "0.1.0"


def build_candidate(
    *,
    name: str,
    module_path: str,
    file_path: str,
    line_start: int,
    line_end: int,
    suggested_action_type: str,
    suggested_data_classes: list[str],
    suggested_approval_required: bool,
    external_side_effect: bool,
    risk: str,
    confidence: float,
    confidence_source: str,
    evidence: list[dict[str, Any]],
    call_chain: list[str],
) -> dict[str, Any]:
    """Build a candidate capability dict with a deterministic capability_id."""
    canonical = f"{module_path}.{name}"
    cap_hash = fingerprint(canonical).removeprefix("sha256:")[:12]
    return {
        "capability_id": f"CAP-{cap_hash}",
        "name": name,
        "module_path": module_path,
        "file_path": file_path,
        "line_start": line_start,
        "line_end": line_end,
        "suggested_action_type": suggested_action_type,
        "suggested_data_classes": sorted(set(suggested_data_classes)),
        "suggested_approval_required": suggested_approval_required,
        "external_side_effect": external_side_effect,
        "risk": risk,
        "confidence": round(confidence, 2),
        "confidence_source": confidence_source,
        "evidence": evidence,
        "call_chain": call_chain,
        "review_status": "pending",
        "source": "deterministic_scanner",
    }


def build_model_surface_entry(
    *,
    name: str,
    module_path: str,
    file_path: str,
    line: int,
    provider: str,
    call_chain: list[str],
) -> dict[str, Any]:
    """Build a model-usage surface entry (not a governed capability)."""
    return {
        "name": name,
        "module_path": module_path,
        "file_path": file_path,
        "line": line,
        "provider": provider,
        "call_chain": call_chain,
        "category": "model_usage",
    }


def build_evidence(
    *,
    evidence_type: str,
    detail: str,
    line: int,
    file_path: str | None = None,
) -> dict[str, Any]:
    """Build an evidence entry."""
    entry: dict[str, Any] = {
        "type": evidence_type,
        "detail": detail,
        "line": line,
    }
    if file_path is not None:
        entry["file_path"] = file_path
    return entry


def build_scan_summary(
    *,
    files_scanned: int,
    functions_seen: int,
    candidates: list[dict[str, Any]],
    model_surface: list[dict[str, Any]],
    ignored_helpers_count: int,
    unenumerated_surface: list[str] | None = None,
) -> dict[str, Any]:
    """Build the scan_summary section."""
    high = sum(1 for c in candidates if c.get("risk") == "high")
    medium = sum(1 for c in candidates if c.get("risk") == "medium")
    low = sum(1 for c in candidates if c.get("risk") == "low")
    return {
        "files_scanned": files_scanned,
        "functions_seen": functions_seen,
        "candidates_found": len(candidates),
        "model_surface_found": len(model_surface),
        "high_risk_count": high,
        "medium_risk_count": medium,
        "low_risk_count": low,
        "ignored_helpers_count": ignored_helpers_count,
        "unenumerated_surface": unenumerated_surface or [],
    }
