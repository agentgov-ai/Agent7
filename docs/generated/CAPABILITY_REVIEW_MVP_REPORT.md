# Capability Review MVP Report

**Date:** 2026-08-29
**Milestone:** Dashboard Capability Review

## Purpose

This milestone adds backend storage, REST endpoints, and a dashboard section so a human can review scanner-discovered candidate capabilities. Each candidate can be approved, rejected, edited, or marked as a false positive.

**Product principle:** Scanner suggests. Human approves. Runtime proves.

The system does NOT:
- Auto-approve any candidate
- Generate final ACAP from reviewed candidates (future milestone)
- Call AI/LLM during review

## Architecture

```
governance-discovery.json
  -> POST /discovery/upload (store in SQLite)
  -> GET /systems/{id}/discovery (retrieve candidates)
  -> POST /systems/{id}/capabilities/{cap_id}/approve|reject|not-a-capability|edit
  -> Dashboard "Capability Discovery" section
```

## Database schema (3 new tables)

| Table | Purpose | Primary Key |
|-------|---------|-------------|
| `discovery_uploads` | One row per scan upload (metadata, scan_summary) | `upload_id` |
| `capabilities` | One row per candidate per upload (all scanner fields) | `(capability_id, upload_id)` |
| `capability_reviews` | Provenance log for every review action | `review_id` |

## API endpoints (6 new)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/discovery/upload` | POST | Upload governance-discovery.json content |
| `/systems/{id}/discovery` | GET | Latest discovery with all capabilities |
| `/systems/{id}/capabilities/{cap}/approve` | POST | Status -> `approved_for_acap` |
| `/systems/{id}/capabilities/{cap}/reject` | POST | Status -> `rejected` |
| `/systems/{id}/capabilities/{cap}/not-a-capability` | POST | Status -> `false_positive` |
| `/systems/{id}/capabilities/{cap}/edit` | POST | Update fields, status -> `edited` |

## Review status values

| Status | Meaning |
|--------|---------|
| `pending` | Scanner discovered, awaiting human review |
| `approved_for_acap` | Human approved as a real, authorized capability |
| `rejected` | Real capability but not authorized |
| `false_positive` | Scanner false positive, not a real capability |
| `edited` | Human modified classification fields |

**Important distinction:** "Rejected" means the capability is real but not authorized. "Not a capability" means the scanner incorrectly flagged it.

## Review provenance

Every review action stores:
- `decision` (approved_for_acap, rejected, false_positive, edited)
- `reviewer` (default: local_user)
- `previous_values_json` (what was there before)
- `edited_values_json` (what changed, for edits)
- `evidence_shown_json` (scanner evidence at review time)
- `reviewed_at` (UTC timestamp)

## Dashboard UI

The "Capability Discovery" section (between Authorization/ACAP and Risk & Frameworks) includes:
- **Upload panel** — file picker + system ID input for uploading discovery JSON
- **Scan Summary** — files scanned, functions seen, candidates found, risk counts
- **Risk filter tabs** — All / High / Medium / Low / Pending / Reviewed
- **Capability cards** — each card shows name, risk badge, confidence source, status, file:lines, action type, data classes, evidence bullets, call chain, and action buttons
- **Model Usage Surface table** — separate from capabilities, shows LLM SDK usage
- **Edit modal** — inline form for modifying action_type, risk, data_classes, approval, side effect

## Editable fields

When editing a capability, the reviewer can change:
- `action_type` (read, write, delete, communicate, execute, unknown)
- `risk` (high, medium, low)
- `data_classes` (comma-separated list)
- `approval_required` (checkbox)
- `external_side_effect` (checkbox)

## Test coverage

15 new tests added to `test_evidence_api.py`:
- Upload stores candidates and returns count
- GET discovery returns capabilities + model surface
- Approve/reject/not-a-capability set correct statuses
- Edit updates fields and sets "edited" status
- Review provenance is stored and tracks previous values
- Pending candidates never auto-approve
- Unknown capability returns 404
- Invalid discovery upload returns 400
- Demo reset works with new tables

Total test suite: 175 tests, all passing.

## Files modified

| File | Changes |
|------|---------|
| `services/evidence_api/db.py` | 3 new tables, 8 new functions, expanded reset_db |
| `services/evidence_api/app.py` | 2 request models, 6 endpoints, uuid import |
| `services/evidence_api/static/index.html` | Discovery section + edit modal HTML |
| `services/evidence_api/static/app.js` | State, fetch, render, action handlers |
| `services/evidence_api/static/styles.css` | Card, filter, modal, button styles |
| `tests/test_evidence_api.py` | Fixture + 15 test methods |

## Next steps

- Generate ACAP preview from approved capabilities
- CLI integration: `agent-governance scan . | agent-governance upload`
- Batch review actions
- Export reviewed capabilities as governance.yaml
