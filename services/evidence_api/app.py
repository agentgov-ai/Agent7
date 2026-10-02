from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from starlette.staticfiles import StaticFiles
import yaml

from . import db
from .coverage import compute_field_coverage
from .draft import build_draft_from_db_events
from .enforcement import ENFORCEMENT_MODES, evaluate_action, resolve_enforcement_mode
from .report import generate_report
from .risk import build_assessment, build_full_assessment, build_risk_profile, evaluate_framework_applicability
from .rules import run_r1_confirm_without_proposal, run_rules_for_system, run_all_acap_rules
from .validation import public_event, validate_event

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSONL = REPO_ROOT / "artifacts" / "governance" / "events.jsonl"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "governance" / "scenarios" / "manifest.json"
DEFAULT_REVIEWED_ACAP = REPO_ROOT / "artifacts" / "governance" / "acap-reviewed.yaml"
DEMO_DATA_DIR = REPO_ROOT / "examples" / "demo-data"
GOVERNANCE_EVENT_SCHEMA = REPO_ROOT / "schemas" / "governance-event.schema.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"
PRODUCT_DIR = Path(__file__).resolve().parent / "product"
DEFAULT_RULE_IDS = ["R1_confirm_without_proposal"]

SYSTEM_REGISTRY: dict[str, dict[str, Path]] = {
    "restaurant-agent": {
        "acap": DEMO_DATA_DIR / "restaurant-agent" / "acap-reviewed.yaml",
        "events": DEMO_DATA_DIR / "restaurant-agent" / "events.jsonl",
    },
    "customer-refund-agent": {
        "acap": DEMO_DATA_DIR / "customer-refund-agent" / "acap-reviewed.yaml",
        "events": DEMO_DATA_DIR / "customer-refund-agent" / "events.jsonl",
    },
    "custom-python-refund-agent": {
        "acap": DEMO_DATA_DIR / "custom-python-tool" / "acap-reviewed.yaml",
        "events": DEMO_DATA_DIR / "custom-python-tool" / "events.jsonl",
    },
    "openai-direct-agent": {
        "acap": DEMO_DATA_DIR / "openai-direct" / "acap-reviewed.yaml",
        "events": DEMO_DATA_DIR / "openai-direct" / "events.jsonl",
    },
    "anthropic-direct-agent": {
        "acap": DEMO_DATA_DIR / "anthropic-direct" / "acap-reviewed.yaml",
        "events": DEMO_DATA_DIR / "anthropic-direct" / "events.jsonl",
    },
    "support-api": {
        "acap": DEMO_DATA_DIR / "fastapi-app" / "acap-reviewed.yaml",
        "events": DEMO_DATA_DIR / "fastapi-app" / "events.jsonl",
    },
}

app = FastAPI(title="Evidence Ingestion API", version="0.1")
app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
app.mount("/product", StaticFiles(directory=PRODUCT_DIR, html=True), name="product")


class EventIngestRequest(BaseModel):
    event: dict[str, Any] | None = None
    events: list[dict[str, Any]] | None = None
    session_ref: str | None = None


class ReplayRequest(BaseModel):
    path: str | None = None
    reset: bool = True
    use_manifest_sessions: bool = True


class RulesRunRequest(BaseModel):
    rule_ids: list[str] = Field(default_factory=lambda: DEFAULT_RULE_IDS.copy())


VALID_AUTHORIZATIONS = {"allowed", "prohibited", "allowed_conditional", "allowed_with_approval"}


class ToolReviewDecision(BaseModel):
    tool_name: str
    authorization: str
    basis: str | None = None
    condition: str | None = None
    approval_required: bool | None = None


class AcapReviewRequest(BaseModel):
    reviewed_by: str
    decisions: list[ToolReviewDecision]


class DiscoveryUploadRequest(BaseModel):
    system_id: str
    discovery: dict[str, Any]


class CapabilityEditRequest(BaseModel):
    action_type: str | None = None
    data_classes: list[str] | None = None
    approval_required: bool | None = None
    external_side_effect: bool | None = None
    risk: str | None = None
    reviewer: str = "local_user"


class ActionEvaluateRequest(BaseModel):
    action: dict[str, Any]


class ActionRecordRequest(BaseModel):
    record: dict[str, Any]


class KillSwitchCreateRequest(BaseModel):
    kill_switch_id: str
    target_capabilities: list[str] = Field(default_factory=list)
    enabled: bool = True
    verdict: str = "DENY"
    reason: str | None = None
    created_by: str = "local_user"


class KillSwitchPatchRequest(BaseModel):
    enabled: bool | None = None
    target_capabilities: list[str] | None = None
    verdict: str | None = None
    reason: str | None = None


class EnforcementModePatchRequest(BaseModel):
    # None clears the override, so the mode the SDK sends applies again.
    mode: str | None = None
    updated_by: str = "local_user"


def _value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _load_reviewed_acap(system_id: str | None = None) -> dict[str, Any]:
    if system_id and system_id in SYSTEM_REGISTRY:
        path = SYSTEM_REGISTRY[system_id]["acap"]
    else:
        path = DEFAULT_REVIEWED_ACAP
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"reviewed ACAP not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _validate_system(system_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load ACAP and validate system_id. Returns (acap, system_record)."""
    if system_id in SYSTEM_REGISTRY:
        acap = _load_reviewed_acap(system_id)
        return acap, _system_record(acap)
    # Check if the system exists in the database (discovery/events/acap)
    conn = db.connect()
    try:
        known = db.list_known_system_ids(conn)
    finally:
        conn.close()
    if system_id in known:
        # DB-discovered system — return minimal record
        return {}, {"system_id": system_id, "source": "discovery"}
    raise HTTPException(status_code=404, detail=f"system not found: {system_id}")


def _system_record(acap: dict[str, Any]) -> dict[str, Any]:
    system = acap.get("system") or {}
    return {
        "system_id": system.get("system_id"),
        "deployment_id": system.get("deployment_id"),
        "environment": system.get("environment"),
        "purpose": _value(system.get("purpose")),
        "owner": _value(system.get("owner")),
        "acap_id": acap.get("acap_id"),
        "acap_status": acap.get("status"),
        "reviewed_at": acap.get("reviewed_at"),
    }


def _acap_summary(acap: dict[str, Any]) -> dict[str, Any]:
    prohibited = ((acap.get("prohibited_actions") or {}).get("items") or [])
    tools = acap.get("tools") or []
    approval_tools = [
        tool.get("name")
        for tool in tools
        if _value(((tool.get("approval") or {}).get("required") or {})) is True
    ]
    return {
        "acap_id": acap.get("acap_id"),
        "status": acap.get("status"),
        "reviewed_at": acap.get("reviewed_at"),
        "reviewed_by": _value(acap.get("reviewed_by")),
        "prohibited_action_count": len(prohibited),
        "approval_required_tools": [name for name in approval_tools if name],
        "content_policy": acap.get("content_policy") or {},
        "contract": {
            "governance_event_schema": str(GOVERNANCE_EVENT_SCHEMA.relative_to(REPO_ROOT)),
        },
    }


def _manifest_session_lookup() -> dict[int, str]:
    if not DEFAULT_MANIFEST.exists():
        return {}
    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    lookup: dict[int, str] = {}
    for run in manifest.get("runs", []):
        if run.get("mode") != "instrumented":
            continue
        session_ref = f"{run['scenario']} [{run['started_utc']}] lines {run['events_line_start']}-{run['events_line_end']}"
        for zero_based in range(int(run["events_line_start"]), int(run["events_line_end"])):
            lookup[zero_based + 1] = session_ref
    return lookup


def _ingest_events(
    events: list[dict[str, Any]],
    *,
    session_ref: str | None = None,
    jsonl_lines: list[int | None] | None = None,
) -> dict[str, Any]:
    accepted = 0
    duplicates = 0
    rejected: list[dict[str, Any]] = []
    conn = db.connect()
    try:
        for index, event in enumerate(events):
            problems = validate_event(event)
            line = (jsonl_lines or [None] * len(events))[index]
            if problems:
                rejected.append(
                    {
                        "index": index,
                        "jsonl_line": line,
                        "event_id": event.get("event_id") if isinstance(event, dict) else None,
                        "errors": problems,
                    }
                )
                continue
            inserted = db.insert_event(conn, event, session_ref=session_ref, jsonl_line=line)
            if inserted:
                accepted += 1
            else:
                duplicates += 1
    finally:
        conn.close()
    return {"accepted": accepted, "duplicates": duplicates, "rejected": rejected}


@app.get("/health")
def health() -> dict[str, Any]:
    conn = db.connect()
    try:
        return {"ok": True, "events": db.event_count(conn), "database": str(db.db_path())}
    finally:
        conn.close()


@app.get("/systems")
def list_systems() -> dict[str, Any]:
    systems = []
    seen: set[str] = set()
    for sid in SYSTEM_REGISTRY:
        try:
            acap = _load_reviewed_acap(sid)
            systems.append(_system_record(acap))
            seen.add(sid)
        except HTTPException:
            pass
    # Add DB-discovered systems not in registry
    conn = db.connect()
    try:
        db_ids = db.list_known_system_ids(conn)
    finally:
        conn.close()
    for sid in sorted(db_ids - seen):
        systems.append({"system_id": sid, "source": "discovery"})
    return {"count": len(systems), "systems": systems}


@app.get("/systems/{system_id}")
def get_system(system_id: str) -> dict[str, Any]:
    acap, system = _validate_system(system_id)
    return system


@app.get("/systems/{system_id}/acap")
def get_system_acap(system_id: str) -> dict[str, Any]:
    acap, system = _validate_system(system_id)
    return {"system": system, "acap": _acap_summary(acap)}


@app.get("/systems/{system_id}/acap/draft")
def get_acap_draft(system_id: str) -> dict[str, Any]:
    acap, system = _validate_system(system_id)
    conn = db.connect()
    try:
        events = db.all_events_for_system(conn, system_id)
    finally:
        conn.close()
    return build_draft_from_db_events(events, system_id)


@app.get("/systems/{system_id}/acap/reviewed")
def get_acap_reviewed(system_id: str) -> dict[str, Any]:
    acap, system = _validate_system(system_id)
    conn = db.connect()
    try:
        decisions = db.list_review_decisions(conn, system_id)
    finally:
        conn.close()
    if not decisions:
        return acap
    reviewed = dict(acap)
    decision_map: dict[str, dict[str, dict[str, Any]]] = {}
    for d in decisions:
        decision_map.setdefault(d["tool_name"], {})[d["field"]] = d
    tools = []
    for tool in reviewed.get("tools", []):
        tool = dict(tool)
        name = tool.get("name")
        if name in decision_map:
            if "authorization" in decision_map[name]:
                d = decision_map[name]["authorization"]
                tool["authorization"] = {
                    "value": d["value"],
                    "provenance": "human_decision",
                    "basis": d.get("basis"),
                    **({"condition": d["condition"]} if d.get("condition") else {}),
                }
            if "approval_required" in decision_map[name]:
                d = decision_map[name]["approval_required"]
                approval = dict(tool.get("approval") or {})
                approval["required"] = {
                    "value": d["value"] == "true",
                    "provenance": "human_decision",
                    "basis": d.get("basis"),
                }
                tool["approval"] = approval
        tools.append(tool)
    reviewed["tools"] = tools
    return reviewed


@app.post("/systems/{system_id}/acap/review")
def post_acap_review(system_id: str, request: AcapReviewRequest) -> dict[str, Any]:
    _validate_system(system_id)
    invalid = [d.authorization for d in request.decisions if d.authorization not in VALID_AUTHORIZATIONS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"invalid authorization values: {invalid}")
    conn = db.connect()
    stored = 0
    try:
        for d in request.decisions:
            db.insert_review_decision(
                conn, system_id, d.tool_name, "authorization",
                d.authorization, d.basis, d.condition, request.reviewed_by,
            )
            stored += 1
            if d.approval_required is not None:
                db.insert_review_decision(
                    conn, system_id, d.tool_name, "approval_required",
                    str(d.approval_required).lower(), d.basis, None, request.reviewed_by,
                )
                stored += 1
    finally:
        conn.close()
    return {
        "system_id": system_id,
        "decisions_stored": stored,
        "reviewed_by": request.reviewed_by,
    }


@app.get("/systems/{system_id}/coverage")
def get_coverage(system_id: str) -> dict[str, Any]:
    _validate_system(system_id)
    conn = db.connect()
    try:
        events = db.all_events_for_system(conn, system_id)
    finally:
        conn.close()
    fields = compute_field_coverage(events)
    return {"system_id": system_id, "event_count": len(events), "fields": fields}


@app.get("/systems/{system_id}/risk-profile")
def get_risk_profile(system_id: str) -> dict[str, Any]:
    acap, system = _validate_system(system_id)
    profile = build_risk_profile(acap)
    return {"system_id": system_id, "risk_profile": profile}


@app.get("/systems/{system_id}/framework-applicability")
def get_framework_applicability(system_id: str) -> dict[str, Any]:
    acap, system = _validate_system(system_id)
    profile = build_risk_profile(acap)
    frameworks = evaluate_framework_applicability(profile, acap)
    return {"system_id": system_id, "frameworks": frameworks}


@app.get("/systems/{system_id}/assessment")
def get_assessment(system_id: str) -> dict[str, Any]:
    acap, system = _validate_system(system_id)
    profile = build_risk_profile(acap)
    applicability = evaluate_framework_applicability(profile, acap)
    conn = db.connect()
    try:
        events = db.all_events_for_system(conn, system_id)
        findings = db.list_findings(conn, system_id=system_id)
    finally:
        conn.close()
    coverage_fields = compute_field_coverage(events)
    return build_assessment(
        system_id, acap, findings, coverage_fields,
        len(events), profile, applicability,
    )


@app.post("/systems/{system_id}/assessments/run")
def run_assessment(system_id: str) -> dict[str, Any]:
    acap, system = _validate_system(system_id)
    profile = build_risk_profile(acap)
    applicability = evaluate_framework_applicability(profile, acap)
    conn = db.connect()
    try:
        events = db.all_events_for_system(conn, system_id)
        findings = db.list_findings(conn, system_id=system_id)
        coverage_fields = compute_field_coverage(events)
        assessment = build_full_assessment(
            system_id, acap, findings, coverage_fields,
            len(events), profile, applicability,
        )
        db.insert_assessment(conn, assessment)
    finally:
        conn.close()
    return assessment


@app.get("/systems/{system_id}/assessments")
def list_assessments(system_id: str) -> dict[str, Any]:
    _validate_system(system_id)
    conn = db.connect()
    try:
        items = db.list_assessments(conn, system_id)
    finally:
        conn.close()
    return {"count": len(items), "assessments": items}


@app.get("/assessments/{assessment_id}")
def get_assessment_by_id(assessment_id: str) -> dict[str, Any]:
    conn = db.connect()
    try:
        result = db.get_assessment_by_id(conn, assessment_id)
    finally:
        conn.close()
    if result is None:
        raise HTTPException(status_code=404, detail=f"assessment not found: {assessment_id}")
    return result


@app.get("/systems/{system_id}/assessment-report.md")
def get_assessment_report(system_id: str):
    from starlette.responses import Response
    acap, system = _validate_system(system_id)
    profile = build_risk_profile(acap)
    applicability = evaluate_framework_applicability(profile, acap)
    conn = db.connect()
    try:
        events = db.all_events_for_system(conn, system_id)
        findings = db.list_findings(conn, system_id=system_id)
        assessments = db.list_assessments(conn, system_id)
        assessment = None
        if assessments:
            assessment = db.get_assessment_by_id(conn, assessments[0]["assessment_id"])
    finally:
        conn.close()
    coverage_fields = compute_field_coverage(events)
    md = generate_report(system_id, acap, assessment, coverage_fields,
                         findings, profile, applicability)
    return Response(content=md, media_type="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="{system_id}-assessment-report.md"'})


@app.post("/demo/reset")
def demo_reset() -> dict[str, Any]:
    """Clear DB, replay evidence for all systems, run rules, run assessments."""
    conn = db.connect()
    try:
        db.reset_db(conn)
    finally:
        conn.close()
    total_events = 0
    total_findings = 0
    assessments: list[dict[str, Any]] = []
    for system_id, reg in SYSTEM_REGISTRY.items():
        events_path = reg.get("events")
        if events_path and events_path.exists():
            result = replay_jsonl(ReplayRequest(
                path=str(events_path), reset=False, use_manifest_sessions=True,
            ))
            total_events += result.get("accepted", 0)
        # Run rules for this system
        acap = _load_reviewed_acap(system_id)
        acap_id = acap.get("acap_id", "unknown")
        conn = db.connect()
        try:
            events = db.all_events_for_system(conn, system_id)
            system_findings = run_rules_for_system(events, system_id, acap_id=acap_id)
            db.insert_findings(conn, system_findings, system_id=system_id)
            total_findings += len(system_findings)
            # Run assessment
            profile = build_risk_profile(acap)
            applicability = evaluate_framework_applicability(profile, acap)
            findings = db.list_findings(conn, system_id=system_id)
            coverage_fields = compute_field_coverage(events)
            assessment = build_full_assessment(
                system_id, acap, findings, coverage_fields,
                len(events), profile, applicability,
            )
            db.insert_assessment(conn, assessment)
            assessments.append({"system_id": system_id, "assessment_id": assessment["assessment_id"],
                                "overall_status": assessment["overall_status"]})
        finally:
            conn.close()
    return {
        "events_replayed": total_events,
        "findings_created": total_findings,
        "systems": len(assessments),
        "assessments": assessments,
    }


@app.post("/evidence/events")
def post_events(request: EventIngestRequest) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    if request.event is not None:
        events.append(request.event)
    if request.events is not None:
        events.extend(request.events)
    if not events:
        raise HTTPException(status_code=400, detail="provide event or events")
    result = _ingest_events(events, session_ref=request.session_ref)
    if result["rejected"]:
        raise HTTPException(status_code=422, detail=result)
    return {"stored_total": result["accepted"], **result}


@app.post("/evidence/replay-jsonl")
def replay_jsonl(request: ReplayRequest) -> dict[str, Any]:
    path = Path(request.path) if request.path else DEFAULT_JSONL
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"JSONL file not found: {path}")
    if request.reset:
        conn = db.connect()
        try:
            db.reset_db(conn)
        finally:
            conn.close()
    session_lookup = _manifest_session_lookup() if request.use_manifest_sessions else {}
    accepted = duplicates = 0
    rejected: list[dict[str, Any]] = []
    conn = db.connect()
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    rejected.append({"jsonl_line": line_number, "errors": [f"invalid JSON: {exc}"]})
                    continue
                problems = validate_event(event)
                if problems:
                    rejected.append({"jsonl_line": line_number, "event_id": event.get("event_id"), "errors": problems})
                    continue
                session_ref = event.get("session_id") or session_lookup.get(line_number) or "jsonl:unscoped"
                inserted = db.insert_event(conn, event, session_ref=session_ref, jsonl_line=line_number)
                if inserted:
                    accepted += 1
                else:
                    duplicates += 1
    finally:
        conn.close()
    return {
        "source": str(path),
        "accepted": accepted,
        "duplicates": duplicates,
        "rejected_count": len(rejected),
        "rejected": rejected,
        "stored_total": accepted + duplicates,
    }


@app.get("/evidence/events")
def get_events(
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    conn = db.connect()
    try:
        events = [public_event(event) for event in db.list_events(conn, limit=limit, offset=offset)]
        return {"count": len(events), "events": events}
    finally:
        conn.close()


@app.post("/rules/run")
def run_rules(request: RulesRunRequest | None = None) -> dict[str, Any]:
    rule_ids = request.rule_ids if request is not None else DEFAULT_RULE_IDS.copy()
    conn = db.connect()
    try:
        events = db.all_events_for_rules(conn)
        all_findings: list[dict[str, Any]] = []
        for rule_id in rule_ids:
            if rule_id == "R1_confirm_without_proposal":
                all_findings.extend(run_r1_confirm_without_proposal(events))
            else:
                raise HTTPException(status_code=400, detail=f"unsupported rule: {rule_id}")
        db.insert_findings(conn, all_findings, system_id="restaurant-agent")
        return {"rules": rule_ids, "events_evaluated": len(events),
                "findings_created": len(all_findings), "findings": all_findings}
    finally:
        conn.close()


@app.get("/findings")
def get_findings(system_id: str | None = Query(default=None)) -> dict[str, Any]:
    conn = db.connect()
    try:
        findings = db.list_findings(conn, system_id=system_id)
        return {"count": len(findings), "findings": findings}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Discovery / capability review endpoints
# ---------------------------------------------------------------------------

@app.post("/discovery/upload")
def upload_discovery(request: DiscoveryUploadRequest) -> dict[str, Any]:
    discovery = request.discovery
    if "schema_version" not in discovery or "candidates" not in discovery:
        raise HTTPException(status_code=400, detail="discovery must contain schema_version and candidates")
    candidates = discovery.get("candidates", [])
    model_surface = discovery.get("model_surface", [])
    upload_id = str(uuid.uuid4())
    scan_summary = discovery.get("scan_summary", {})
    conn = db.connect()
    try:
        db.insert_discovery_upload(
            conn, upload_id, request.system_id,
            discovery.get("scanner_version"),
            discovery.get("schema_version"),
            discovery.get("project_hash"),
            len(candidates), len(model_surface),
            json.dumps(scan_summary, sort_keys=True, ensure_ascii=False),
            json.dumps(model_surface, sort_keys=True, ensure_ascii=False, default=str),
        )
        stored = db.insert_capabilities(conn, upload_id, request.system_id, candidates)
        # Carry forward review decisions from prior scan
        carried = db.carry_forward_reviews(conn, request.system_id, upload_id)
    finally:
        conn.close()
    return {
        "upload_id": upload_id,
        "system_id": request.system_id,
        "candidates_stored": stored,
        "reviews_carried_forward": carried,
    }


@app.get("/systems/{system_id}/discovery")
def get_system_discovery(system_id: str) -> dict[str, Any]:
    conn = db.connect()
    try:
        result = db.get_discovery(conn, system_id)
        if result is not None:
            changeset = db.compute_discovery_changeset(conn, system_id)
            if changeset:
                result["changeset"] = changeset
    finally:
        conn.close()
    if result is None:
        raise HTTPException(status_code=404, detail=f"no discovery for system: {system_id}")
    return result


def _review_capability(system_id: str, capability_id: str, decision: str, status: str) -> dict[str, Any]:
    """Shared logic for approve / reject / not-a-capability."""
    conn = db.connect()
    try:
        cap = db.get_capability(conn, system_id, capability_id)
        if cap is None:
            raise HTTPException(status_code=404, detail=f"capability not found: {capability_id}")
        previous = json.dumps({"review_status": cap["review_status"]}, sort_keys=True)
        db.update_capability_status(conn, system_id, capability_id, status)
        review_id = str(uuid.uuid4())
        db.insert_capability_review(
            conn, review_id, capability_id, cap["upload_id"], system_id,
            decision, "local_user", previous, None,
            json.dumps(cap.get("evidence", []), sort_keys=True, ensure_ascii=False, default=str),
        )
        cap = db.get_capability(conn, system_id, capability_id)
    finally:
        conn.close()
    return cap  # type: ignore[return-value]


@app.post("/systems/{system_id}/capabilities/{capability_id}/approve")
def approve_capability(system_id: str, capability_id: str) -> dict[str, Any]:
    return _review_capability(system_id, capability_id, "approved_for_acap", "approved_for_acap")


@app.post("/systems/{system_id}/capabilities/{capability_id}/reject")
def reject_capability(system_id: str, capability_id: str) -> dict[str, Any]:
    return _review_capability(system_id, capability_id, "rejected", "rejected")


@app.post("/systems/{system_id}/capabilities/{capability_id}/not-a-capability")
def mark_false_positive(system_id: str, capability_id: str) -> dict[str, Any]:
    return _review_capability(system_id, capability_id, "false_positive", "false_positive")


@app.post("/systems/{system_id}/capabilities/{capability_id}/edit")
def edit_capability(
    system_id: str, capability_id: str, request: CapabilityEditRequest,
) -> dict[str, Any]:
    conn = db.connect()
    try:
        cap = db.get_capability(conn, system_id, capability_id)
        if cap is None:
            raise HTTPException(status_code=404, detail=f"capability not found: {capability_id}")
        updates: dict[str, Any] = {}
        previous: dict[str, Any] = {}
        if request.action_type is not None:
            previous["suggested_action_type"] = cap.get("suggested_action_type")
            updates["suggested_action_type"] = request.action_type
        if request.data_classes is not None:
            previous["suggested_data_classes"] = cap.get("suggested_data_classes")
            updates["suggested_data_classes"] = request.data_classes
        if request.approval_required is not None:
            previous["suggested_approval_required"] = cap.get("suggested_approval_required")
            updates["suggested_approval_required"] = request.approval_required
        if request.external_side_effect is not None:
            previous["external_side_effect"] = cap.get("external_side_effect")
            updates["external_side_effect"] = request.external_side_effect
        if request.risk is not None:
            previous["risk"] = cap.get("risk")
            updates["risk"] = request.risk
        if not updates:
            raise HTTPException(status_code=400, detail="no fields to update")
        updates["review_status"] = "edited"
        db.update_capability_fields(conn, system_id, capability_id, updates)
        review_id = str(uuid.uuid4())
        db.insert_capability_review(
            conn, review_id, capability_id, cap["upload_id"], system_id,
            "edited", request.reviewer,
            json.dumps(previous, sort_keys=True, ensure_ascii=False, default=str),
            json.dumps({k: v for k, v in updates.items() if k != "review_status"},
                       sort_keys=True, ensure_ascii=False, default=str),
            json.dumps(cap.get("evidence", []), sort_keys=True, ensure_ascii=False, default=str),
        )
        cap = db.get_capability(conn, system_id, capability_id)
    finally:
        conn.close()
    return cap  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# ACAP version generation
# ---------------------------------------------------------------------------

def _cap_summary(cap: dict[str, Any]) -> dict[str, Any]:
    """Slim a capability dict for inclusion in an ACAP version."""
    return {
        "capability_id": cap["capability_id"],
        "name": cap["name"],
        "module_path": cap.get("module_path"),
        "file_path": cap.get("file_path"),
        "line_start": cap.get("line_start"),
        "line_end": cap.get("line_end"),
        "suggested_action_type": cap.get("suggested_action_type"),
        "suggested_data_classes": cap.get("suggested_data_classes", []),
        "suggested_approval_required": cap.get("suggested_approval_required"),
        "external_side_effect": cap.get("external_side_effect"),
        "risk": cap.get("risk"),
        "confidence": cap.get("confidence"),
        "confidence_source": cap.get("confidence_source"),
        "evidence": cap.get("evidence", []),
        "review_status": cap.get("review_status"),
    }


@app.post("/systems/{system_id}/acap/generate-from-discovery")
def generate_acap_from_discovery(system_id: str) -> dict[str, Any]:
    from datetime import datetime, timezone

    conn = db.connect()
    try:
        discovery = db.get_discovery(conn, system_id)
        if discovery is None:
            raise HTTPException(status_code=404, detail=f"no discovery for system: {system_id}")

        caps = discovery.get("capabilities", [])
        allowed: list[dict[str, Any]] = []
        denied: list[dict[str, Any]] = []
        pending_ids: list[str] = []
        pending_high_risk: list[str] = []
        false_positive_count = 0

        for cap in caps:
            status = cap.get("review_status", "pending")
            if status in ("approved_for_acap", "edited"):
                allowed.append(_cap_summary(cap))
            elif status == "rejected":
                denied.append(_cap_summary(cap))
            elif status == "false_positive":
                false_positive_count += 1
            else:  # pending or needs_reapproval
                pending_ids.append(cap["capability_id"])
                if cap.get("risk") == "high" or status == "needs_reapproval":
                    pending_high_risk.append(cap["capability_id"])

        reviews = db.list_capability_reviews(conn, system_id)
        version_number = db.next_acap_version_number(conn, system_id)
        now = datetime.now(timezone.utc).isoformat()

        version: dict[str, Any] = {
            "acap_version_id": f"ACAP-{system_id}-v{version_number}",
            "system_id": system_id,
            "version_number": version_number,
            "status": "generated",
            "generated_at": now,
            "generated_from": {
                "upload_id": discovery["upload_id"],
                "scanner_version": discovery.get("scanner_version"),
                "project_hash": discovery.get("project_hash"),
            },
            "allowed_capabilities": allowed,
            "denied_capabilities": denied,
            "unresolved": {
                "pending_count": len(pending_ids),
                "pending_capability_ids": pending_ids,
                "pending_high_risk": pending_high_risk,
            },
            "excluded": {
                "false_positive_count": false_positive_count,
            },
            "model_surface": discovery.get("model_surface", []),
            "review_summary": {
                "total_candidates": len(caps),
                "approved_count": len(allowed),
                "denied_count": len(denied),
                "false_positive_count": false_positive_count,
                "pending_count": len(pending_ids),
                "review_count": len(reviews),
            },
        }

        db.insert_acap_version(conn, version)
    finally:
        conn.close()
    return version


@app.get("/systems/{system_id}/acap/versions")
def list_acap_versions_endpoint(system_id: str) -> dict[str, Any]:
    conn = db.connect()
    try:
        versions = db.list_acap_versions(conn, system_id)
    finally:
        conn.close()
    return {"system_id": system_id, "versions": versions}


@app.get("/systems/{system_id}/acap/versions/{version_id}")
def get_acap_version_endpoint(system_id: str, version_id: str) -> dict[str, Any]:
    conn = db.connect()
    try:
        version = db.get_acap_version(conn, system_id, version_id)
    finally:
        conn.close()
    if version is None:
        raise HTTPException(status_code=404, detail=f"ACAP version not found: {version_id}")
    return version


@app.post("/systems/{system_id}/rules/run-acap")
def run_acap_rules_endpoint(system_id: str) -> dict[str, Any]:
    """Compare runtime evidence against the latest ACAP version."""
    conn = db.connect()
    try:
        versions = db.list_acap_versions(conn, system_id)
        if not versions:
            raise HTTPException(
                status_code=404,
                detail=f"no ACAP version for system: {system_id}",
            )
        latest = versions[0]  # list_acap_versions orders by version_number DESC
        acap_version = db.get_acap_version(conn, system_id, latest["acap_version_id"])
        if acap_version is None:
            raise HTTPException(status_code=404, detail="ACAP version payload missing")

        events = db.all_events_for_system(conn, system_id)
        findings = run_all_acap_rules(events, acap_version)

        if findings:
            db.insert_findings(conn, findings, system_id=system_id)

        return {
            "system_id": system_id,
            "acap_version_id": latest["acap_version_id"],
            "acap_version_number": latest["version_number"],
            "events_evaluated": len(events),
            "findings_created": len(findings),
            "findings": findings,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Governance manifest generation
# ---------------------------------------------------------------------------

def _build_manifest_from_acap(acap_version: dict[str, Any]) -> dict[str, Any]:
    """Build a governance.yaml-compatible manifest from an ACAP version."""
    from datetime import datetime, timezone

    capabilities: list[dict[str, Any]] = []
    for cap in acap_version.get("allowed_capabilities", []):
        module_path = cap.get("module_path")
        if not module_path:
            continue  # skip — no module_path means uninstrumentable
        entry: dict[str, Any] = {
            "capability_id": cap.get("capability_id"),
            "name": cap["name"],
            "module_path": f"{module_path}.{cap['name']}",
            "action_type": cap.get("suggested_action_type") or cap.get("action_type") or "unknown",
            "status": "approved",
        }
        approval = cap.get("suggested_approval_required") or cap.get("approval_required")
        if approval is not None:
            entry["approval_required"] = bool(approval)
        data_classes = cap.get("suggested_data_classes") or cap.get("data_classes")
        if data_classes:
            entry["data_classes"] = list(data_classes)
        side_effect = cap.get("external_side_effect")
        if side_effect is not None:
            entry["external_side_effect"] = bool(side_effect)
        capabilities.append(entry)

    generated_from = acap_version.get("generated_from") or {}
    return {
        "system_id": acap_version["system_id"],
        "generated_from": {
            "acap_version_id": acap_version.get("acap_version_id"),
            "acap_version_number": acap_version.get("version_number"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "evidence_api",
        },
        "capabilities": capabilities,
    }


def _load_acap_for_manifest(
    system_id: str, version_id: str | None,
) -> dict[str, Any]:
    """Load the specified (or latest) ACAP version, or raise 404."""
    conn = db.connect()
    try:
        if version_id:
            acap = db.get_acap_version(conn, system_id, version_id)
            if acap is None:
                raise HTTPException(status_code=404, detail=f"ACAP version not found: {version_id}")
            return acap

        versions = db.list_acap_versions(conn, system_id)
        if not versions:
            raise HTTPException(status_code=404, detail=f"no ACAP version for system: {system_id}")
        acap = db.get_acap_version(conn, system_id, versions[0]["acap_version_id"])
        if acap is None:
            raise HTTPException(status_code=404, detail="ACAP version payload missing")
        return acap
    finally:
        conn.close()


@app.get("/systems/{system_id}/governance-manifest.yaml")
def get_governance_manifest_yaml(
    system_id: str, version_id: str | None = Query(default=None),
) -> PlainTextResponse:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="PyYAML not installed. Use the JSON endpoint: /governance-manifest.json",
        )
    acap = _load_acap_for_manifest(system_id, version_id)
    manifest = _build_manifest_from_acap(acap)
    text = yaml.dump(manifest, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return PlainTextResponse(
        content=text,
        media_type="text/yaml",
        headers={"Content-Disposition": f'attachment; filename="governance.yaml"'},
    )


@app.get("/systems/{system_id}/governance-manifest.json")
def get_governance_manifest_json(
    system_id: str, version_id: str | None = Query(default=None),
) -> dict[str, Any]:
    acap = _load_acap_for_manifest(system_id, version_id)
    return _build_manifest_from_acap(acap)


# ---------------------------------------------------------------------------
# Audit status
# ---------------------------------------------------------------------------

@app.get("/systems/{system_id}/audit-status")
def get_audit_status_endpoint(system_id: str) -> dict[str, Any]:
    conn = db.connect()
    try:
        return db.get_audit_status(conn, system_id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Governed actions: pre-execution authorization, records and kill switches
# ---------------------------------------------------------------------------

@app.post("/actions/evaluate")
def evaluate_action_endpoint(request: ActionEvaluateRequest) -> dict[str, Any]:
    """Authorize one action before the caller executes it.

    Deliberately does not call _validate_system: a governed application may
    post actions before any discovery upload exists for its system.
    """
    action = request.action or {}
    system_id = str(action.get("system_id") or "").strip()
    if not system_id:
        raise HTTPException(status_code=422, detail="action.system_id is required")
    if not action.get("capability_name"):
        raise HTTPException(status_code=422, detail="action.capability_name is required")

    conn = db.connect()
    try:
        decision = evaluate_action(conn, action)
        mode_info = resolve_enforcement_mode(conn, system_id, action.get("enforcement_mode"))
        # Keep both: the mode actually in force drives the Governed Actions
        # table, while the mode the SDK asked for is what an override is
        # compared against -- storing only the effective one would let an
        # override feed back on itself and misreport the system's own mode.
        action["requested_enforcement_mode"] = mode_info["sdk_mode"]
        action["enforcement_mode"] = mode_info["mode"]
        action.setdefault("action_id", decision["action_id"])
        db.insert_governed_action(conn, action)
        db.insert_action_decision(conn, decision, system_id=system_id)
    finally:
        conn.close()
    return {"decision": decision, "enforcement_mode": mode_info}


@app.post("/actions/record")
def record_action_endpoint(request: ActionRecordRequest) -> dict[str, Any]:
    """Persist what actually happened after a decision was applied."""
    record = request.record or {}
    if not record.get("action_id"):
        raise HTTPException(status_code=422, detail="record.action_id is required")
    stored_request = record.get("request") or {}
    system_id = record.get("system_id") or stored_request.get("system_id")
    if not system_id:
        raise HTTPException(status_code=422, detail="record.system_id is required")

    conn = db.connect()
    try:
        # The action may not have been evaluated through this backend (local
        # fallback, or an offline run replaying records), so store it too.
        if stored_request:
            stored_request.setdefault("action_id", record["action_id"])
            stored_request.setdefault("system_id", system_id)
            db.insert_governed_action(conn, stored_request, replace=False)
        decision = record.get("decision")
        if decision and decision.get("decision_id"):
            db.insert_action_decision(conn, decision, system_id=system_id)
        db.upsert_action_record(conn, record)
    finally:
        conn.close()
    return {"stored": True, "action_id": record["action_id"]}


@app.get("/systems/{system_id}/actions")
def list_actions_endpoint(
    system_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    conn = db.connect()
    try:
        actions = db.list_governed_actions(conn, system_id, limit=limit, offset=offset)
        summary = db.action_summary_counts(conn, system_id)
    finally:
        conn.close()
    return {
        "system_id": system_id,
        "summary": summary,
        "count": len(actions),
        "actions": actions,
    }


@app.get("/systems/{system_id}/actions/{action_id}")
def get_action_endpoint(system_id: str, action_id: str) -> dict[str, Any]:
    conn = db.connect()
    try:
        action = db.get_governed_action(conn, system_id, action_id)
    finally:
        conn.close()
    if action is None:
        raise HTTPException(status_code=404, detail=f"action not found: {action_id}")
    return action


@app.post("/systems/{system_id}/kill-switches")
def create_kill_switch_endpoint(
    system_id: str, request: KillSwitchCreateRequest
) -> dict[str, Any]:
    conn = db.connect()
    try:
        switch = db.insert_kill_switch(
            conn,
            {
                "kill_switch_id": request.kill_switch_id,
                "system_id": system_id,
                "enabled": request.enabled,
                "target_capabilities": request.target_capabilities,
                "verdict": request.verdict,
                "reason": request.reason,
                "created_by": request.created_by,
            },
        )
    finally:
        conn.close()
    return switch


@app.get("/systems/{system_id}/kill-switches")
def list_kill_switches_endpoint(system_id: str) -> dict[str, Any]:
    conn = db.connect()
    try:
        switches = db.list_kill_switches(conn, system_id)
    finally:
        conn.close()
    return {"system_id": system_id, "count": len(switches), "kill_switches": switches}


@app.patch("/systems/{system_id}/kill-switches/{kill_switch_id}")
def patch_kill_switch_endpoint(
    system_id: str, kill_switch_id: str, request: KillSwitchPatchRequest
) -> dict[str, Any]:
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    conn = db.connect()
    try:
        switch = db.update_kill_switch(conn, system_id, kill_switch_id, updates)
    finally:
        conn.close()
    if switch is None:
        raise HTTPException(status_code=404, detail=f"kill switch not found: {kill_switch_id}")
    return switch


def _enforcement_mode_state(conn: Any, system_id: str) -> dict[str, Any]:
    """Resolve the mode against the last mode this system's SDK actually sent."""
    return resolve_enforcement_mode(
        conn, system_id, db.latest_action_enforcement_mode(conn, system_id)
    )


@app.get("/systems/{system_id}/enforcement-mode")
def get_enforcement_mode_endpoint(system_id: str) -> dict[str, Any]:
    """The effective enforcement mode, and how it was arrived at.

    Like /actions/evaluate, this deliberately does not call _validate_system: a
    governed app may post actions before any discovery upload exists.
    """
    conn = db.connect()
    try:
        return _enforcement_mode_state(conn, system_id)
    finally:
        conn.close()


@app.patch("/systems/{system_id}/enforcement-mode")
def patch_enforcement_mode_endpoint(
    system_id: str, request: EnforcementModePatchRequest
) -> dict[str, Any]:
    """Set or clear the dashboard override for a system's enforcement mode.

    The override takes effect on the governed app's next action -- no restart.
    A mode weaker than the one the SDK sends is stored but reported as ignored:
    the dashboard can tighten a system's posture, never loosen it.
    """
    mode = request.mode
    conn = db.connect()
    try:
        if mode is None:
            db.clear_enforcement_mode_override(conn, system_id)
        else:
            normalized = str(mode).strip().lower()
            if normalized not in ENFORCEMENT_MODES:
                raise HTTPException(
                    status_code=422,
                    detail=f"mode must be one of {sorted(ENFORCEMENT_MODES)}, got {mode!r}",
                )
            db.set_enforcement_mode_override(
                conn, system_id, normalized, updated_by=request.updated_by
            )
        return _enforcement_mode_state(conn, system_id)
    finally:
        conn.close()
