# Architecture Graphs

Mermaid diagrams for the AI Governance Command Center prototype.

---

## 1. System Architecture Overview

```mermaid
graph TB
    subgraph "Demo Agents"
        RA["Restaurant Agent<br/>(LangChain + LangGraph)"]
        RF["Refund Agent<br/>(Synthetic Events)"]
    end

    subgraph "Governance SDK (sdk-python/ai_governance/)"
        CB["GovernanceCallback<br/>(BaseCallbackHandler)"]
        WR["GovernanceEventWriter<br/>(sanitize + fingerprint)"]
        DS["discover_tools()"]
        BS["bootstrap.py<br/>init_governance()"]
        FN["findings.py<br/>(R1, R2, R3, R_write)"]
        CL["control_library.py"]
        OT["otel_export.py"]
    end

    subgraph "Evidence API (services/evidence_api/)"
        FA["FastAPI app.py<br/>(21 endpoints)"]
        VL["validation.py"]
        DB["SQLite<br/>(events, findings,<br/>assessments, acap_reviews)"]
        RL["rules.py"]
        CV["coverage.py"]
        DR["draft.py"]
        RK["risk.py"]
        RP["report.py"]
        CL2["control_library.py"]
    end

    subgraph "Frontend"
        UI["Dashboard SPA<br/>(static/app.js)"]
    end

    subgraph "Storage"
        JSONL["events.jsonl<br/>(append-only)"]
        DISC["discovery.json"]
        ACAP["acap-reviewed.yaml"]
        CTRL["canonical-controls.yaml"]
        OTLP["otlp-traces.json"]
    end

    RA -->|callbacks| CB
    BS --> CB
    BS --> DS
    DS --> DISC
    CB --> WR
    WR --> JSONL
    WR -.->|optional HTTP| FA
    RF -->|generate_evidence.py| JSONL

    FA --> VL
    VL --> DB
    FA --> RL
    RL --> DB
    RL --> CL2
    CL2 --> CTRL
    FA --> CV
    FA --> DR
    DR --> DB
    FA --> RK
    RK --> ACAP
    FA --> RP

    OT --> JSONL
    OT --> OTLP

    UI -->|fetch| FA
```

---

## 2. Evidence Ingestion Flow

```mermaid
sequenceDiagram
    participant Agent as LangChain Agent
    participant CB as GovernanceCallback
    participant WR as EventWriter
    participant JSONL as events.jsonl
    participant API as Evidence API
    participant VAL as validate_event()
    participant DB as SQLite

    Note over Agent: Agent executes tool/LLM/chain

    Agent->>CB: on_tool_start(tool_name, input, run_id)
    CB->>CB: Map run_id to trace_id/span_id
    CB->>CB: Build event dict (no raw content)
    CB->>WR: write(event)
    WR->>WR: sanitize() all string values
    WR->>WR: Redact emails, phones, cards, keys
    WR->>JSONL: Append JSON line

    opt EvidenceApiSink configured
        WR->>API: POST /evidence/events
        API->>VAL: validate_event(event)
        VAL->>VAL: Check required fields
        VAL->>VAL: Check event_type enum
        VAL->>VAL: Run raw text probes
        VAL->>VAL: Check timestamp format
        alt Valid
            API->>DB: insert_event()
            DB-->>API: OK (or duplicate)
            API-->>WR: 200 {accepted: 1}
        else Invalid
            API-->>WR: 422 {rejected: [...]}
        end
    end

    Agent->>CB: on_tool_end(output, run_id)
    CB->>CB: Compute duration_ms
    CB->>WR: write(event)
    WR->>JSONL: Append JSON line
```

---

## 3. JSONL Replay Flow (Demo Setup)

```mermaid
sequenceDiagram
    participant Client as Dashboard / Test
    participant API as Evidence API
    participant MAN as manifest.json
    participant JSONL as events.jsonl
    participant VAL as validate_event()
    participant DB as SQLite

    Client->>API: POST /demo/reset

    Note over API: For each system in SYSTEM_REGISTRY

    API->>DB: reset_db() -- clear all tables

    loop For each system (restaurant, refund)
        API->>JSONL: Read system's events.jsonl
        API->>MAN: Load manifest session mapping

        loop For each JSONL line
            API->>API: Parse JSON
            API->>MAN: Look up session_ref by line number
            API->>VAL: validate_event(event)
            alt Valid
                API->>DB: insert_event(event, session_ref, line_no)
            else Invalid
                API->>API: Add to rejected list
            end
        end

        API->>API: run_rules_for_system()
        API->>DB: insert_findings()
        API->>API: build_full_assessment()
        API->>DB: insert_assessment()
    end

    API-->>Client: {events_replayed, findings_created, systems, assessments}
```

---

## 4. Rules Engine and Finding Flow

```mermaid
flowchart TD
    A[POST /rules/run] --> B[Load events from SQLite]
    B --> C[Group events by session_ref]

    C --> D{For each session}
    D --> E[Order events by jsonl_line / timestamp]

    E --> F{Rule: R1_confirm_without_proposal}
    F --> G[Scan for place_order tool_start]
    G --> H{confirm_order found?}
    H -->|Yes, no prior place_order| I[Create Finding]
    H -->|No, or place_order exists| J[Skip]

    E --> K{Rule: R_write_no_approval}
    K --> L[Scan for write tools]
    L --> M{approval.required=true?}
    M -->|Yes| N{approval.granted=true?}
    N -->|No| O[Create Finding]
    N -->|Yes| P[Skip]
    M -->|No| P

    I --> Q[Generate deterministic finding_id<br/>SHA256 of rule_id + sorted event_ids]
    O --> Q

    Q --> R[Enrich with control_library]
    R --> S[Look up rule_mappings]
    S --> T[Add failed_control + framework_mappings]

    T --> U[Insert into findings table]
    U --> V[Return findings list]
```

---

## 5. ACAP Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Discovery: discover_tools()

    Discovery --> DraftGeneration: discovery.json +<br/>overrides.yaml +<br/>runtime events
    DraftGeneration --> Draft: acap-draft.yaml<br/>(all tools "unresolved")

    Draft --> HumanReview: GET /systems/{id}/acap/draft<br/>Review in dashboard

    HumanReview --> ReviewDecisions: POST /systems/{id}/acap/review<br/>Tool authorizations

    ReviewDecisions --> ReviewedACAP: acap-reviewed.yaml<br/>(tools allowed/prohibited/<br/>conditional/with_approval)

    ReviewedACAP --> RiskProfile: build_risk_profile()
    ReviewedACAP --> FrameworkApplicability: evaluate_framework_applicability()
    ReviewedACAP --> RuleEvaluation: Rules reference ACAP policies

    RiskProfile --> Assessment: build_full_assessment()
    FrameworkApplicability --> Assessment
    RuleEvaluation --> Assessment

    Assessment --> [*]

    note right of Draft
        7 review questions generated:
        Q1: purpose
        Q2: owner
        Q3: allowed actions
        Q4: prohibited actions
        Q5: approval requirements
        Q6: sensitive data
        Q7: reassessment triggers
    end note
```

---

## 6. Assessment Build Flow

```mermaid
flowchart LR
    subgraph Inputs
        ACAP[Reviewed ACAP]
        EVT[Events from SQLite]
        FIND[Findings]
        CTRL[Control Library]
    end

    subgraph "risk.py"
        RP[build_risk_profile]
        FA[evaluate_framework_applicability]
        COV[compute_field_coverage]
        BA[build_full_assessment]
    end

    subgraph Output
        ASS["Assessment Snapshot<br/>assessment_id: A-{hash}<br/>overall_status<br/>evidence_confidence<br/>framework_status<br/>recommended_actions"]
    end

    ACAP --> RP
    RP -->|authority_level<br/>autonomy_level<br/>data_sensitivity| FA
    ACAP --> FA
    EVT --> COV

    RP --> BA
    FA --> BA
    COV --> BA
    FIND --> BA

    BA --> ASS
    ASS -->|insert_assessment| DB[(SQLite)]
```

---

## 7. Frontend / Backend API Flow

```mermaid
sequenceDiagram
    participant User as User
    participant UI as Dashboard (app.js)
    participant API as Evidence API

    User->>UI: Open /ui/

    Note over UI: loadEvidenceView()

    par Parallel fetches
        UI->>API: GET /systems
        UI->>API: GET /health
        UI->>API: GET /findings?system_id=restaurant-agent
        UI->>API: GET /evidence/events?limit=1000
    end

    API-->>UI: systems list
    API-->>UI: health status
    API-->>UI: findings list
    API-->>UI: events list

    Note over UI: For selected system

    par System-specific fetches
        UI->>API: GET /systems/restaurant-agent/acap
        UI->>API: GET /systems/restaurant-agent/acap/draft
        UI->>API: GET /systems/restaurant-agent/coverage
        UI->>API: GET /systems/restaurant-agent/risk-profile
        UI->>API: GET /systems/restaurant-agent/framework-applicability
        UI->>API: GET /systems/restaurant-agent/assessments
    end

    API-->>UI: ACAP summary
    API-->>UI: draft ACAP
    API-->>UI: coverage fields
    API-->>UI: risk profile
    API-->>UI: applicability
    API-->>UI: assessments list

    UI->>API: GET /assessments/{latest_id}
    API-->>UI: latest assessment detail

    Note over UI: render() - build DOM

    UI->>UI: renderKpiStrip() - 6 KPI cards
    UI->>UI: renderSystem() - profile + ACAP
    UI->>UI: renderLatestAssessment()
    UI->>UI: renderAcapReview() - tool table
    UI->>UI: renderRiskProfile()
    UI->>UI: renderApplicability()
    UI->>UI: renderCoverage()
    UI->>UI: renderFindingsList()

    User->>UI: Click finding
    UI->>UI: renderDetails() + renderTimeline()

    User->>UI: Click "Run Assessment"
    UI->>API: POST /systems/restaurant-agent/assessments/run
    API-->>UI: new assessment
    UI->>UI: Reload all data

    User->>UI: Switch to "customer-refund-agent"
    Note over UI: Reload all system-specific data
```

---

## 8. Data Storage Map

```mermaid
graph LR
    subgraph "Local Files (gitignored)"
        JSONL["artifacts/governance/<br/>events.jsonl"]
        DISC["artifacts/governance/<br/>discovery.json"]
        COV["artifacts/governance/<br/>coverage.json"]
        DRAFT["artifacts/governance/<br/>acap-draft.yaml"]
        REVIEWED["artifacts/governance/<br/>acap-reviewed.yaml"]
        FINDINGS["artifacts/governance/<br/>findings.json"]
        OTLP_F["artifacts/governance/otel/<br/>otlp-traces.json"]
    end

    subgraph "Committed Files"
        CTRL["control-library/<br/>canonical-controls.yaml"]
        SCHEMA["schemas/<br/>governance-event.schema.json"]
        OVERRIDES["governance-tool-<br/>overrides.yaml"]
        REFUND_E["examples/refund-agent/<br/>events.jsonl"]
        REFUND_A["examples/refund-agent/<br/>acap-reviewed.yaml"]
    end

    subgraph "Runtime (SQLite)"
        DB_E["events table"]
        DB_F["findings table"]
        DB_A["assessments table"]
        DB_R["acap_reviews table"]
    end

    JSONL -->|replay| DB_E
    REFUND_E -->|replay| DB_E
    DB_E -->|rules| DB_F
    DB_E -->|coverage + risk| DB_A
    REVIEWED -->|risk profile| DB_A
    REFUND_A -->|risk profile| DB_A
    CTRL -->|enrich findings| DB_F
```

---

## 9. Privacy & Sanitization Pipeline

```mermaid
flowchart TD
    RAW[Raw LangChain Event] --> CB[GovernanceCallback]

    CB --> HASH[Hash prompts/responses<br/>SHA256 fingerprint]
    CB --> SHAPE[Extract message shape<br/>roles + count only]
    CB --> STRIP[Strip raw content<br/>Never stored]

    CB --> TOOL_ARGS[Tool Arguments]
    TOOL_ARGS --> SAN[sanitize]

    SAN --> EMAIL["Emails -> &lt;redacted-email&gt;"]
    SAN --> PHONE["Phones -> &lt;redacted-phone&gt;"]
    SAN --> CARDS["12-19 digits -> &lt;redacted-number&gt;"]
    SAN --> KEYS["Sensitive keys -> &lt;redacted&gt;<br/>(api_key, password, token,<br/>authorization, cvv, card_number)"]
    SAN --> TRUNC["Strings > 512 chars -> truncated"]
    SAN --> DEPTH["Depth > 6 -> &lt;max-depth&gt;"]

    EMAIL --> SAFE[Sanitized Event]
    PHONE --> SAFE
    CARDS --> SAFE
    KEYS --> SAFE
    TRUNC --> SAFE
    DEPTH --> SAFE
    HASH --> SAFE
    SHAPE --> SAFE

    SAFE --> JSONL[events.jsonl]
    SAFE --> API_VAL[API validate_event]
    API_VAL --> PROBE[Raw text probes]
    PROBE -->|"system prompt text<br/>order text<br/>adversarial text"| REJECT[Rejected]
    PROBE -->|clean| STORE[SQLite]

    STORE --> PUB[public_event]
    PUB --> STRIP2["Remove sanitized_arguments<br/>Remove result_summary"]
    STRIP2 --> RESP[API Response]
```
