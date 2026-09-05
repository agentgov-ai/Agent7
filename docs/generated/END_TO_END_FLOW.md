# End-to-End Flow

This document traces the complete runtime path from AI agent invocation through to the governance dashboard, covering every stage of evidence generation, ingestion, analysis, and presentation.

---

## The Full Pipeline

```
AI Agent (LangChain)
    |
    v
SDK Callback (GovernanceCallback)
    |
    v
Event Schema (governance-event v0.1)
    |
    +---> Local JSONL file (events.jsonl)
    +---> HTTP POST to Evidence API (optional)
    +---> OTLP export (offline batch, optional)
    |
    v
Evidence API (FastAPI)
    |
    v
SQLite Database (events table)
    |
    v
Rules Engine (deterministic)
    |
    v
Findings (linked to events)
    |
    v
Control Library (canonical-controls.yaml)
    |
    v
Framework Mappings (ACAP, NIST, EU AI Act, ISO 42001)
    |
    v
Assessment (risk profile + coverage + findings + frameworks)
    |
    v
Dashboard UI (vanilla JS SPA)
```

---

## Stage 1: Agent Invocation

### Restaurant Agent

1. User starts the agent: `python Restaurant_agent1.py`
2. `init_governance()` is called in `bootstrap.py`:
   - Loads tool overrides from `governance-tool-overrides.yaml`
   - Runs `discover_tools()` to introspect all 6 LangChain tools
   - Creates `GovernanceEventWriter` pointing at `artifacts/governance/events.jsonl`
   - Creates `GovernanceCallback` with the writer and metadata (system_id, deployment_id, environment, agent_id)
   - Returns a `Governance` wrapper object
3. The agent's invocation config is merged: `GOVERNANCE.merge_invoke_config(config)` injects the callback into `config["callbacks"]` and adds governance metadata to `config["metadata"]`.
4. The agent runs its conversation loop using LangGraph's `create_agent()` with `MemorySaver` checkpointer.

### Refund Agent

The refund agent is not a real LangChain agent. `generate_evidence.py` directly constructs JSONL events that mimic what the SDK would produce. This lets the Evidence API demonstrate multi-system support without requiring a second real agent setup.

---

## Stage 2: SDK Callback Event Capture

When the LangChain agent executes, the `GovernanceCallback` receives lifecycle events:

### What triggers each event type:

| LangChain Hook | Event Type | What's Captured |
|----------------|------------|-----------------|
| `on_chain_start` | `chain_start` | Component name, input shape (keys only, no content) |
| `on_chain_end` | `chain_end` | Duration, output hash |
| `on_chain_error` | `chain_error` | Error type, error message (sanitized) |
| `on_llm_start` | `llm_start` | Model name/provider, message count, roles, prompt template hash |
| `on_llm_end` | `llm_end` | Duration, token usage (prompt/completion/total), output hash |
| `on_llm_error` | `llm_error` | Error type |
| `on_tool_start` | `tool_start` | Tool name, action_type, sanitized arguments, approval status |
| `on_tool_end` | `tool_end` | Duration, result hash, sanitized result summary |
| `on_tool_error` | `tool_error` | Error type |
| `on_retriever_start` | `retriever_start` | Query hash |
| `on_retriever_end` | `retriever_end` | Document count |

### What is NOT captured (by design):

- Raw prompt text (only SHA256 hash of the prompt template)
- Raw LLM response text (only hash)
- Raw tool argument values (only sanitized summaries)
- Raw tool results (only hash + sanitized summary)
- Customer names, email, phone, card numbers (redacted by `sanitize()`)
- API keys, tokens, passwords (redacted by sensitive key detection)

### Trace hierarchy:

Each agent invocation gets a `trace_id` (from LangChain's `run_id` at the root). Each component within the invocation gets a unique `span_id`. Parent-child relationships are tracked via `parent_span_id`:

```
chain_start (trace_id=T1, span_id=S1, parent=null)     # LangGraph root
  |-- llm_start (trace_id=T1, span_id=S2, parent=S1)   # Model call
  |-- llm_end   (trace_id=T1, span_id=S2, parent=S1)
  |-- tool_start (trace_id=T1, span_id=S3, parent=S1)  # Tool invocation
  |-- tool_end   (trace_id=T1, span_id=S3, parent=S1)
  |-- llm_start (trace_id=T1, span_id=S4, parent=S1)   # Next model call
  ...
chain_end (trace_id=T1, span_id=S1, parent=null)
```

---

## Stage 3: Event Schema

Every event conforms to the governance-event schema v0.1 (`schemas/governance-event.schema.json`).

### Required fields:
- `schema_version` -- Always "0.1"
- `event_id` -- UUID4
- `timestamp` -- ISO 8601 with timezone
- `system_id` -- e.g. "restaurant-agent"
- `deployment_id` -- e.g. "local-test"
- `environment` -- e.g. "local"
- `event_type` -- One of 16 types (chain/llm/tool/retriever start/end/error, approval_*, custom)
- `trace_id` -- Root invocation ID
- `span_id` -- This component's ID
- `source` -- `{type: "langchain_callback", library: "langchain-core", library_version: "1.2.17"}`
- `outcome` -- `{status: "started"|"success"|"error", duration_ms, error_type}`

### Optional typed sections:
- `actor` -- `{agent_id, identity_type}`
- `component` -- `{kind: "chain"|"llm"|"tool"|"retriever", name, version}`
- `model` -- `{provider, name}`
- `prompt` -- `{template_id, template_hash, content_capture: "hash"|"none", message_count, roles}`
- `tool` -- `{name, action_type, arguments_hash, sanitized_arguments, external_side_effect, target, reversible}`
- `approval` -- `{required, granted, policy_id}`
- `data` -- `{classifications, sources, destinations}`
- `attributes` -- `{input_shape, output_hash, result_hash, result_summary}`

---

## Stage 4: JSONL Writing

The `GovernanceEventWriter` in `writer.py`:

1. Receives the event dict from the callback.
2. Applies `sanitize()` recursively to all string values:
   - Emails -> `<redacted-email>`
   - Phone numbers -> `<redacted-phone>`
   - 12-19 digit sequences -> `<redacted-number>`
   - Sensitive dict keys (api_key, password, token, etc.) -> `<redacted>`
   - Strings > 512 chars -> truncated with `...<truncated>`
3. Serializes to JSON and appends one line to `artifacts/governance/events.jsonl`.
4. The file is append-only and immutable during a test run.

### Optional: HTTP API Sink

If `GOVERNANCE_API_ENDPOINT` is set (or passed to `init_governance`), the writer also POSTs each event to the Evidence API:

```python
EvidenceApiSink(endpoint="http://127.0.0.1:8000")
# POST /evidence/events with {"event": {...}}
# Timeout: 0.5 seconds. Failures are logged but never block the agent.
```

---

## Stage 5: Evidence API Ingestion

The Evidence API receives events through two paths:

### Path A: Live ingestion (`POST /evidence/events`)

- Accepts single event or batch: `{"event": {...}}` or `{"events": [...]}`
- Each event passes through `validate_event()`:
  - Checks all required fields present and non-empty
  - Validates event_type against enum
  - Validates outcome.status against enum
  - Checks timestamp is valid ISO with timezone
  - Runs raw text probes (rejects events containing system prompt text, order text, adversarial text, or test markers)
  - Rejects `prompt.content_capture` of "full" or "sanitized"
- Valid events are inserted into SQLite via `db.insert_event()`
- Duplicates (same event_id) are silently skipped
- Response: `{"stored_total": N, "accepted": N, "duplicates": N, "rejected": [...]}`

### Path B: JSONL replay (`POST /evidence/replay-jsonl`)

- Reads a JSONL file line by line
- Optionally resets the DB first (`reset: true`)
- Uses scenario manifest (`manifest.json`) to map JSONL line numbers to session references
- Each event validated and inserted same as Path A
- Used primarily for demo setup: `POST /demo/reset` replays both restaurant-agent and refund-agent event files

---

## Stage 6: SQLite Storage

Events are stored in the `events` table:

```sql
CREATE TABLE events (
    event_id        TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    session_ref     TEXT NOT NULL,
    session_id      TEXT,
    system_id       TEXT,
    trace_id        TEXT NOT NULL,
    span_id         TEXT NOT NULL,
    parent_span_id  TEXT,
    event_type      TEXT NOT NULL,
    component_kind  TEXT,
    component_name  TEXT,
    tool_name       TEXT,
    payload_json    TEXT NOT NULL,    -- full event JSON
    jsonl_line      INTEGER,         -- source line number
    ingested_at     TEXT NOT NULL
);
```

Key design decisions:
- Full event payload stored as JSON blob in `payload_json` for flexibility
- Indexed columns (`tool_name`, `session_ref`, `system_id`) for query performance
- `jsonl_line` preserves the link back to the source JSONL file
- Duplicates are rejected by PRIMARY KEY constraint on `event_id`

---

## Stage 7: Rules Engine

When `POST /rules/run` is called (or during `POST /systems/{id}/assessments/run`):

### R1_confirm_without_proposal (restaurant-agent)

1. Load all events from SQLite, ordered by session_ref, jsonl_line, timestamp
2. Group by session_ref
3. For each session:
   - Scan events in order
   - Track whether `place_order` tool_start has been seen
   - If `confirm_order` tool_start appears without prior `place_order` -> **FINDING**
4. Build finding with deterministic ID: `F-{SHA256("R1|" + sorted_event_ids)[:12]}`
5. Enrich with control library: maps to AGT-AUTH-001 and its framework references

### R_write_no_approval (refund-agent)

1. Same event loading and session grouping
2. For each `tool_start` event where:
   - `tool.action_type == "write"`
   - `approval.required == true`
   - `approval.granted != true`
   -> **FINDING**
3. Deterministic ID and control enrichment same as R1

### Finding structure:

```json
{
    "finding_id": "F-06236c96da2c",
    "rule_id": "R1_confirm_without_proposal",
    "acap_id": "restaurant-agent-local-reviewed",
    "violates": "P1",
    "severity": "high",
    "session": "s5_adversarial",
    "event_ids": ["bef3e128-513d-4484-86d2-603c8916e220"],
    "trace_ids": ["..."],
    "outcome_event_id": "...",
    "outcome_status": "success",
    "description": "confirm_order was invoked with no prior place_order proposal...",
    "failed_control": "AGT-AUTH-001",
    "failed_control_title": "Agent must obtain human approval before executing write actions",
    "framework_mappings": {
        "ACAP": {"section": "P1", "reference": "..."},
        "NIST_AI_RMF": {"function": "GOVERN", "category": "GOVERN 1.1"},
        "EU_AI_Act": {"article": "Article 14"},
        "ISO_42001": {"clause": "Clause 6.1.3"}
    }
}
```

---

## Stage 8: Control Library & Framework Mapping

The `control_library.py` module loads `control-library/canonical-controls.yaml` and enriches findings:

1. Look up `rule_mappings[finding.rule_id]` -> get `control_id` (e.g. "AGT-AUTH-001")
2. Find the control definition with that ID
3. Add to finding:
   - `failed_control` = control_id
   - `failed_control_title` = control title
   - `framework_mappings` = ACAP, NIST AI RMF, EU AI Act, ISO 42001 references

This creates a traceable chain: **event -> finding -> rule -> control -> framework requirement**.

---

## Stage 9: Risk Profile & Assessment

### Risk Profile (`risk.py:build_risk_profile()`)

Derived from the reviewed ACAP structure:

| Signal | Derivation |
|--------|------------|
| `authority_level` | advisory (no writes), delegated (all writes need approval), autonomous (writes without approval) |
| `autonomy_level` | human_in_loop (approval required), human_on_loop (side effects exist), fully_autonomous |
| `data_sensitivity` | high (payment/financial/health/biometric), medium (contact/personal/pii), low |
| `external_side_effects` | True if any tool has `external_side_effect` |
| `human_approval_model` | required_for_writes, partial, not_required |

### Framework Applicability (`risk.py:evaluate_framework_applicability()`)

| Framework | When Applicable |
|-----------|----------------|
| ACAP | tool_count > 0 |
| OWASP Agentic | Tools or agents present |
| NIST AI RMF | Always |
| EU AI Act | EU jurisdiction AND (autonomous authority OR high data sensitivity) |
| ISO/IEC 42001 | Always (informational) |

### Assessment (`risk.py:build_full_assessment()`)

Combines all signals into a frozen snapshot:

1. `overall_status` = `requires_remediation` if high-severity findings, `needs_review` if any findings, `satisfactory` if clean
2. `evidence_confidence` = `high` if all fields captured, `low` if fields missing, `medium` if partial/annotation_required
3. `framework_status` = per-framework pass/fail based on findings and applicability
4. `recommended_next_actions` = remediation steps based on gaps
5. Assessment stored with deterministic `assessment_id` = `A-{SHA256(system_id + timestamp)[:12]}`

---

## Stage 10: Dashboard UI

The frontend (`static/app.js`) is a vanilla JavaScript SPA:

### Data loading (`loadEvidenceView()`):

1. Fetch `/systems` -- get list of registered systems
2. Fetch `/health` -- get event count and DB status
3. For the selected system:
   - `GET /systems/{id}/acap` -- reviewed ACAP summary
   - `GET /systems/{id}/acap/draft` -- draft ACAP with tool stats
   - `GET /systems/{id}/coverage` -- field coverage report
   - `GET /systems/{id}/risk-profile` -- risk classification
   - `GET /systems/{id}/framework-applicability` -- framework matrix
   - `GET /systems/{id}/assessments` -- assessment history
   - `GET /assessments/{latest_id}` -- latest assessment detail
4. `GET /findings?system_id={id}` -- findings for this system
5. `GET /evidence/events` -- paginated events

### Rendering pipeline:

```
state object populated
    |
    v
render()
    |-- renderKpiStrip()         -> 6 KPI cards (status, risk, events, findings, controls, confidence)
    |-- renderSystem()           -> system profile + ACAP summary panels
    |-- renderLatestAssessment() -> assessment status, framework status, recommendations
    |-- renderAcapReview()       -> tool authorization table
    |-- renderRiskProfile()      -> risk classification display
    |-- renderApplicability()    -> framework applicability table
    |-- renderCoverage()         -> evidence coverage table
    |-- renderFindingsList()     -> clickable finding buttons (left panel)
    |-- renderDetails()          -> selected finding detail (right panel)
            |-- renderControlAndFrameworks()  -> framework mapping cards
            |-- renderEventIds()              -> linked event ID chips
            |-- renderTimeline()             -> event timeline with highlights
```

### User interactions:

| Action | What Happens |
|--------|-------------|
| Select system from dropdown | Reloads all data for that system |
| Click "Run Assessment" | `POST /systems/{id}/assessments/run`, reloads |
| Click "Reset Demo" | `POST /demo/reset`, reloads all |
| Click "Export Report" | Opens `GET /systems/{id}/assessment-report.md` in new tab |
| Click a finding | Shows detail panel with control mapping, framework references, event timeline |

---

## OTLP / OpenTelemetry Export (Optional, Offline)

This is a **batch conversion**, not live streaming:

1. Read `artifacts/governance/events.jsonl`
2. Convert each event to an OTLP span:
   - `trace_id` -> 32-char hex (padded from governance UUID)
   - `span_id` -> 16-char hex (padded from governance UUID)
   - `parent_span_id` -> from event hierarchy
   - Attributes from event metadata (component, model, tool, etc.)
3. Strip privacy-sensitive fields (sanitized_arguments, result_summary)
4. Run privacy probes to verify no raw text leaked
5. Write to `artifacts/governance/otel/otlp-traces.json`
6. Optionally POST to local OTel collector at `http://127.0.0.1:4318/v1/traces`
7. Generate mapping report at `artifacts/governance/otel/mapping-report.json`

Command: `python -m governance_probe.otel_export --no-send`

---

## Session Management

Sessions group related events from a single agent interaction. Two mechanisms exist:

1. **New events**: Include a `session_id` field directly in the event (added in later SDK versions).
2. **Historical events**: Use the scenario manifest (`artifacts/governance/scenarios/manifest.json`) which maps JSONL line ranges to session references. During replay, `_manifest_session_lookup()` builds a `{line_number: session_ref}` mapping.

This dual mechanism is a backward-compatibility concern flagged in the codebase -- newer events should always include `session_id`.

---

## Key Design Principles Visible in the Flow

1. **Privacy by default** -- Raw content never captured; hashes and sanitized summaries only.
2. **Fail-open** -- Governance layer never crashes the agent. Dropped events are counted but swallowed.
3. **Deterministic findings** -- Same events always produce same finding IDs. No ML/LLM in the rules.
4. **Evidence traceability** -- Every finding links to exact event IDs, which link to trace/span hierarchy.
5. **Observed != Authorized** -- Discovery proposes tool capabilities, but authorization is always "unresolved" until a human confirms via ACAP review.
6. **Local-first** -- JSONL is the source of truth. SQLite, API, and OTLP are derived views.
