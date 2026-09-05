# API and Data Model Reference

Complete reference for the Evidence API endpoints, SQLite schema, event schema, and data storage locations.

---

## API Endpoints

Base URL: `http://127.0.0.1:8000`

### Health & System Registry

#### GET /health
**Purpose:** Health check and basic status.

**Response:**
```json
{
    "ok": true,
    "events": 242,
    "database": "sqlite"
}
```

---

#### GET /systems
**Purpose:** List all registered AI systems.

**Response:**
```json
{
    "count": 2,
    "systems": [
        {
            "system_id": "restaurant-agent",
            "deployment_id": "local-test",
            "environment": "local",
            "purpose": "Restaurant ordering assistant...",
            "owner": "restaurant-agent developer"
        },
        {
            "system_id": "customer-refund-agent",
            "deployment_id": "local-test",
            "environment": "local",
            "purpose": "...",
            "owner": "..."
        }
    ]
}
```

**Note:** System list is derived from the `SYSTEM_REGISTRY` dict in `app.py`, which maps system IDs to their ACAP and events file paths.

---

#### GET /systems/{system_id}
**Purpose:** Get single system details.

**Response:** Single system_record object (same shape as items in `/systems`).

**Error:** 404 if system_id not in registry.

---

### ACAP Management

#### GET /systems/{system_id}/acap
**Purpose:** Get reviewed ACAP summary for a system.

**Response:**
```json
{
    "system": {
        "system_id": "restaurant-agent",
        "deployment_id": "local-test",
        "environment": "local",
        "purpose": "...",
        "owner": "..."
    },
    "acap": {
        "acap_id": "restaurant-agent-local-reviewed",
        "status": "reviewed",
        "reviewed_by": "Shrey / restaurant-agent developer",
        "reviewed_at": "2026-07-22",
        "tool_count": 6,
        "tools_with_approval": ["confirm_order"],
        "prohibited_count": 0,
        "raw_prompts": false,
        "raw_outputs": false
    }
}
```

---

#### GET /systems/{system_id}/acap/draft
**Purpose:** Generate a draft ACAP from discovery data, overrides, and runtime events.

**Response:** Full ACAP structure with:
- `system` block (system_id, deployment_id, environment, framework, purpose, owner)
- `content_policy` (raw_prompts, raw_outputs, tool_values)
- `agents` list (agent_id, framework, authorization)
- `models` list (provider, name, observed_names, authorization)
- `prompts` list (template_hash, length_chars, content_capture)
- `tools` list -- each tool includes:
  - `name`, `discovered`, `observed`
  - `proposed_action_type`, `proposed_external_side_effect`, `proposed_reversible`
  - `proposed_data_classes`, `proposed_target`
  - `authorization: "unresolved"` (always -- draft never authorizes)
  - `approval` (required, condition)
  - `observed_usage` (starts, successes, errors, error_types)
- `review_questions` (Q1-Q7 with targets)
- `reassess_when` triggers

---

#### POST /systems/{system_id}/acap/review
**Purpose:** Submit human review decisions for tool authorizations.

**Request body:**
```json
{
    "reviewed_by": "Alice",
    "decisions": [
        {
            "tool_name": "confirm_order",
            "authorization": "allowed_with_approval",
            "basis": "Requires customer confirmation before writing",
            "condition": "customer_confirmation",
            "approval_required": true
        },
        {
            "tool_name": "get_menu",
            "authorization": "allowed",
            "basis": "Read-only menu lookup"
        }
    ]
}
```

**Valid authorization values:** `allowed`, `prohibited`, `allowed_conditional`, `allowed_with_approval`

**Response:**
```json
{
    "system_id": "restaurant-agent",
    "decisions_stored": 2,
    "reviewed_by": "Alice"
}
```

---

#### GET /systems/{system_id}/acap/reviewed
**Purpose:** Get reviewed ACAP with human decisions applied.

**Logic:** Loads the base ACAP YAML, then overlays any `acap_reviews` from the database. If no DB reviews exist, falls back to the YAML file as-is.

**Response:** Full ACAP structure with authorization values reflecting human decisions.

---

### Evidence Ingestion

#### POST /evidence/events
**Purpose:** Ingest single or batch governance events.

**Request body (single):**
```json
{
    "event": {
        "schema_version": "0.1",
        "event_id": "uuid-here",
        "timestamp": "2026-07-17T14:08:15.811951+00:00",
        "system_id": "restaurant-agent",
        "deployment_id": "local-test",
        "environment": "local",
        "event_type": "tool_start",
        "trace_id": "uuid",
        "span_id": "uuid",
        "source": {"type": "langchain_callback"},
        "outcome": {"status": "started"}
    }
}
```

**Request body (batch):**
```json
{
    "events": [
        { "...event1..." },
        { "...event2..." }
    ],
    "session_ref": "optional-session-label"
}
```

**Response (success):**
```json
{
    "stored_total": 243,
    "accepted": 1,
    "duplicates": 0,
    "rejected": []
}
```

**Response (partial failure -- 422):**
```json
{
    "stored_total": 242,
    "accepted": 0,
    "duplicates": 0,
    "rejected": [
        {
            "event_id": "bad-event",
            "errors": ["missing required field: system_id"]
        }
    ]
}
```

**Validation rules:**
- All required fields must be present and non-empty strings
- `event_type` must be one of 16 valid types
- `outcome.status` must be started/success/error/unknown
- Timestamp must be valid ISO 8601 with timezone
- Raw text probes reject events containing system prompt text, order content, adversarial strings, or test markers
- `prompt.content_capture` of "full" or "sanitized" is rejected

---

#### POST /evidence/replay-jsonl
**Purpose:** Replay events from a JSONL file into the database.

**Request body:**
```json
{
    "path": "artifacts/governance/events.jsonl",
    "reset": true,
    "use_manifest_sessions": true
}
```

**Response:**
```json
{
    "source": "artifacts/governance/events.jsonl",
    "accepted": 242,
    "duplicates": 0,
    "rejected_count": 0,
    "rejected": [],
    "stored_total": 242
}
```

---

#### GET /evidence/events
**Purpose:** Paginated event retrieval.

**Query params:**
- `limit` (int, 1-5000, default 1000)
- `offset` (int, default 0)

**Response:**
```json
{
    "count": 242,
    "events": [
        {
            "schema_version": "0.1",
            "event_id": "...",
            "event_type": "tool_start",
            "tool": {
                "name": "confirm_order",
                "action_type": "write",
                "arguments_exposed": false
            },
            "_session_ref": "s5_adversarial",
            "_jsonl_line": 305
        }
    ]
}
```

**Privacy:** Events are passed through `public_event()` which removes `sanitized_arguments` and `result_summary`, replacing them with `arguments_exposed: false` and `summary_exposed: false`.

---

### Rules & Findings

#### POST /rules/run
**Purpose:** Execute evidence rules to generate findings.

**Request body (optional):**
```json
{
    "rule_ids": ["R1_confirm_without_proposal"]
}
```

If no body is provided, default rules run.

**Response:**
```json
{
    "rules": ["R1_confirm_without_proposal"],
    "events_evaluated": 242,
    "findings_created": 1,
    "findings": [
        {
            "finding_id": "F-06236c96da2c",
            "rule_id": "R1_confirm_without_proposal",
            "severity": "high",
            "session": "s5_adversarial",
            "event_ids": ["bef3e128-..."],
            "description": "confirm_order was invoked...",
            "failed_control": "AGT-AUTH-001",
            "framework_mappings": { "..." }
        }
    ]
}
```

---

#### GET /findings
**Purpose:** Query stored findings.

**Query params:**
- `system_id` (str, optional) -- filter by system

**Response:**
```json
{
    "count": 1,
    "findings": [ { "...finding_object..." } ]
}
```

---

### Coverage & Risk

#### GET /systems/{system_id}/coverage
**Purpose:** Evidence field coverage report.

**Response:**
```json
{
    "system_id": "restaurant-agent",
    "event_count": 242,
    "fields": [
        {
            "field": "schema_version / event_id / timestamp",
            "status": "captured",
            "presence": 1.0
        },
        {
            "field": "retrieval source identifiers",
            "status": "missing",
            "presence": 0.0,
            "note": "FAISS retriever invoked internally..."
        }
    ]
}
```

**17 fields tracked** with statuses: captured, captured_for_new_events, captured_with_annotation, annotation_required, partial, missing.

---

#### GET /systems/{system_id}/risk-profile
**Purpose:** Risk classification derived from ACAP.

**Response:**
```json
{
    "system_id": "restaurant-agent",
    "risk_profile": {
        "use_case": "Restaurant ordering assistant...",
        "environment": "local",
        "authority_level": "delegated",
        "autonomy_level": "human_in_loop",
        "data_sensitivity": "medium",
        "external_side_effects": true,
        "human_approval_model": "required_for_writes",
        "jurisdiction": null
    }
}
```

---

#### GET /systems/{system_id}/framework-applicability
**Purpose:** Determine which compliance frameworks apply.

**Response:**
```json
{
    "system_id": "restaurant-agent",
    "frameworks": [
        {
            "framework": "ACAP",
            "applicable": true,
            "reason": "System has 6 tools requiring authorization boundaries"
        },
        {
            "framework": "EU AI Act",
            "applicable": false,
            "reason": "No EU jurisdiction configured..."
        },
        {
            "framework": "ISO/IEC 42001",
            "applicable": "informational",
            "reason": "AI management system standard..."
        }
    ]
}
```

---

### Assessment

#### GET /systems/{system_id}/assessment
**Purpose:** Compute current assessment (not stored).

**Response:** Assessment object with coverage, findings summary, risk profile, framework applicability.

---

#### POST /systems/{system_id}/assessments/run
**Purpose:** Trigger a new assessment run and store the snapshot.

**Response:**
```json
{
    "assessment_id": "A-7f3a2b1c9e4d",
    "system_id": "restaurant-agent",
    "assessed_at": "2026-08-07T...",
    "overall_status": "requires_remediation",
    "evidence_confidence": "medium",
    "acap_status": "reviewed",
    "risk_profile": { "..." },
    "evidence_summary": {
        "event_count": 242,
        "coverage": {
            "captured": 12,
            "partial": 1,
            "annotation_required": 2,
            "missing": 1,
            "total_fields": 17
        }
    },
    "findings_summary": {
        "total": 1,
        "by_severity": {"high": 1, "medium": 0, "low": 0},
        "failed_controls": ["AGT-AUTH-001"]
    },
    "framework_applicability": [ "..." ],
    "framework_status": [
        {"framework": "ACAP", "status": "failed"},
        {"framework": "NIST AI RMF", "status": "needs_review"}
    ],
    "recommended_next_actions": [
        "Remediate 1 high-severity finding(s)...",
        "Add instrumentation for 1 missing evidence field(s)"
    ]
}
```

---

#### GET /systems/{system_id}/assessments
**Purpose:** List assessment history (most recent first).

**Response:**
```json
{
    "count": 2,
    "assessments": [
        {
            "assessment_id": "A-7f3a2b1c9e4d",
            "overall_status": "requires_remediation",
            "created_at": "2026-08-07T..."
        }
    ]
}
```

---

#### GET /assessments/{assessment_id}
**Purpose:** Retrieve a specific stored assessment by ID.

**Response:** Full assessment payload (same as POST response above).

---

### Reporting

#### GET /systems/{system_id}/assessment-report.md
**Purpose:** Export governance assessment as a Markdown document.

**Response:** `Content-Type: text/markdown`

Report sections:
1. Title & metadata
2. Executive summary (finding count, high-severity count, failed controls)
3. System profile table
4. Risk profile table
5. Reviewed ACAP summary
6. Evidence coverage table
7. Findings with control mappings, framework references, event timeline
8. Framework applicability table
9. Framework status
10. Recommended actions
11. Limitations disclaimer

---

### Demo/Admin

#### POST /demo/reset
**Purpose:** Full demo reset -- clear DB, replay all systems, run rules, create assessments.

**Response:**
```json
{
    "events_replayed": 264,
    "findings_created": 2,
    "systems": 2,
    "assessments": [
        {"system_id": "restaurant-agent", "assessment_id": "A-..."},
        {"system_id": "customer-refund-agent", "assessment_id": "A-..."}
    ]
}
```

---

## SQLite Schema

Database file: `services/evidence_api/evidence.db` (or `EVIDENCE_DB_PATH` env var).

### Table: events

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `event_id` | TEXT | PRIMARY KEY | Unique event identifier (UUID) |
| `timestamp` | TEXT | NOT NULL | ISO 8601 datetime with timezone |
| `session_ref` | TEXT | NOT NULL | Session grouping label |
| `session_id` | TEXT | | First-class session ID (newer events) |
| `system_id` | TEXT | | Multi-system identifier |
| `trace_id` | TEXT | NOT NULL | Root invocation trace ID |
| `span_id` | TEXT | NOT NULL | Component span ID |
| `parent_span_id` | TEXT | | Parent span for hierarchy |
| `event_type` | TEXT | NOT NULL | chain/llm/tool/retriever start/end/error |
| `component_kind` | TEXT | | chain, llm, tool, retriever |
| `component_name` | TEXT | | Component name |
| `tool_name` | TEXT | | Tool name (indexed) |
| `payload_json` | TEXT | NOT NULL | Full event JSON blob |
| `jsonl_line` | INTEGER | | Source JSONL line number |
| `ingested_at` | TEXT | NOT NULL | Ingestion timestamp |

### Table: findings

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `finding_id` | TEXT | PRIMARY KEY | Deterministic hash ID (F-{hash}) |
| `rule_id` | TEXT | NOT NULL | Rule that generated the finding |
| `system_id` | TEXT | | System filter |
| `session_ref` | TEXT | NOT NULL | Session where violation occurred |
| `severity` | TEXT | NOT NULL | high, medium, low |
| `event_ids_json` | TEXT | NOT NULL | JSON array of linked event IDs |
| `payload_json` | TEXT | NOT NULL | Full finding structure |
| `created_at` | TEXT | NOT NULL | Finding creation timestamp |

### Table: assessments

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `assessment_id` | TEXT | PRIMARY KEY | Hash ID (A-{hash}) |
| `system_id` | TEXT | NOT NULL | System reference |
| `overall_status` | TEXT | | satisfactory / needs_review / requires_remediation |
| `payload_json` | TEXT | NOT NULL | Full assessment snapshot |
| `created_at` | TEXT | NOT NULL | Assessment timestamp |

### Table: acap_reviews

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `system_id` | TEXT | NOT NULL | System reference |
| `tool_name` | TEXT | NOT NULL | Tool being reviewed |
| `field` | TEXT | NOT NULL | authorization or approval_required |
| `value` | TEXT | NOT NULL | Decision value |
| `basis` | TEXT | | Justification text |
| `condition` | TEXT | | Conditional clause |
| `provenance` | TEXT | NOT NULL, DEFAULT 'human_decision' | Decision source |
| `reviewed_by` | TEXT | | Reviewer name |
| `reviewed_at` | TEXT | NOT NULL | Decision timestamp |
| **PK** | | (system_id, tool_name, field) | Composite primary key |

---

## Event Schema (v0.1)

Defined in `schemas/governance-event.schema.json`.

### Required Fields

| Field | Type | Example |
|-------|------|---------|
| `schema_version` | string | "0.1" |
| `event_id` | string (UUID) | "8ce578c3-20c3-4847-93fb-b523735d9fac" |
| `timestamp` | string (ISO 8601) | "2026-07-17T14:08:15.811951+00:00" |
| `system_id` | string | "restaurant-agent" |
| `deployment_id` | string | "local-test" |
| `environment` | string | "local" |
| `event_type` | enum | "tool_start" |
| `trace_id` | string (UUID) | "019f7068-0fc3-7163-8cf3-69d2304d097e" |
| `span_id` | string (UUID) | "unique-per-component" |
| `source` | object | `{"type": "langchain_callback", "library": "langchain-core"}` |
| `outcome` | object | `{"status": "started"}` |

### Valid event_type Values (16)

`chain_start`, `chain_end`, `chain_error`, `llm_start`, `llm_end`, `llm_error`, `tool_start`, `tool_end`, `tool_error`, `retriever_start`, `retriever_end`, `retriever_error`, `approval_requested`, `approval_granted`, `approval_denied`, `custom`

### Valid outcome.status Values

`started`, `success`, `error`, `unknown`

### Optional Typed Sections

| Section | Key Fields | When Present |
|---------|-----------|--------------|
| `actor` | agent_id, identity_type | All events |
| `component` | kind, name, version | All events |
| `model` | provider, name | llm_start/end |
| `prompt` | template_hash, content_capture, message_count, roles | llm_start |
| `tool` | name, action_type, arguments_hash, sanitized_arguments, external_side_effect, target, reversible | tool_start/end |
| `approval` | required, granted, policy_id | tool events with approval logic |
| `data` | classifications, sources, destinations | Annotated events |
| `attributes` | input_shape, output_hash, result_hash, result_summary | Various |

### Valid tool.action_type Values

`read`, `write`, `communicate`, `execute`, `unknown`, `null`

### Valid prompt.content_capture Values

`none`, `hash`, `sanitized`, `full`

**Note:** `full` and `sanitized` are rejected by the Evidence API validator.

---

## Data Storage Locations

### Gitignored Artifacts (`artifacts/governance/`)

| File | Format | Purpose | Written By |
|------|--------|---------|------------|
| `events.jsonl` | JSONL | Canonical evidence stream | GovernanceEventWriter |
| `discovery.json` | JSON | Tool catalog + model/prompt fingerprints | discover_tools() |
| `coverage.json` | JSON | Field coverage report | coverage_report.py |
| `acap-draft.yaml` | YAML | Auto-generated ACAP (all unresolved) | acap_draft.py |
| `acap-reviewed.yaml` | YAML | Human-reviewed ACAP (source of truth) | acap_review.py |
| `acap-human-answers.yaml` | YAML | Human responses to review questions | acap_review.py |
| `findings.json` | JSON | Deterministic findings | findings.py |
| `findings.md` | Markdown | Human-readable findings | findings.py |
| `run-summary.md` | Markdown | Execution summary | verify_objective.py |
| `GO_NO_GO.md` | Markdown | Objective completion report | verify_objective.py |
| `scenarios/manifest.json` | JSON | Scenario line ranges + session mapping | scenario_runner.py |
| `otel/otlp-traces.json` | JSON | OTLP trace payloads | otel_export.py |
| `otel/mapping-report.json` | JSON | OTLP mapping validation | otel_export.py |

### Committed Configuration

| File | Format | Purpose |
|------|--------|---------|
| `governance-tool-overrides.yaml` | YAML | Human-maintained tool annotations |
| `control-library/canonical-controls.yaml` | YAML | Controls + framework mappings |
| `schemas/governance-event.schema.json` | JSON Schema | Event validation schema |
| `examples/refund-agent/acap-reviewed.yaml` | YAML | Refund agent ACAP |
| `examples/refund-agent/events.jsonl` | JSONL | Refund agent evidence |

### Runtime Database

| Location | Format | Purpose |
|----------|--------|---------|
| `services/evidence_api/evidence.db` | SQLite | API storage (events, findings, assessments, reviews) |
