# ACAP Runtime Comparison Rules Report

**Date:** 2026-08-29
**Milestone:** Runtime vs ACAP Comparison Rules

## Purpose

Compare runtime evidence against the latest generated ACAP version and produce findings when observed behavior violates approved authorization. This is the "runtime proves" step of the governance loop.

**Product principle:** Scanner suggests. Human approves. Runtime proves.

## Important: Observation Only

These rules are **observation-only** — they detect and report violations but do NOT block runtime execution. The system produces findings for human review; it does not enforce authorization at runtime.

## Four New Rules

| Rule ID | Severity | Trigger |
|---------|----------|---------|
| `R_ACAP_unapproved_observed` | medium | Runtime tool observed with no matching allowed capability in ACAP |
| `R_ACAP_denied_observed` | high | Runtime tool observed that is explicitly denied in ACAP |
| `R_ACAP_approval_required_missing` | high | Allowed capability requires approval but no trusted approval evidence present |
| `R_ACAP_data_class_mismatch` | medium | Runtime data classes exceed ACAP allowed data classes |

### No Duplicate Findings

If a tool is in `denied_capabilities`, it triggers `R_ACAP_denied_observed` only — NOT also `R_ACAP_unapproved_observed`. This prevents contradictory duplicate findings.

## Approval Trust Model

**`approval.granted` alone is NOT trusted.** A boolean inside the runtime event is set by the same application being audited and can be forged.

Trusted approval requires an explicit verification marker:
- `approval.verified == true`
- `approval.trusted == true`
- `approval.token_verified == true`

If only `approval.granted == true` exists without a trusted marker, the finding says: *"Approval required, but no trusted approval evidence was observed. approval.granted alone is not trusted."*

**Note:** The trusted approval token design is not fully implemented yet. This MVP establishes the principle that self-reported approval is insufficient.

## Matching Strategy

**Current:** Match runtime `tool.name` to ACAP capability `name`.

Tool name extraction: `tool.name` first, falls back to `component.name`.

**Limitations:**
- Name-only matching may miss renamed tools or aliased invocations
- No module_path or capability_id matching yet
- Model surface events (OpenAI/Anthropic SDK calls) are ignored by ACAP rules — only `tool_start` business events are evaluated

## ACAP Field Resilience

Helper functions handle naming variations across ACAP versions:
- `_approval_required(cap)` — checks `approval_required`, `suggested_approval_required`, and `approval.required` (including `{value: ...}` wrappers)
- `_data_classes(cap)` — checks `data_classes` and `suggested_data_classes`
- `_action_type(cap)` — checks `action_type` and `suggested_action_type`

## Finding Structure

Every ACAP finding includes:
```json
{
  "finding_id": "F-{sha256[:12]}",
  "rule_id": "R_ACAP_...",
  "acap_id": "ACAP-{system}-v{N}",
  "acap_version_id": "ACAP-{system}-v{N}",
  "acap_version_number": N,
  "violates": "ACAP_authorization",
  "severity": "high|medium",
  "session": "...",
  "event_ids": ["..."],
  "trace_ids": ["..."],
  "capability_id": "CAP-..." or null,
  "capability_name": "tool_name",
  "description": "Human-readable explanation"
}
```

## API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/systems/{id}/rules/run-acap` | POST | Run all 4 ACAP rules against latest ACAP version |

The existing `/rules/run` endpoint is unchanged — legacy rules (R1, R_write_no_approval) continue to work.

## Authorization Rules

- `approved_for_acap` / `edited` → authorized (in `allowed_capabilities`)
- `rejected` → denied (in `denied_capabilities`)
- `false_positive` → excluded from ACAP, does NOT authorize runtime use
- `pending` → excluded from ACAP, does NOT authorize runtime use

## Test Coverage

11 new tests:
- Approved capability → no unapproved finding
- Unapproved tool → finding created
- Denied tool → high severity finding, no duplicate unapproved finding
- approval.granted alone → finding (not trusted)
- approval.verified=true → no finding (trusted)
- false_positive does not authorize runtime
- pending does not authorize runtime
- Findings pin to ACAP version (acap_version_id + version_number)
- No ACAP version → 404
- Legacy R1 finding F-06236c96da2c still produced

Total: 197 tests, all passing.

## Files Modified

| File | Changes |
|------|---------|
| `services/evidence_api/rules.py` | 4 rules + 6 helpers + `run_all_acap_rules` dispatcher |
| `services/evidence_api/app.py` | `POST /systems/{id}/rules/run-acap` endpoint |
| `services/evidence_api/static/app.js` | Show ACAP version in finding detail panel |
| `tests/test_evidence_api.py` | 11 new test methods + `_make_tool_event` + `_ingest_event` helpers |
