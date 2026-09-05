# Onboarding and Continuous Audit Loop Report

**Date:** 2026-08-29
**Milestone:** Real Onboarding + Continuous Audit Loop

## Summary

Transformed the dashboard from a demo-seeded experience into a real user workflow where scanning and uploading automatically registers systems, review decisions persist across rescans, and audit freshness is tracked.

**Product principle:** Scanner suggests. Human approves. Runtime proves. Rescan shows drift.

## Real User Workflow

```
1. agent-governance scan . --output governance-discovery.json
2. agent-governance upload-discovery governance-discovery.json --api http://127.0.0.1:8000
3. Dashboard: review capabilities (approve/reject/edit)
4. Dashboard: generate ACAP version
5. Dashboard: download governance.yaml
6. Add to app:
   gov = GovernanceClient.from_config("governance.yaml")
   gov.instrument_from_config()
7. Run your app → runtime events flow in
8. Dashboard: Run ACAP Rules → findings appear
9. Code changes → rescan → upload → changeset shows drift
```

## Key Changes

### A. Dynamic System Registry

`/systems` now returns systems from both `SYSTEM_REGISTRY` (demo fixtures) and the database (discovery uploads, events, ACAP versions, findings). Uploading a discovery for a new system automatically makes it visible.

### B. CLI `upload-discovery` Command

```bash
agent-governance upload-discovery governance-discovery.json --api http://127.0.0.1:8000
```

- Reads governance-discovery.json
- POSTs to `/discovery/upload`
- Prints: system_id, upload_id, candidates, reviews carried forward, dashboard URL
- Uses stdlib only (urllib), no new dependencies

### C. Discovery Changeset

When a second scan is uploaded for the same system, the API computes a changeset:
- **New:** capabilities not in the previous scan
- **Changed:** capabilities where action_type, data_classes, risk, approval_required, side_effect, file_path, or line range differ
- **Removed:** capabilities that were in the previous scan but not the current one
- **Unchanged:** capabilities that match exactly

Matching uses `capability_id` (primary) or `name+module_path` (fallback).

### D. Review Preservation Across Rescans

| Scenario | Result |
|----------|--------|
| Unchanged approved capability | Stays `approved_for_acap` |
| Unchanged rejected capability | Stays `rejected` |
| Unchanged false_positive | Stays `false_positive` |
| Changed high-risk approved capability | Becomes `needs_reapproval` |
| New capability | Starts `pending` |

`needs_reapproval` is treated like `pending` in ACAP generation — excluded from `allowed_capabilities` and counted as unresolved.

### E. Audit Status

New endpoint: `GET /systems/{system_id}/audit-status`

| Status | Meaning |
|--------|---------|
| `discovery_missing` | No scan uploaded yet |
| `acap_missing` | Discovery exists but no ACAP generated |
| `needs_reapproval` | Changed capabilities need re-review |
| `scan_changed_since_acap` | New scan after last ACAP |
| `runtime_missing` | No runtime events yet |
| `runtime_changed_since_assessment` | New events since last assessment |
| `up_to_date` | Everything current |

Each status includes a `next_action` in plain English.

### F. Dashboard Improvements

- **Upload flow:** After upload → refreshes systems → selects uploaded system → switches to Discovery tab → shows candidates immediately
- **Overview tab:** Audit status panel with badge + next action guidance
- **Discovery tab:** Changeset panel showing new/changed/removed counts on rescan

## Files Changed

| File | Changes |
|------|---------|
| `services/evidence_api/db.py` | Migration for `previous_upload_id` + `scan_sequence_number`, `list_known_system_ids()`, `compute_discovery_changeset()`, `carry_forward_reviews()`, `get_audit_status()` |
| `services/evidence_api/app.py` | Dynamic `/systems`, `_validate_system()` accepts DB systems, discovery upload carries reviews, changeset in discovery response, ACAP treats `needs_reapproval` as pending, `GET /audit-status` |
| `sdk-python/ai_governance/cli.py` | `upload-discovery` subcommand |
| `services/evidence_api/static/index.html` | Audit status panel in Overview |
| `services/evidence_api/static/app.js` | `auditStatus` state + fetch, `renderAuditStatus()`, upload flow improvements (refresh systems, select, switch tab) |
| `tests/test_evidence_api.py` | 13 new tests |

## Test Coverage

13 new tests:
- Discovery upload registers new system in /systems
- /systems includes discovery-only system
- Second upload produces changeset (new/changed/removed)
- Unchanged approved capability preserved
- Changed high-risk approved → needs_reapproval
- needs_reapproval excluded from ACAP allowed
- New candidate starts pending
- Removed candidate in changeset
- Audit status: discovery_missing, acap_missing, up_to_date
- Demo reset works with new tables
- Existing demo systems still listed

Total: 239 tests, all passing.

## Limitations

- CLI `upload-discovery` uses urllib (stdlib), not httpx/requests
- `scan --upload` combined command not yet implemented (documented as next step)
- `agent-governance init` not yet implemented (documented as future)
- Changeset does not track line-level diffs (only field-level changes)
- Audit status is computed on-demand, not cached
