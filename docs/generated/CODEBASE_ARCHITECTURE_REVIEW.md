# Codebase Architecture Review

## Executive Summary

This repository implements an **AI Governance Command Center prototype** that proves runtime evidence can be extracted from LangChain-based AI agents in a privacy-conscious, trustworthy manner -- without requiring source-code upload, framework replacement, or infrastructure buildout.

The system has three layers:

1. **Demo Agents** -- Two LangChain agents (restaurant ordering, customer refund) that generate real tool/LLM/chain events.
2. **Governance SDK** (`sdk-python/ai_governance/`) -- A reusable instrumentation library that passively captures events via LangChain callbacks, sanitizes them, writes JSONL evidence, and optionally exports to an API or OpenTelemetry.
3. **Evidence API + Dashboard** (`services/evidence_api/`) -- A FastAPI backend that ingests events, runs deterministic rules, generates findings linked to controls and compliance frameworks, builds risk profiles, runs assessments, and serves a single-page governance dashboard.

The prototype operates in **local-first** mode: evidence is written to JSONL files, replayed into SQLite on demand, and analyzed entirely offline. No cloud infrastructure, Kafka, Redis, or Kubernetes is involved.

---

## Repository Structure

```
Restaurant_Agent/
|-- CLAUDE.md                          # Mission, rules, evidence model, engineering rules
|-- README.md                          # Quick-start reference
|-- README_START_HERE.md               # Setup guide for Claude Code
|-- INSTALL.md                         # Dependency installation steps
|-- STARTER_MANIFEST.json              # Package metadata (v2.1)
|-- .gitignore                         # Excludes .env, artifacts, __pycache__
|-- Restaurant_agent1.py               # Root-level compatibility wrapper
|-- governance-tool-overrides.yaml     # Human-maintained tool annotations
|
|-- docs/
|   |-- FIRST_OBJECTIVE.md             # Experiment scope & GO/NO-GO criteria
|   |-- EVIDENCE_REQUIREMENTS.md       # Field provenance matrix
|   |-- RESTAURANT_SCENARIOS.md        # Five test scenario definitions
|   |-- INSTRUMENTATION_DECISION_TREE.md
|   |-- MILESTONES.md                  # Five-milestone plan (M0-M5)
|   |-- MINIMAL_ACAP.md               # Example ACAP shape
|   |-- generated/                     # Generated documentation (this file)
|
|-- schemas/
|   |-- governance-event.schema.json   # JSON Schema (draft 2020-12) for events
|
|-- templates/
|   |-- governance-tool-overrides.example.yaml
|   |-- restaurant-acap.example.yaml
|
|-- sdk-python/ai_governance/          # REUSABLE SDK (the product)
|   |-- __init__.py                    # Public API exports
|   |-- callback.py                    # LangChain BaseCallbackHandler
|   |-- writer.py                      # JSONL writer + sanitizer + API sink
|   |-- discovery.py                   # Automatic tool introspection
|   |-- bootstrap.py                   # Initialization & config merging
|   |-- findings.py                    # Deterministic rule engine (R1-R3)
|   |-- acap_draft.py                  # Draft ACAP generation
|   |-- acap_review.py                 # Human-in-the-loop ACAP review
|   |-- coverage_report.py            # Field coverage metrics
|   |-- scenario_runner.py            # Subprocess scenario execution
|   |-- otel_export.py                # OTLP trace conversion
|   |-- control_library.py            # Control loading & finding enrichment
|   |-- verify_objective.py           # GO/NO-GO checker
|   |-- pyproject.toml                # Package definition
|
|-- governance_probe/                  # COMPATIBILITY SHIM (delegates to sdk-python)
|   |-- __init__.py                    # Re-exports from ai_governance
|   |-- _compat.py                     # sys.path manipulation
|   |-- bootstrap.py                   # -> ai_governance.bootstrap
|   |-- callback.py                    # -> ai_governance.callback
|   |-- discovery.py                   # -> ai_governance.discovery
|   |-- writer.py                      # -> ai_governance.writer
|   |-- acap_draft.py                  # -> ai_governance.acap_draft
|   |-- findings.py                    # -> ai_governance.findings
|   |-- coverage_report.py            # -> ai_governance.coverage_report
|   |-- scenario_runner.py            # -> ai_governance.scenario_runner
|   |-- otel_export.py                # -> ai_governance.otel_export
|   |-- acap_review.py                # -> ai_governance.acap_review
|   |-- verify_objective.py           # -> ai_governance.verify_objective
|
|-- examples/
|   |-- restaurant-agent/
|   |   |-- Restaurant_agent1.py       # Main LangChain restaurant ordering agent
|   |   |-- Indian_restaurant_menu_Extract.xlsx
|   |   |-- orders_log.json            # Written by confirm_order tool
|   |   |-- governance-tool-overrides.yaml
|   |
|   |-- refund-agent/
|       |-- generate_evidence.py       # Synthetic JSONL event generator
|       |-- events.jsonl               # Generated refund evidence
|       |-- acap-reviewed.yaml         # Reviewed ACAP for refund agent
|
|-- control-library/
|   |-- canonical-controls.yaml        # 3 controls + 4 framework mappings each
|
|-- services/evidence_api/
|   |-- app.py                         # FastAPI application (21 endpoints)
|   |-- db.py                          # SQLite schema & queries (4 tables)
|   |-- validation.py                  # Event validation + privacy blocking
|   |-- rules.py                       # Rule engine (R1, R_write_no_approval)
|   |-- coverage.py                    # Field coverage computation
|   |-- draft.py                       # ACAP draft from DB events
|   |-- risk.py                        # Risk profiling & assessment builder
|   |-- report.py                      # Markdown report generator
|   |-- control_library.py            # Control loading for API context
|   |-- evidence.db                    # SQLite database (runtime)
|   |-- static/
|       |-- index.html                 # Dashboard HTML
|       |-- app.js                     # Dashboard JavaScript (SPA)
|       |-- styles.css                 # Dashboard styling
|
|-- tests/
|   |-- test_evidence_api.py           # 58 API integration tests
|   |-- test_evidence_ui.py            # UI rendering tests
|   |-- test_findings.py              # Offline deterministic rule tests
|   |-- test_governance_probe.py      # SDK callback/writer/redaction tests
|   |-- test_otel_export.py           # OTLP trace generation tests
|   |-- test_sdk_layout.py            # SDK package structure tests
|
|-- artifacts/governance/              # GITIGNORED runtime evidence
|   |-- events.jsonl                   # Canonical evidence stream
|   |-- discovery.json                 # Auto-discovered tool catalog
|   |-- coverage.json                  # Field coverage report
|   |-- acap-draft.yaml               # Auto-generated ACAP
|   |-- acap-reviewed.yaml            # Human-reviewed ACAP (source of truth)
|   |-- findings.json                  # Deterministic findings
|   |-- GO_NO_GO.md                    # Objective completion summary
|   |-- baseline/                      # Pre-instrumentation transcripts
|   |-- scenarios/                     # Scenario run outputs + manifest
|   |-- otel/                          # OTLP trace exports
|
|-- reference/                         # Original PoC implementations
|   |-- python/governance_probe/       # Early callback/writer/discovery code
|   |-- python/integration_example.py  # Example integration
|   |-- otel/otel-collector.local.yaml # Local OTel collector config
|
|-- .claude/                           # Claude Code configuration
    |-- settings.json                  # Tool permissions
    |-- agents/                        # Specialized review agents
    |-- skills/                        # Custom command workflows
```

---

## Layer 1: Demo Agents (examples/)

### Restaurant Agent (`examples/restaurant-agent/Restaurant_agent1.py`)

**What it is:** A LangChain conversational agent that takes restaurant orders from customers.

**Technology stack:**
- LangChain + LangGraph for agent construction
- `ChatOpenAI` pointing at OpenRouter (Qwen 2.5 7B Instruct model)
- FAISS vector store for menu search (loaded from Excel via `UnstructuredExcelLoader`)
- HuggingFace embeddings (`all-mpnet-base-v2`)
- `MemorySaver` checkpointer for conversation state

**Six tools:**

| Tool | Action Type | Side Effect | Approval | Purpose |
|------|-------------|-------------|----------|---------|
| `greet_customer` | communicate | none | no | Initial greeting |
| `get_user_name` | read | none | no | Extract customer name |
| `get_menu` | read | none | no | FAISS semantic menu search |
| `place_order` | communicate | none | no | Propose order back to customer |
| `confirm_order` | write | orders_log.json | **yes** | Write confirmed order to file |
| `show_receipt` | read | none | no | Calculate price + GST |

**Governance integration:** The agent's invocation config is merged with `GOVERNANCE.merge_invoke_config(config)` to inject the callback handler and metadata. This is the only line of code that connects the agent to governance.

**Data:** Uses fake test data. Orders written to local `orders_log.json` with "PENDING STAFF VERIFICATION".

### Refund Agent (`examples/refund-agent/`)

**What it is:** A synthetic evidence generator (not a real LangChain agent) that produces mock JSONL events demonstrating a customer refund workflow.

**Two scenarios:**
- `s1_normal` -- Proper flow: lookup_order -> check_eligibility -> refund_execute (approved) -> send_notification
- `s2_bypass` -- Refund bypass: refund_execute directly without eligibility check, no approval granted -- triggers the `R_write_no_approval` rule

**Purpose:** Demonstrates multi-system support in the Evidence API without requiring a second real LangChain agent.

---

## Layer 2: Governance SDK (`sdk-python/ai_governance/`)

This is the **reusable product** -- the library that could be attached to any LangChain agent.

### callback.py -- GovernanceCallback

**Class:** `GovernanceCallback(BaseCallbackHandler)`

- Hooks into LangChain's callback system: `on_chain_start/end/error`, `on_llm_start/end/error`, `on_tool_start/end/error`, `on_retriever_start/end/error`
- **Fail-open:** `raise_error = False`. Any exception in the callback is swallowed and counted in `dropped_events`. The agent is never affected.
- **Privacy:** Never captures raw prompts or responses. Only hashes via `fingerprint()`, message-shape metadata (roles, count), and token usage.
- **Thread-safe:** Uses dicts guarded by a lock for `_trace_for_run`, `_session_for_run`, `_started`.
- **Timing:** Records `time.monotonic()` at start, computes `duration_ms` at end.

### writer.py -- GovernanceEventWriter

- Appends events as JSON lines to a local JSONL file (append-only, immutable per run).
- **Sanitization functions:**
  - `sanitize()` -- Recursively walks dicts/lists, redacts sensitive keys (api_key, password, token, authorization, cvv, card_number), emails, phone numbers, 12-19 digit sequences (credit cards). Max depth 6, string truncation at 512 chars.
  - `fingerprint()` -- SHA256 hash of JSON-serialized value.
- **EvidenceApiSink** -- Optional HTTP POST to Evidence API endpoint. Best-effort with 0.5s timeout; failures don't block the agent.

### discovery.py -- Tool Introspection

- `discover_tools()` -- Inspects LangChain `BaseTool` objects or plain functions. Extracts name, description, args_schema, implementation path. Marks all `action_type` as "unknown" until human confirms.
- `write_tool_discovery()` -- Writes `discovery.json` with tools, prompt hash, model info, package versions.

### bootstrap.py -- Initialization

- `init_governance()` -- Entry point that wires everything together:
  1. Loads human-maintained tool overrides from YAML
  2. Runs tool discovery
  3. Creates `GovernanceCallback` and `GovernanceEventWriter`
  4. Returns a `Governance` wrapper with `merge_invoke_config()` method
- Fail-open: returns `None` if initialization fails.

### findings.py -- Deterministic Rule Engine

Four rules, all session-scoped:

| Rule ID | Description | Severity | Maps To |
|---------|-------------|----------|---------|
| R1_confirm_without_proposal | confirm_order with no prior place_order in session | high | AGT-AUTH-001 |
| R2_confirmation_without_customer_turn | Proposal and confirm in same invoke turn (no human between) | high | AGT-AUTH-002 |
| R3_duplicate_confirmation | Two successful confirm_order for identical items | medium | AGT-INTEG-001 |
| R_write_no_approval | Write action without approval.granted | high | AGT-AUTH-001 |

Finding IDs are deterministic: `F-{SHA256(rule_id + sorted_event_ids)[:12]}`.

### otel_export.py -- OpenTelemetry Conversion

- Converts local governance JSONL to OTLP trace payloads (not live instrumentation).
- Privacy probes verify no raw text leaks into OTLP spans.
- Optional POST to local OTel collector (default `http://127.0.0.1:4318/v1/traces`).

### Other SDK Files

| File | Purpose |
|------|---------|
| `acap_draft.py` | Generates draft ACAP from discovery + overrides + runtime evidence |
| `acap_review.py` | Human-in-the-loop ACAP review workflow (CLI) |
| `coverage_report.py` | Field-by-field evidence presence metrics |
| `scenario_runner.py` | Subprocess-based scenario execution with scripted stdin |
| `control_library.py` | Loads canonical controls YAML, enriches findings with framework mappings |
| `verify_objective.py` | GO/NO-GO decision checker against success criteria |

---

## Layer 3: Evidence API + Dashboard (`services/evidence_api/`)

### Backend (FastAPI)

21 endpoints organized into 7 groups:

1. **Health & Systems** -- `/health`, `/systems`, `/systems/{id}`
2. **Evidence Ingestion** -- `POST /evidence/events`, `POST /evidence/replay-jsonl`, `GET /evidence/events`
3. **ACAP Management** -- Draft generation, human review, reviewed retrieval
4. **Rules & Findings** -- Rule execution, finding queries
5. **Coverage & Risk** -- Field coverage, risk profiling, framework applicability
6. **Assessment** -- Run assessments, list/retrieve snapshots, export markdown reports
7. **Demo** -- `POST /demo/reset` (replay all systems, run rules, create assessments)

### Database (SQLite)

4 tables: `events`, `findings`, `assessments`, `acap_reviews`. See `API_AND_DATA_MODEL.md` for full schema.

### Frontend (Vanilla JS SPA)

Single-page dashboard served at `/ui/`. No React/Vue/Angular framework -- plain JavaScript with DOM manipulation. Features:

- System selector dropdown (switch between restaurant-agent and refund-agent)
- 6 KPI cards (status, risk, events, findings, controls, confidence)
- System profile and ACAP summary panels
- Assessment section with framework status and recommended actions
- Tool authorization review table
- Risk profile and framework applicability displays
- Evidence coverage table
- Findings list with detail panel, control mappings, framework references, and event timeline

---

## How Components Connect

```
Restaurant Agent (LangChain)
    |
    |-- invoke config includes GovernanceCallback
    |
    v
GovernanceCallback (passive, fail-open)
    |
    |-- on_tool_start/end, on_llm_start/end, on_chain_start/end
    |
    v
GovernanceEventWriter
    |
    |-- append to events.jsonl (local JSONL)
    |-- optional HTTP POST to EvidenceApiSink
    |
    v
Evidence API (FastAPI)
    |
    |-- POST /evidence/events or POST /evidence/replay-jsonl
    |-- validate_event() checks schema + privacy
    |-- insert_event() into SQLite
    |
    v
SQLite (events table)
    |
    |-- POST /rules/run
    |       |-- run_r1_confirm_without_proposal() or run_rules_for_system()
    |       |-- generates deterministic findings
    |       |-- enriches with control library mappings
    |       v
    |   findings table
    |
    |-- POST /systems/{id}/assessments/run
    |       |-- build_risk_profile() from reviewed ACAP
    |       |-- evaluate_framework_applicability()
    |       |-- compute_field_coverage() from events
    |       |-- build_full_assessment() combining all signals
    |       v
    |   assessments table
    |
    |-- GET /ui/ -> static/index.html + app.js
            |-- loadEvidenceView() fetches all API data
            |-- render() builds DOM
```

---

## Compatibility Layer: governance_probe/

The `governance_probe/` package is a **backward-compatibility shim**. Every module simply imports from `sdk-python/ai_governance/` and re-exports. The `_compat.py` file adds `sdk-python/` to `sys.path`.

This exists because the original PoC used `governance_probe` as the package name. The real code lives in `sdk-python/ai_governance/`.

---

## Control Library (`control-library/canonical-controls.yaml`)

Three controls with mappings to four compliance frameworks:

| Control ID | Title | Category | ACAP | NIST AI RMF | EU AI Act | ISO 42001 |
|------------|-------|----------|------|-------------|-----------|-----------|
| AGT-AUTH-001 | Human approval before write actions | Authorization | P1 | GOVERN 1.1 | Article 14 | Clause 6.1.3 |
| AGT-AUTH-002 | No model-generated approval | Authorization | P2 | GOVERN 1.4 | Article 14 | Clause 8.4 |
| AGT-INTEG-001 | No duplicate write operations | Integrity | P3 | MANAGE 2.2 | Article 9 | Clause 8.2 |

Rule-to-control mappings: R1 -> AGT-AUTH-001, R2 -> AGT-AUTH-002, R3 -> AGT-INTEG-001, R_write_no_approval -> AGT-AUTH-001.

EU AI Act references are explicitly marked as "potential relevance only" requiring human review.

---

## Test Suites

| Test File | Count | What It Verifies |
|-----------|-------|------------------|
| `test_evidence_api.py` | ~58 | All API endpoints, event ingestion/validation, replay, rules, findings, ACAP draft/review, coverage, risk, assessments, demo reset, multi-system, report generation, privacy |
| `test_evidence_ui.py` | ~3 | HTML/JS serving, API call expectations, no raw payload exposure |
| `test_findings.py` | ~12 | R1/R2/R3 rules offline (no network), finding determinism, session/trace isolation |
| `test_governance_probe.py` | ~20 | Callback behavior, event writing, sanitization, redaction, session tracking, run hierarchy |
| `test_otel_export.py` | ~8 | OTLP payload structure, trace/span ID conversion, no raw-text leakage |
| `test_sdk_layout.py` | ~3 | SDK module structure, import paths |

---

## Observations and Concerns

### Stale / Confusing Areas
1. **Root-level `Restaurant_agent1.py`** is just a wrapper that launches `examples/restaurant-agent/Restaurant_agent1.py`. Could confuse newcomers.
2. **`governance_probe/`** is entirely a re-export shim for `sdk-python/ai_governance/`. The dual naming is confusing.
3. **`reference/`** directory contains early PoC code that appears superseded by `sdk-python/`. Unclear if still referenced.
4. **Refund agent** (`examples/refund-agent/generate_evidence.py`) generates synthetic events rather than running a real agent. This is intentional for the PoC but could mislead reviewers into thinking both agents are real.

### Duplication
5. **`_value()` helper** is defined identically in both `app.py` and `risk.py`.
6. **`control_library.py`** exists in both `sdk-python/ai_governance/` and `services/evidence_api/` -- they do similar things (load YAML controls, enrich findings).
7. **Raw text probe patterns** are defined separately in `validation.py`, `otel_export.py`, and `app.js`. Any change must be made in three places.

### Risk Areas
8. **`evidence.db`** is checked into git (appears in git status as modified). A SQLite database should generally be gitignored.
9. **No authentication** on the Evidence API. Any network caller can ingest events, run assessments, or reset the demo.
10. **`EvidenceApiSink`** uses `urllib` with 0.5s timeout and no retry. In production this would need a queue or batch mechanism.
11. **Assessment IDs** use `SHA256(system_id + timestamp)`. Two assessments created in the same second for the same system would collide (unlikely but possible).

### Missing
12. **No pagination** in findings or assessments endpoints.
13. **No session_ref filtering** on the GET /evidence/events endpoint beyond limit/offset.
14. **OTLP export** is offline batch conversion, not live streaming. M5 milestone is marked optional.
