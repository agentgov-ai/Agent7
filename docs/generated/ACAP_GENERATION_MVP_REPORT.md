# ACAP Version Generation MVP Report

**Date:** 2026-08-29
**Milestone:** ACAP Version Generation from Reviewed Capabilities

## Purpose

Generate immutable ACAP versions from human-reviewed capability decisions. This closes the governance loop: scanner discovers candidates, human reviews them, and the ACAP records the authorization boundary.

**Product principle:** Scanner suggests. Human approves. Runtime proves.

## Architecture

```
Discovery Upload → Human Review → POST /acap/generate-from-discovery → Immutable ACAP Version
```

## ACAP Version Structure

```json
{
  "acap_version_id": "ACAP-{system_id}-v{N}",
  "system_id": "...",
  "version_number": N,
  "status": "generated",
  "generated_at": "ISO timestamp",
  "generated_from": {
    "upload_id": "...",
    "scanner_version": "0.1.0",
    "project_hash": "sha256:..."
  },
  "allowed_capabilities": [...],
  "denied_capabilities": [...],
  "unresolved": {
    "pending_count": N,
    "pending_capability_ids": [...],
    "pending_high_risk": [...]
  },
  "excluded": { "false_positive_count": N },
  "model_surface": [...],
  "review_summary": {
    "total_candidates": N,
    "approved_count": N,
    "denied_count": N,
    "false_positive_count": N,
    "pending_count": N,
    "review_count": N
  }
}
```

## Capability → ACAP Mapping

| Review Status | ACAP Section | Meaning |
|--------------|--------------|---------|
| `approved_for_acap` | `allowed_capabilities` | Authorized for use |
| `edited` | `allowed_capabilities` | Authorized with human corrections |
| `rejected` | `denied_capabilities` | Real capability, not authorized |
| `false_positive` | Excluded (counted) | Scanner error, not a real capability |
| `pending` | Excluded (counted, warned) | Not yet reviewed |

Model surface entries are included as informational metadata only — never as capability authorizations.

## API Endpoints (3 new)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/systems/{id}/acap/generate-from-discovery` | POST | Generate new immutable ACAP version |
| `/systems/{id}/acap/versions` | GET | List all versions (summary) |
| `/systems/{id}/acap/versions/{vid}` | GET | Get full version payload |

## Immutability

Each generation creates a new version with an incrementing `version_number`. Past versions are never mutated. The `acap_versions` table stores the full payload as `payload_json` — a snapshot of the authorization boundary at generation time.

## Dashboard UI

The "Capability Discovery" section now includes:
- **ACAP Preview panel** — counts of approved/denied/pending/false_positive with lists
- **Warning banner** — highlights unreviewed high-risk capabilities
- **Generate ACAP Version button** — creates a new version from current review state
- **Version History panel** — shows all generated versions with IDs and timestamps

## Database

New table: `acap_versions`
```sql
acap_version_id TEXT PRIMARY KEY,
system_id TEXT NOT NULL,
version_number INTEGER NOT NULL,
generated_at TEXT NOT NULL,
upload_id TEXT NOT NULL,
scanner_version TEXT,
project_hash TEXT,
payload_json TEXT NOT NULL
```

## Test Coverage

11 new tests:
- Approved → allowed_capabilities, rejected → denied_capabilities
- False positives excluded from both lists
- Pending excluded and counted (with high-risk tracking)
- Version immutability (re-fetch returns identical payload)
- Second generation increments version_number
- Review provenance summary included
- Model surface not treated as capability authorization
- List/get version endpoints work
- No-discovery → 404

Total: 186 tests, all passing.

## What this does NOT do

- Auto-approve any pending capability
- Mutate past ACAP versions or scanner records
- Treat model usage as capability authorization
- Call AI/LLM
- Generate compliance-certified ACAP (status is "generated", not "certified")
