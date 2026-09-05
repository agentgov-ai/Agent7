# Governance Loop Dashboard Polish Report

**Date:** 2026-08-29
**Milestone:** End-to-End Governance Loop Dashboard Polish

## Purpose

Make the dashboard clearly show the full governance loop: **Scanner Suggested → Human Reviewed → ACAP Generated → Runtime Rules Run → Findings Detected**.

This is a frontend-only milestone. No API, database, scanner, or rule changes.

## Changes

### 1. Governance Loop Workflow Panel

A 5-step status indicator at the top of the Capability Discovery section:

| Step | Indicator | Condition |
|------|-----------|-----------|
| Scanner Suggested | Green dot | Discovery data loaded |
| Human Reviewed | Green dot | At least one capability reviewed |
| ACAP Generated | Green dot | At least one ACAP version exists |
| Runtime Rules Run | Green dot | Findings exist for the system |
| Findings Detected | Green dot | ACAP-based findings exist |

Steps that aren't complete show a gray dot. Arrows connect the steps visually.

### 2. Run ACAP Rules Button

Added inside the ACAP Version History panel:
- **Enabled** when an ACAP version exists
- **Disabled** with hint "Generate an ACAP version first." when no ACAP version exists
- Shows loading state ("Running...") during execution
- After completion: shows success/error message with finding count
- Automatically refreshes findings list and workflow status

### 3. ACAP-Specific Finding Display

**Finding list (left panel):**
- ACAP-based findings show a purple "ACAP" badge next to severity
- Meta line shows `rule_id | capability_name` instead of `rule_id | session`

**Finding detail (right panel):**
- ACAP field shows `ACAP-{system}-v{N} (vN)` for ACAP findings
- Outcome field shows `{capability_name} (runtime observed)` for ACAP findings
- Rule-specific recommendations for all 4 ACAP rules

### 4. Rule Recommendations

| Rule | Recommendation |
|------|---------------|
| R_ACAP_unapproved_observed | Review this tool and add it to the capability inventory |
| R_ACAP_denied_observed | Investigate why denied tool was invoked at runtime |
| R_ACAP_approval_required_missing | Implement verified approval mechanism |
| R_ACAP_data_class_mismatch | Review and update capability's allowed data classes |

### 5. Governance Explanation Panel

At the bottom of the Capability Discovery section:

> *"Scanner output is not authorization. Only reviewed capabilities enter ACAP. Runtime findings compare observed behavior against the active ACAP version."*

### 6. Visual Badges

- **ACAP** (purple) — on ACAP-based findings in the list
- Existing severity badges (high=red, medium=orange) unchanged
- Workflow step dots (gray=incomplete, green=done)

## Files Modified

| File | Changes |
|------|---------|
| `static/index.html` | Workflow panel (5 steps), Run ACAP Rules button with hint/result areas, governance explainer panel |
| `static/app.js` | `renderWorkflowStatus()`, `runAcapRules()` with loading/success/error states, auto-refresh findings, ACAP finding badges in list, ACAP context in detail panel, 4 rule recommendations |
| `static/styles.css` | Workflow steps (`.wf-step`, `.wf-dot`, `.wf-arrow`), explainer panel, ACAP badge, result messages, responsive overrides |

## Manual Verification Checklist

- [ ] `/ui/` loads without console errors
- [ ] Workflow panel shows 5 steps with gray dots initially
- [ ] Upload discovery → "Scanner Suggested" turns green
- [ ] Approve a capability → "Human Reviewed" turns green
- [ ] Generate ACAP version → "ACAP Generated" turns green
- [ ] Run ACAP Rules button is enabled after ACAP generation
- [ ] Click Run ACAP Rules → button shows "Running...", then result message
- [ ] Findings list refreshes automatically after rules run
- [ ] ACAP findings show purple "ACAP" badge in list
- [ ] ACAP finding detail shows version number and capability name
- [ ] "Runtime Rules Run" and "Findings Detected" steps turn green
- [ ] Run ACAP Rules button disabled with hint when no ACAP version
- [ ] Governance explainer text visible at bottom of Discovery section
- [ ] Existing approve/edit/reject/not-a-capability buttons still work
- [ ] ACAP version generation still works
- [ ] No console errors throughout workflow

## Test Results

All 197 existing tests pass. No backend changes were made, so no new tests were needed.
