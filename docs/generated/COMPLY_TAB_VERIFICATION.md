# Comply Tab — Change Notes & Verification

**Date:** 2026-10-03
**Scope:** Make the Comply tab interactive and explainable. No change to enforcement
semantics, kill-switch decision order, observe/enforce behaviour, or the generated
governance manifest.

---

## The bug

For a discovery-only system such as `skyquery-local`, every Comply signal read as zero:

```
ACAP           applicable=False   "No tools or authorization boundaries discovered"
OWASP Agentic  applicable=False   "No agentic behavior discovered"
risk_profile   use_case=null  environment=null  external_side_effects=false
```

even though the system had 2 ACAP versions, 39 discovered capabilities (2 approved,
1 rejected) and 151 governed actions.

**Root cause:** `_validate_system()` in `services/evidence_api/app.py` returns a literal
empty dict for any system not in the hardcoded `SYSTEM_REGISTRY`:

```python
if system_id in known:
    # DB-discovered system — return minimal record
    return {}, {"system_id": system_id, "source": "discovery"}
```

All four Comply endpoints fed that `{}` into `risk.py`, which derives everything from
`acap["tools"]` and `acap["system"]`. No tools → no authority, no side effects, no
applicability. The DB was never consulted.

## The fix

A **facts layer**. `_system_facts(system_id)` in `app.py` reads what the database
actually knows — ACAP versions, discovery capabilities and their review statuses,
governed-action counts, kill switches, environment — and passes it to `risk.py` as an
optional second argument.

Facts **supplement** a reviewed ACAP; they never override one. A reviewed ACAP always
wins, so the six `SYSTEM_REGISTRY` fixture systems are provably unaffected (the registry
branch of `_validate_system` is untouched).

Rather than duplicate the derivation rules, `capabilities_as_tools()` reshapes capability
rows (`suggested_action_type`, `external_side_effect`, …) into the tool shape the existing
loop already understands (`proposed_action_type`, …), so one code path serves both.

### New applicability rules

| Framework | Applicable when |
|---|---|
| **ACAP** | a reviewed ACAP has tools **OR** an ACAP version exists **OR** ≥1 approved capability |
| **OWASP Agentic** | ACAP tools/agents **OR** discovered capabilities **OR** governed actions **OR** an observed action type in read/write/execute/query_execute/external_api_call |

Every framework entry now also carries `why`, `why_not`, `evidence` and `would_change`
so a result can be explained rather than asserted. These are factual statements about the
system's own data — no legal claims. States remain `applicable` / `informational` /
`passed` / `not_applicable`.

## Files changed

| File | Change |
|---|---|
| `services/evidence_api/risk.py` | optional `facts` param on `build_risk_profile` and `evaluate_framework_applicability`; `capabilities_as_tools()`; `_derived_use_case()`; explainability fields |
| `services/evidence_api/app.py` | `_system_facts()`, `_comply_inputs()`; the 4 Comply endpoints + the markdown report now use them |
| `static/index.html` | Run Assessment button + result line in the Latest Assessment card head; Framework Detail card |
| `static/app.js` | `state.selectedFramework`; clickable applicability rows; `renderFrameworkDetail()`; `fillList()`; `runAssessment()` upgraded with busy state, `resp.ok` check and a success line; empty-state text |
| `static/styles.css` | `.card-head-actions`; `:disabled` for `.btn-secondary` |
| `tests/test_evidence_api.py` | 5 new tests |

API contracts unchanged — no endpoint renamed, no response field removed.

## Results after the fix (`skyquery-local`)

```
ACAP           applicable=True   "Approved authorization boundary exists for this system:
                                  ACAP-skyquery-local-v2 with 2 approved capabilities"
OWASP Agentic  applicable=True   "Governed tool/API behavior detected through discovered
                                  capabilities and runtime action decisions"
risk_profile   use_case="SkyQuery governed data/query assistant"
               environment="local"  external_side_effects=true
framework_status: ACAP=passed  OWASP=passed  NIST=passed
                  EU AI Act=not_applicable  ISO/IEC 42001=informational
```

`restaurant-agent` is byte-identical to before (verified side by side).

## Automated tests

Added to `tests/test_evidence_api.py`:

1. `test_acap_applicable_from_approved_capabilities_without_reviewed_acap` — discovered but
   unapproved → ACAP not applicable; after approving one → applicable.
2. `test_applicability_entries_carry_explanations` — applicable frameworks have `why`,
   non-applicable have `why_not`; both have `evidence` and `would_change`.
3. `test_risk_profile_derived_for_discovery_only_system` — use_case, environment and side
   effects populated with no reviewed ACAP.
4. `test_assessment_framework_status_not_applicable_without_boundary` — the inverse still
   holds: no ACAP and no approvals → `not_applicable`.
5. `test_reviewed_acap_system_applicability_is_unchanged_by_facts` — regression guard for
   the fixture systems.

```powershell
python -m pytest tests -q
```

**Baseline before this work: 29 failed, 275 passed. After: 29 failed, 280 passed.**
The 29 are pre-existing and unrelated (they need the gitignored
`artifacts/governance/events.jsonl`); verified identical by stashing the changes and
re-running.

## Manual verification

```powershell
python -m uvicorn services.evidence_api.app:app --host 127.0.0.1 --port 8077
```

Open `http://127.0.0.1:8077/ui/`, select **skyquery-local**, go to **Comply**:

| Step | Expected |
|---|---|
| Click **Run Assessment** (top-right of Latest Assessment) | Button shows "Running…" and is disabled; a green line reads `Assessment A-… completed (satisfactory).`; Assessment ID and Assessed At update. No page reload. |
| Framework Status table | ACAP `passed`, OWASP Agentic `passed` — not `not_applicable` |
| Risk Profile | Use Case `SkyQuery governed data/query assistant`, Environment `local`, Side Effects `yes` |
| Click the **ACAP** row | Detail card: "Why it applies" lists the ACAP version and approved-capability counts; Evidence lists version id and counts; "What would change this" suggests reviewing the 36 pending capabilities |
| Click the **EU AI Act** row | Heading flips to "Why it does not apply"; lists missing EU jurisdiction and local environment; "What would change this" says declare EU jurisdiction, classify high-risk, re-run |
| Approve another capability in **Agents / Discovery**, return to Comply, click Run Assessment | Approved count in the ACAP evidence increases — applicability is derived from current state, not frozen |

**Verified in a real browser** (Playwright against a live server on 8077): Run Assessment
produced `A-320504a34f12`, ACAP and OWASP flipped to `passed`, both detail paths rendered,
and Governed Actions / Enforcement Mode / Kill Switches / Discovery were re-checked
afterwards and still work.

## Defensive behaviour

- No assessment yet → Framework Status table and Recommended Actions both read
  "No assessment yet. Click Run Assessment."
- No framework selected → detail card reads "No framework selected."
- A system with no discovery and no ACAP (only a governed action) returns 200 on all four
  Comply endpoints; ACAP reports `not_applicable` with an explicit `why_not`.
- `_system_facts` wraps its DB reads in `try/except` and logs — enrichment can never take
  down an endpoint that worked before.
- Run Assessment with no system selected shows a message instead of silently doing nothing.

## Known limitation

`use_case` for a discovery-only system is derived, not declared: `"SkyQuery governed
data/query assistant"` when the system id contains `skyquery`, otherwise
`"Governed application with N discovered capabilities"`. This is a display convenience, not
a human-reviewed statement of purpose. A reviewed ACAP's `purpose` always takes precedence.
