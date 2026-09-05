# Five-day evidence-extraction plan

This is a focused prototype sequence. A small codebase may complete it faster; a complex or poorly tested codebase may take longer.

## Milestone 0 — Inventory and baseline (Half day)

- Run the restaurant agent without changes.
- Record local run/test commands and one baseline scenario.
- Inspect LangChain/LangGraph versions, invocation path, tools, prompts, models and existing tracing.
- Produce the repository inventory and instrumentation plan.

**Exit:** We know exactly where instrumentation attaches and which real side effects must be mocked.

## Milestone 1 — Local runtime capture (Day 1)

- Add a removable callback/adapter.
- Emit local JSONL for chain/agent, LLM, tool, retriever and error events.
- Preserve run hierarchy.
- Hash prompts and sanitize tool data.
- Add focused tests.

**Exit:** One normal restaurant-agent request produces a connected trace without changing the response.

## Milestone 2 — Governance enrichment (Day 2)

- Add stable system, deployment, environment and logical agent metadata.
- Auto-discover tools, descriptions and argument schemas.
- Add minimal tool override annotations for action type, data class, side effect and approval.
- Capture or explicitly mark approval events.

**Exit:** The trace distinguishes read-only activity from a write/external action.

## Milestone 3 — Scenario and coverage validation (Day 3)

- Run read, write, error and consequential scenarios using fake data and mocks.
- Measure field coverage, event duplication and basic overhead.
- Produce `coverage.json` and a run summary.

**Exit:** We can state exactly which evidence is automatic, which needs annotation and which is unavailable.

## Milestone 4 — Auto-ACAP and first finding (Day 4)

- Generate the draft ACAP from discovery.
- Confirm only the key human boundaries.
- Add a few deterministic checks.
- Produce one finding linked to exact evidence.

**Exit:** A controlled policy violation or missing-control case appears in `findings.json` with event IDs and remediation.

## Milestone 5 — Standard transport (Optional Day 5)

- Add OpenInference/OpenTelemetry only after local capture is stable.
- Route spans to a local OpenTelemetry Collector.
- Correlate OTel trace IDs with governance events.
- Confirm no duplicate or raw-content leakage.

**Exit:** The same evidence can leave the app through a vendor-neutral OTLP path, ready for a future ingestion service.

## Next milestone after GO

Build the smallest governance ingestion API that accepts the normalized schema, stores evidence and renders a basic finding view. Do not jump directly to all frameworks or an enterprise dashboard.
