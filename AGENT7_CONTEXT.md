# Agent7 / AgentGov — Product Context

> Paste this whole file into ChatGPT/Claude to give it full context on the product.
> **Status:** working prototype, pre-production. **Last verified:** 2026-10-03.

---

## 1. What it is

Runtime governance for AI agents. It answers: *what is this agent allowed to do, did it stay
inside that boundary, and can we stop it before it does something dangerous?*

The differentiator: the SDK asks the backend for a decision **before every governed action**, so
an operator can change policy in the dashboard and a **separately running application** changes
behaviour on its very next call — no restart, no redeploy, no code change.

Repo: `C:\Users\shrey\Downloads\Restaurant_Agent` (name is historical — the restaurant agent is
now just one example). SDK distribution: `agent-governance-sdk` 0.1.0, **TestPyPI only**.

### The governance loop (the product story)

```
DISCOVER  →  UNDERSTAND  →  AUTHORIZE  →  ENFORCE  →  PROVE  →  COMPLY  →  LEARN
   │            │              │            │           │         │          │
 AST scan   risk+evidence   human        block at    evidence   framework  rescan
 the code   per capability  approves     runtime     records    mapping    drift
                            → ACAP
```

Key principle, enforced throughout: **observed behaviour is never authorization.** Discovery
proposes a catalog; a human must approve the operating boundary. That boundary is the ACAP
(Agent Capability Authorization Policy).

---

## 2. Architecture

Three deployable pieces.

```
┌──────────────────────────────────────────────────────────────────────┐
│  YOUR APP  (e.g. SkyQuery FastAPI backend, :8000)                    │
│                                                                      │
│   ┌────────────────────────────────────────────────────┐            │
│   │  ai_governance SDK  (pip install agent-governance-sdk)│          │
│   │                                                      │          │
│   │  GovernanceMiddleware ──── request-level trace       │          │
│   │                                                      │          │
│   │  @gov.tool / instrument_from_config()                │          │
│   │        │                                             │          │
│   │        ├─ build ActionRequest  (NO raw arg values)   │          │
│   │        ├─ authorize:  local policy  +  backend       │          │
│   │        │     └─ most restrictive wins                │          │
│   │        ├─ enforce_decision(verdict, mode)            │          │
│   │        │     observe → always run                    │          │
│   │        │     shadow  → run, record would-have-blocked│          │
│   │        │     enforce → DENY does not run             │          │
│   │        ├─ ALLOW → tool_start → fn() → tool_end       │          │
│   │        └─ BLOCK → action_decision only; fn NEVER called         │
│   └────────────────────┬───────────────────────────────┘            │
└────────────────────────┼─────────────────────────────────────────────┘
                         │  HTTP (1s timeout, falls back to local policy)
                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  EVIDENCE API   services/evidence_api/   FastAPI + SQLite   (:8077)  │
│                                                                      │
│   POST /actions/evaluate   → verdict + effective enforcement mode     │
│   POST /actions/record     → what actually happened                  │
│   /discovery  /capabilities  /acap  /rules  /findings  /assessment    │
│   /kill-switches  /enforcement-mode                                   │
│                                                                      │
│   SQLite: events, findings, assessments, discovery_uploads,          │
│           capabilities, capability_reviews, acap_versions,           │
│           governed_actions, action_decisions, action_records,        │
│           kill_switches, system_enforcement_modes                    │
└────────────────────────┬─────────────────────────────────────────────┘
                         │  serves
                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  DASHBOARD   /ui/   vanilla JS, no build step                        │
│  Overview · Governed Actions · Approvals · Agents/Discovery ·        │
│  Policies · Evidence · Comply · Findings · Settings                  │
└──────────────────────────────────────────────────────────────────────┘
```

### Decision order (fixed — must not be reordered)

```
kill switch → denied/rejected → not approved → argument policy → approval required → allow
```

**Local policy is a floor.** Both the local and backend verdicts are computed and the *more
restrictive* wins. `denied_argument_patterns` inspects live argument values which never leave the
process, so a backend ALLOW cannot wave them through. An unreachable backend never downgrades a
local DENY. The one permitted upgrade: a verified local approval releases a backend hold.

**Enforcement mode** is the stricter of what the SDK sends (`governance.yaml`) and the dashboard
override. The dashboard can tighten posture, never switch enforcement off.

### Key files

| Path | Role |
|---|---|
| `sdk-python/ai_governance/client.py` | `GovernanceClient` — `tool()`, `authorize()`, `from_config()`, `instrument_from_config()` |
| `sdk-python/ai_governance/enforcement.py` | Policy compilation, local decision engine, mode semantics, HTTP transport |
| `sdk-python/ai_governance/manifest.py` | Parses `governance.yaml`, monkey-patches target functions |
| `sdk-python/ai_governance/scanner/` | AST scanner (`ast_scanner`, `sinks`, `rules`, `models`) |
| `sdk-python/ai_governance/adapters/` | LangChain, OpenAI, Anthropic, FastAPI |
| `services/evidence_api/app.py` | ~44 endpoints |
| `services/evidence_api/enforcement.py` | Backend verdict engine + `resolve_enforcement_mode` |
| `services/evidence_api/db.py` | SQLite schema + helpers |
| `services/evidence_api/static/` | Dashboard (`index.html`, `app.js`, `styles.css`) |
| `control-library/canonical-controls.yaml` | 3 controls → NIST / EU AI Act / ISO 42001 / ACAP mappings |

---

## 3. ✅ What works (verified running, not just claimed)

### Pre-execution enforcement — the core demo
- A denied capability **does not execute its function body**. Proven by a side-effect list, not a
  return value. Works for `async def` too.
- Three modes: `observe` (never blocks) / `shadow` (runs, records what it would have blocked) /
  `enforce` (DENY and unapproved holds do not run).
- **Kill switches** — toggle one in the dashboard and a separately running app is denied on its
  next call, no restart.
- **Dashboard-controlled enforcement mode** — segmented control `SDK default | Observe | Shadow |
  Enforce`. **Verified end to end in a real browser:** set Enforce in the UI → a separate process
  configured for `observe` was blocked on `DROP TABLE flights` (`argument_pattern_denied`), body
  never ran → "SDK default" cleared it and the next call executed again.
- **Argument policy** — regex deny-patterns matched against live argument values in-process.
  Catches destructive SQL.

### Privacy
- No raw argument values persisted. Only `arguments_hash` (sha256), argument names, type names,
  and on denial the `matched_pattern_id` — never the matching text.
- **Verified:** `DROP TABLE flights` appears in no enforcement table (`governed_actions`,
  `action_decisions`, `action_records`) and not in `actions.jsonl`.
- Redaction of emails, phone numbers, 12–19 digit runs, secret-ish key names.

### Discovery → review → policy
AST scanner finds payment SDKs (Stripe/PayPal/Braintree), email/SMTP, SQL writes, FastAPI routes,
model usage → emits `governance-discovery.json` with risk, action type, data classes, approval
requirement, per-candidate evidence → upload → human approve/reject in dashboard → versioned ACAP
→ export `governance.yaml` the SDK consumes.

### Adapters
LangChain callback, OpenAI, Anthropic, FastAPI middleware, plain Python functions.

### Tests
**275 passed, 29 failed.** The 29 are a known pre-existing baseline (see §4.6), not regressions.

---

## 4. ❌ What does NOT work (verified broken)

### 4.1 The flagship finding does not reproduce — **biggest risk**
`POST /demo/reset` returns HTTP 200 saying *"440 events replayed, 1 finding created"*, but
produces **zero findings for restaurant-agent**. The dashboard shows that system as
`satisfactory` / clean.

- **Cause:** the rule groups events by session. The session map
  `artifacts/governance/scenarios/manifest.json` is **gitignored and absent** — `artifacts/` does
  not exist at all. Only 18 of 394 events carry an inline `session_id`; the other 376 collapse
  into one bucket, so the rule short-circuits.
- **It fails silently** — no error, no warning.
- `F-06236c96da2c`, the "deterministic evidence-linked finding" the original project objective was
  defined around, is cited in 7 docs and **does not exist on a fresh checkout**.
- **Do not open the Findings tab in a demo** unless this is fixed first.

### 4.2 Cannot govern class methods — **may block the SkyQuery integration**
The "no code changes" promise works by monkey-patching a module attribute. The resolver imports
everything before the last dot as a module (`sdk-python/ai_governance/manifest.py:100-131`). So
`app.services.QueryService.execute_sql` fails to resolve and **that capability is silently never
governed**. Only module-level functions work via the manifest path.
Workaround: apply `@gov.tool()` in source (which means touching the app's code).

### 4.3 No authentication anywhere
18 mutating endpoints with zero auth — including capability approve/reject, kill switches,
enforcement mode, and `POST /demo/reset` (wipes the DB). Reviewer identity is an unverified
request-body string defaulting to `"local_user"`. `POST /evidence/replay-jsonl` reads an arbitrary
server file path from the request body. **Localhost only — never expose the port.**

### 4.4 Approval verification is not real
`verify_approval_token()` returns true if the approval dict has `verified` / `trusted` /
`token_verified` set to `True`. The governed application writes that dict itself. It distinguishes
`{"granted": True}` from `{"verified": True}` — two literals the same process controls. It does
**not** stop an app from self-approving, and there is no audit trail of who approved.

### 4.5 All six dashboard systems are frozen fixtures
`restaurant-agent`, `customer-refund-agent`, `custom-python-refund-agent`, `openai-direct-agent`,
`anthropic-direct-agent`, `support-api` are hand-frozen JSONL from `examples/demo-data/`. The API
omits rather than labels their provenance, and **the dashboard renders no badge distinguishing
fixture from live data.** Tells: `environment: local`, timestamps dated 2026-07.

### 4.6 The 29 failing tests
`test_evidence_api.py` (25), `test_otel_export.py` (3), `test_evidence_ui.py` (1) — all from the
missing `artifacts/governance/events.jsonl`. Mostly cosmetic, **except** `test_demo_reset` and
`test_demo_reset_is_idempotent`, which are the live break in §4.1.

### 4.7 Smaller gaps
- Rules are **hardcoded per system id** (`services/evidence_api/rules.py:7`); `R1` literally
  matches tool names `place_order` / `confirm_order`. Not a general rule engine yet.
- ACAP findings never get control-library enrichment, so Failed Control and framework mappings
  stay blank in the live dashboard.
- `schemas/governance-event.schema.json` exists but **never validates anything** — validation is
  hand-rolled field checks.
- The "no raw text leaked" privacy check is 5 regexes matching restaurant-demo sentinel strings;
  for any other app it detects nothing.
- Scanner is AST + name heuristics, not dataflow — half the confidence score can come from a
  function being *named* something risky. No transitive call chains, no dynamic dispatch.
- No decision caching: one synchronous HTTP call (1s timeout) per governed action.
- `CLAUDE.md` is **stale** — its "Do not build yet" section forbids the backend, dashboard and
  frontend that now exist. Do not read it as current policy.
- Session work is **uncommitted** (13 files, 3-commit repo);
  `examples/enforcement-demo-app/run_mode_demo.py` is untracked.

---

## 5. Commands

```powershell
# ---- Install -------------------------------------------------------------
python -m pip install -e ./sdk-python          # [all] for adapters, [acap] for YAML support

# ---- Start backend + dashboard ------------------------------------------
# NOTE: uvicorn is only installed on C:\Users\shrey\anaconda4\python.exe
# Use port 8077 — SkyQuery and this API both default to 8000.
python -m uvicorn services.evidence_api.app:app --host 127.0.0.1 --port 8077
#   dashboard  http://127.0.0.1:8077/ui/
#   API docs   http://127.0.0.1:8077/docs
#   health     http://127.0.0.1:8077/health

# ---- SAFEST LIVE DEMO ----------------------------------------------------
# Whole loop in-process: no server, no AI calls, no API key, isolated temp DB.
python scripts/run_full_governance_loop_demo.py

# ---- Enforcement demos ---------------------------------------------------
cd examples/enforcement-demo-app
python run_demo.py --api http://127.0.0.1:8077          # --mode observe|shadow|enforce
python run_mode_demo.py --api http://127.0.0.1:8077     # live mode flip, no restart

# ---- Scanner -------------------------------------------------------------
python -m ai_governance scan examples/scanner-demo-app --output governance-discovery.json
python -m ai_governance upload-discovery governance-discovery.json --api http://127.0.0.1:8077

# ---- Enforcement mode over the API --------------------------------------
curl http://127.0.0.1:8077/systems/<system_id>/enforcement-mode
curl -X PATCH http://127.0.0.1:8077/systems/<system_id>/enforcement-mode \
     -H "Content-Type: application/json" -d '{"mode":"enforce"}'     # null clears the override

# ---- Kill switch ---------------------------------------------------------
curl -X POST http://127.0.0.1:8077/systems/<system_id>/kill-switches \
     -H "Content-Type: application/json" \
     -d '{"kill_switch_id":"disable_x","target_capabilities":["fetch_live_flights"],"enabled":true}'

# ---- Demo data reset -----------------------------------------------------
python scripts/run_demo_reset.py --in-process            # no server needed

# ---- Tests ---------------------------------------------------------------
python -m pytest tests -q        # expect 275 passed / 29 failed — that IS the baseline
```

### Two documented commands are broken — do not use
| Broken | Use instead |
|---|---|
| `python -m ai_governance scan <path> --system-id X` | `--system-id` doesn't exist on `scan`; pass it at `upload-discovery` |
| `cd services/evidence_api && uvicorn app:app` (in `DEMO_WALKTHROUGH.md`) | run from repo root: `uvicorn services.evidence_api.app:app` |

### Environment variables
| Var | Purpose |
|---|---|
| `GOVERNANCE_API_ENDPOINT` | Points the SDK at the backend |
| `EVIDENCE_DB_PATH` | Override SQLite path (used for isolated test DBs) |
| `GOVERNANCE_EVIDENCE=1` | Enables the legacy restaurant-agent probe |

---

## 6. SkyQuery integration (the demo target)

SkyQuery = FastAPI backend (:8000) + Next.js frontend (:3000). Agent7 goes in **the backend** — a
control running in the browser is bypassable by anyone who can call the API directly. Run Agent7
on **8077** to avoid the port clash.

Integration is two things, with **no edits inside any SkyQuery function**:

```python
from ai_governance import GovernanceClient
from ai_governance.adapters.fastapi import GovernanceMiddleware

gov = GovernanceClient.from_config(
    "governance.yaml",
    api_endpoint="http://127.0.0.1:8077",
    enforcement_mode="observe",      # observe | shadow | enforce
)
gov.instrument_from_config()
app.add_middleware(GovernanceMiddleware, governance_client=gov)
```

plus a `governance.yaml` listing capabilities, e.g.:

```yaml
system_id: skyquery
deployment_id: local-dev
environment: local
agent_id: skyquery-copilot
enforcement_mode: observe

capabilities:
  - name: execute_generated_sql
    module_path: app.services.query.execute_generated_sql
    action_type: execute
    status: approved
    data_classes: [flight, operational]
    denied_argument_patterns:
      - id: destructive_sql
        pattern: '(?i)\b(drop|delete|truncate|alter|grant|insert|update)\b'   # SINGLE quotes
```

> Write regexes in **single** quotes. A double-quoted YAML scalar turns `\b` into a literal
> backspace; the SDK rejects such a pattern rather than letting a deny rule silently never fire.

Full guide: `docs/generated/SKYQUERY_AGENT7_INTEGRATION_GUIDE.md`.

### Demo script (verified to work)
1. Start SkyQuery **once** with `enforcement_mode="observe"`. Never restart it again.
2. Dashboard mode control on **SDK default**.
3. Run a dangerous SQL prompt in Chat → **recorded but not blocked** (observe never blocks).
4. Click **Enforce** in the dashboard.
5. Run the **same** prompt → **blocked**: `DENY`, `argument_pattern_denied`, `denied_blocked`.
   The SQL never reaches Trino.
6. SkyQuery was not restarted and its code did not change.

### Three things to check in SkyQuery before committing to this
1. **Are the dangerous operations module-level functions or class methods?** Methods cannot be
   governed by the manifest path (§4.2). This is the one that can kill the demo.
2. **Import order.** A module that did `from x import fn` before `instrument_from_config()` keeps
   an ungoverned reference. Use `module.fn()` call sites, or instrument before importing routers.
3. **Observe-mode wrapping.** In `observe`, capabilities marked `denied`/`rejected` are never
   wrapped, so a later flip to `enforce` cannot govern them. Boot in `shadow` if you need that.
   (Approved capabilities — including the dangerous-SQL one — are always wrapped, so the demo
   above is unaffected.)

---

## 7. What to build next (prioritized)

### P0 — demo blockers
1. **Confirm SkyQuery's capability shape.** If its SQL/export ops are class methods, the manifest
   path governs nothing. Fix: apply `@gov.tool()` in SkyQuery source, **or** add class-attribute
   support to `_resolve_target()` in `manifest.py` (split on the last dot that resolves to a
   module, walk remaining attributes, `setattr` on the class).
2. **Commit the working tree.** 13 modified + 1 untracked file on a 3-commit repo.
3. **Decide the findings story.** Either regenerate `artifacts/governance/` (events.jsonl +
   `scenarios/manifest.json`) so `F-06236c96da2c` reproduces, or cut the Findings tab.

### P1 — makes the control trustworthy (the real product gap)
4. **Real approval verification.** Replace the dict-key check in `verify_approval_token()`
   (`sdk-python/ai_governance/enforcement.py:344`) with a signed, short-lived, action-bound token
   issued by something other than the governed process. **Biggest credibility gap.**
5. **Authentication on the API.** At minimum a shared-secret header; properly, per-operator
   identity so "who approved this capability" is real. Capability approval and kill-switch toggles
   are themselves privileged actions and should be governed.
6. **Label fixture vs live data.** `_system_record()` in `app.py` omits `source` for the six demo
   systems. Add it and render a badge, so frozen fixtures can never be mistaken for live data.

### P2 — generalize beyond the demo
7. **Generic rule engine** driven by the ACAP instead of hardcoded system ids.
   Plan: `docs/generated/GENERIC_RULE_ENGINE_PLAN.md`.
8. **Wire control-library enrichment into ACAP findings** (`run_all_acap_rules` never calls
   `control_library.enrich_finding`).
9. **Decision caching + policy version stamp** — avoid an HTTP round trip per action; stamp each
   record with the exact policy version it was decided under.
10. **Generalize the privacy leak check** (`core/validation.py:10-16`).
11. **Actually use the JSON Schema** for validation.

### P3 — scale and polish
Enforcement findings over the action tables; drift/rescan diff; scanner dataflow analysis; OTLP
export; real PyPI release (4 blockers in `TESTPYPI_RELEASE_REPORT.md`); replace `SYSTEM_REGISTRY`
with config; de-duplicate `governance_probe/` vs `_poc/` (~55 KB of byte-identical copies).

---

## 8. Recommended demo posture

**Lead with enforcement.** It is the strongest story and the part verified working end to end: a
dashboard click changes a running app's behaviour, and a dangerous query stops before it executes.

**Avoid:** the Findings tab (§4.1), any claim that the six listed systems are live (§4.5), and any
claim that approvals are cryptographically verified (§4.4).

**Useful framing:** this is a working prototype that proves the hard part — pre-execution control
of a running agent from a central policy plane. The remaining work is hardening (auth, real
approval tokens, caching), not architecture.
