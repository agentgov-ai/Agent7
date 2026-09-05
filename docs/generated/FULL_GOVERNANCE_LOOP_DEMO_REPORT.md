# Full Governance Loop Demo Report

**Date:** 2026-08-29
**Milestone:** End-to-End Governance Loop Demo Script

## Purpose

Prove the full governance loop in a single script: scan → review → ACAP → manifest → instrument → runtime → findings.

## Command

```bash
python scripts/run_full_governance_loop_demo.py
```

No running server required. Uses FastAPI TestClient with isolated temp DB.

## Demo Steps

| Step | Action | Result |
|------|--------|--------|
| 1 | Scan `examples/scanner-demo-app` | 4 candidates, 3 model surface entries |
| 2 | Upload discovery to Evidence API | Stored in temp DB |
| 3 | Approve `refund_execute` + `send_invoice_email`, reject `delete_customer` | 2 approved, 1 rejected |
| 4 | Generate ACAP version | ACAP-scanner-demo-v1 |
| 5 | Download governance manifest | 2 instrumentable capabilities |
| 6 | Ingest runtime events | `refund_execute` (approval.granted only) + `delete_customer` (denied) |
| 7 | Run ACAP rules | 2 findings created |

## Findings Produced

### R_ACAP_denied_observed (HIGH)
> Tool 'delete_customer' was observed at runtime but is explicitly denied in ACAP v1.

### R_ACAP_approval_required_missing (HIGH)
> Tool 'refund_execute' requires approval per ACAP v1, but no trusted approval evidence was observed. approval.granted alone is not trusted.

## Sample Output

```
================================================================
  Summary
================================================================
  Scanner candidates:        4
  Approved capabilities:     2
  Rejected capabilities:     1
  ACAP version:              ACAP-scanner-demo-v1
  Manifest capabilities:     2
  Runtime events ingested:   2
  ACAP findings created:     2
  Finding rule IDs:          R_ACAP_approval_required_missing, R_ACAP_denied_observed

  Checks:
    ACAP findings exist:        PASS
    Denied capability finding:  PASS
    Approval missing finding:   PASS
```

## Test Coverage

1 smoke test: `tests/test_full_loop_demo.py` — runs the full demo in-process, asserts exit code 0 (all checks pass).

Total suite: 226 tests, all passing.

## Files

| File | Purpose |
|------|---------|
| `scripts/run_full_governance_loop_demo.py` | Full loop demo script |
| `tests/test_full_loop_demo.py` | Smoke test |
| `docs/generated/FULL_GOVERNANCE_LOOP_DEMO_REPORT.md` | This report |

## What This Proves

1. **Scanner suggests** — AST analysis finds 4 candidates from demo app
2. **Human approves** — 2 approved, 1 rejected via API
3. **ACAP generated** — Immutable version created with allowed/denied/pending
4. **Manifest generated** — Only approved capabilities, ready for `from_config()`
5. **Runtime proves** — Events compared against ACAP, 2 violations detected:
   - Denied capability was executed
   - Approved capability lacked trusted approval evidence
