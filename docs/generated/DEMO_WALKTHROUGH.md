# Demo Walkthrough

How to present the AI Governance Command Center prototype in a meeting. This guide covers starting the system, navigating the dashboard, explaining each section, and demonstrating multi-system support.

---

## Prerequisites

1. Python environment with dependencies installed (see `INSTALL.md`)
2. `.env` file with OpenRouter API key (only needed if running live agent -- not required for dashboard demo)
3. Terminal access

---

## Step 1: Start the Evidence API

```bash
cd services/evidence_api
python -m uvicorn app:app --reload --port 8000
```

The API starts at `http://127.0.0.1:8000`. Verify with:
```bash
curl http://127.0.0.1:8000/health
# {"ok": true, "events": 0, "database": "sqlite"}
```

---

## Step 2: Load Demo Data

The demo ships with pre-recorded evidence from 6 restaurant agent scenarios and 2 refund agent scenarios. Load them:

```bash
curl -X POST http://127.0.0.1:8000/demo/reset
```

This replays all JSONL evidence files, runs deterministic rules, and creates assessments for both systems. Response shows:
- ~264 events replayed
- 2 findings created (1 per system)
- 2 assessments generated

---

## Step 3: Open the Dashboard

Open in browser: **http://127.0.0.1:8000/ui/**

The dashboard loads automatically with the restaurant-agent selected.

---

## Step 4: Explain the KPI Strip

The top row shows 6 key indicators:

| Card | What to Say |
|------|-------------|
| **Governance Status** | "This system currently **requires remediation** -- we found a high-severity governance violation." |
| **Risk Level** | "The risk level is **delegated** -- the agent can take actions but all write operations require human approval." |
| **Evidence Events** | "We captured **242 events** from 6 controlled test scenarios without any code changes to the agent itself." |
| **Open Findings** | "There is **1 open finding** -- a confirm_order was executed without the required prior proposal step." |
| **Failed Controls** | "**1 control failed** -- AGT-AUTH-001, which requires human approval before write actions." |
| **Evidence Confidence** | "Confidence is **medium** -- most fields are captured, but retrieval source IDs and some annotations are still missing." |

---

## Step 5: System Profile & ACAP

Scroll to the Overview section. Two panels:

### Left: System Profile
- **System ID:** restaurant-agent
- **Deployment:** local-test
- **Environment:** local
- **Owner:** restaurant-agent developer
- **Purpose:** Restaurant ordering assistant

**What to say:** "This identifies which AI system we're governing. In production, each deployed agent gets its own system ID and ACAP."

### Right: ACAP Summary
- **ACAP ID:** restaurant-agent-local-reviewed
- **Status:** Reviewed
- **Reviewed by:** Shrey / restaurant-agent developer
- **Approval tools:** confirm_order (the only tool that requires human approval)
- **Prohibited count:** 0 explicitly prohibited tools

**What to say:** "The ACAP -- AI Capability and Authorization Policy -- defines what this agent is allowed and not allowed to do. It was auto-generated from tool discovery, then reviewed by a human who confirmed authorization boundaries."

---

## Step 6: Run an Assessment

Click the green **"Run Assessment"** button in the header.

The system will:
1. Compute evidence coverage from all stored events
2. Run deterministic rules to generate findings
3. Build a risk profile from the reviewed ACAP
4. Evaluate framework applicability
5. Combine into an assessment snapshot with an overall status

**What to say:** "This is a one-click governance assessment. It evaluates the agent against its ACAP, checks for policy violations, measures evidence coverage, and determines which compliance frameworks apply."

---

## Step 7: Explain the Finding

Scroll to the Findings section. Click on the finding (F-06236c96da2c).

The detail panel shows:

### The Violation
**What to say:** "In test scenario s5 (adversarial prompt injection), the agent was tricked into calling `confirm_order` without ever calling `place_order` first. This violates ACAP policy P1: the agent must propose an order before confirming it."

### The Control
**What to say:** "This maps to control AGT-AUTH-001: 'Agent must obtain human approval before executing write actions.' The model-supplied approval argument is not trusted evidence of human consent."

### Framework Mappings
**What to say:** "This control traces to four compliance frameworks:
- **ACAP P1** -- our own AI authorization policy
- **NIST AI RMF GOVERN 1.1** -- legal and regulatory requirements for human oversight
- **EU AI Act Article 14** -- human oversight for high-risk AI systems (potential relevance, not a legal claim)
- **ISO 42001 Clause 6.1.3** -- AI risk assessment controls

These are informational references -- a compliance officer would determine actual applicability."

### Event Timeline
**What to say:** "Every finding is linked to the exact runtime events that triggered it. You can see the trace: which model was called, which tools fired, what the outcome was, and when the violation occurred. This is audit-grade traceability."

---

## Step 8: Explain Framework Mapping

Scroll to the Risk & Frameworks section.

### Risk Profile
**What to say:** "The risk profile is computed automatically from the ACAP:
- **Authority level: delegated** -- the agent can act but writes need approval
- **Autonomy level: human-in-the-loop** -- approval is structurally required
- **Data sensitivity: medium** -- contact data is processed
- **External side effects: yes** -- the agent writes to an orders log"

### Framework Applicability
**What to say:** "Based on the risk profile, we automatically determine which frameworks apply:
- **ACAP:** Yes -- 6 tools need authorization boundaries
- **OWASP Agentic:** Yes -- prompt injection, tool misuse risks
- **NIST AI RMF:** Yes -- always applicable
- **EU AI Act:** Not currently -- no EU jurisdiction configured
- **ISO 42001:** Informational -- AI management system standard"

---

## Step 9: Show Evidence Coverage

Scroll to the Runtime Evidence section.

**What to say:** "This table shows exactly which governance fields we're capturing and which are still gaps:
- **Green (captured):** Schema version, event IDs, timestamps, trace hierarchy, tool names, outcomes -- all automated
- **Orange (annotation required):** Data classification and prompt template IDs need human annotation
- **Red (missing):** Retrieval source identifiers -- FAISS is called internally by LangChain and doesn't expose document sources through the callback
- **Yellow (partial):** Token usage -- depends on the model provider returning it"

---

## Step 10: Switch to the Refund Agent

Use the system selector dropdown in the header. Switch from "restaurant-agent" to **"customer-refund-agent"**.

The entire dashboard reloads with the refund agent's data:

**What to say:** "This is the same governance platform evaluating a completely different AI system -- a customer refund agent. Notice:
- Different finding: **R_write_no_approval** -- a refund was processed without the required approval
- Different tools: lookup_order, check_eligibility, refund_execute, send_notification
- Different risk profile: this agent has **financial** data sensitivity (payment data)
- Same framework mappings, same control library, same assessment workflow

This demonstrates that the governance layer is **system-agnostic**. You define the ACAP for each agent, and the platform evaluates them all consistently."

---

## Step 11: Export the Report

Click **"Export Report"** in the header.

A Markdown governance assessment report opens in a new tab. It contains:
- Executive summary with finding counts
- System profile and risk classification
- ACAP summary
- Evidence coverage table
- Full finding details with framework mappings and event timelines
- Framework applicability and status
- Recommended next actions
- Limitations disclaimer

**What to say:** "This is a shareable governance report that could go to a compliance officer, auditor, or risk committee. Everything is traceable back to specific runtime events."

---

## Key Talking Points

### What makes this different?

1. **No source code required** -- We instrument via LangChain callbacks, not code analysis. The agent's code is untouched.

2. **Privacy by default** -- Raw prompts and responses are never captured. We store hashes and sanitized summaries. Emails, phones, and card numbers are automatically redacted.

3. **Deterministic findings** -- No ML or LLM in the rules engine. Same events always produce the same findings. Every finding ID is a SHA256 hash of the rule + events.

4. **Fail-open design** -- If the governance layer crashes, the agent continues working normally. Evidence is best-effort, never blocking.

5. **Observed != Authorized** -- We discover what tools exist, but we never assume they're allowed. A human must review and confirm the ACAP.

6. **Framework-agnostic** -- Controls map to ACAP, NIST, EU AI Act, and ISO 42001. Adding a new framework means adding mappings, not rebuilding.

### What's the catch?

- This is a **prototype** -- no authentication, no multi-user, no production deployment
- The refund agent is **synthetic** (generated events, not a real agent)
- EU AI Act applicability is **informational only** -- requires legal review
- Token usage capture is **provider-dependent** -- some models don't return it
- FAISS retrieval sources are **not visible** through LangChain callbacks

---

## Quick Reference Commands

| Action | Command |
|--------|---------|
| Start API | `cd services/evidence_api && python -m uvicorn app:app --reload --port 8000` |
| Load demo data | `curl -X POST http://127.0.0.1:8000/demo/reset` |
| Open dashboard | Browser: `http://127.0.0.1:8000/ui/` |
| Run restaurant agent | `python Restaurant_agent1.py` (needs .env with API key) |
| Generate refund evidence | `python examples/refund-agent/generate_evidence.py` |
| Run tests | `python -m pytest tests/ -v` |
| Export OTLP traces | `python -m governance_probe.otel_export --no-send` |
