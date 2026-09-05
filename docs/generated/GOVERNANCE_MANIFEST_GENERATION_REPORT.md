# Governance Manifest Generation Report

**Date:** 2026-08-29
**Milestone:** Generate governance.yaml from Reviewed Capabilities

## Purpose

Generate a `governance.yaml` manifest from an immutable ACAP version so users can instrument approved functions without manual decorators. Closes the full governance loop: scan → review → ACAP → manifest → instrument.

## API Endpoints (2 new)

| Endpoint | Method | Content-Type | Purpose |
|----------|--------|-------------|---------|
| `/systems/{id}/governance-manifest.yaml` | GET | text/yaml | Download YAML manifest |
| `/systems/{id}/governance-manifest.json` | GET | application/json | Get JSON manifest |

Both support `?version_id=ACAP-...-vN` to select a specific ACAP version. Default: latest.

## Manifest Structure

```yaml
system_id: my-system
generated_from:
  acap_version_id: ACAP-my-system-v1
  acap_version_number: 1
  generated_at: 2026-08-29T...
  source: evidence_api
capabilities:
  - capability_id: CAP-abc123
    name: refund_execute
    module_path: app.refund_execute
    action_type: write
    approval_required: true
    data_classes: [financial]
    external_side_effect: true
    status: approved
```

## What's Included / Excluded

| Source | Included | Status in manifest |
|--------|----------|-------------------|
| `allowed_capabilities` | Yes | `approved` |
| `denied_capabilities` | No | — |
| `pending` (unresolved) | No | — |
| `false_positive` | No | — |
| `model_surface` | No | — |
| Capability without `module_path` | No (uninstrumentable) | — |

## Dashboard

- **Download button** on each ACAP version card ("governance.yaml" link)
- **Usage snippet panel** showing:
  ```python
  from ai_governance import GovernanceClient
  gov = GovernanceClient.from_config("governance.yaml")
  gov.instrument_from_config()
  ```

## YAML Dependency

- YAML endpoint requires PyYAML. Returns 503 with clear message if not installed.
- JSON endpoint always works (no YAML dependency).

## Test Coverage

10 new tests:
- YAML manifest generated from approved capabilities
- JSON manifest generated from approved capabilities
- Denied capabilities excluded
- False positives excluded
- Pending capabilities excluded
- Metadata (generated_from) present with source=evidence_api
- All capabilities have status=approved
- Selected version_id returns that version
- No ACAP version → 404
- Generated YAML loadable by SDK's `load_manifest()`

Total suite: 225 tests, all passing.

## Files Modified

| File | Changes |
|------|---------|
| `services/evidence_api/app.py` | `_build_manifest_from_acap()`, `_load_acap_for_manifest()`, 2 GET endpoints |
| `services/evidence_api/static/index.html` | Usage snippet panel |
| `services/evidence_api/static/app.js` | Download button per version card, usage panel visibility |
| `services/evidence_api/static/styles.css` | `.btn-download`, `.usage-snippet` styles |
| `tests/test_evidence_api.py` | 10 new test methods |
