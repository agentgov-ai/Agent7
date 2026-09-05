# Restaurant Agent Governance Evidence Prototype

## Mission

Use the existing LangChain restaurant-agent codebase to prove that we can extract trustworthy, privacy-conscious runtime evidence for the future AI Governance Command Center.

The first objective is complete when the repository can run controlled restaurant-agent scenarios and produce a normalized evidence stream, an evidence-coverage report, an automatically discovered tool catalog, a draft ACAP, and at least one deterministic evidence-linked finding.

## Current priority

Instrument the application that already exists. Do not begin the full platform architecture until this experiment has a clear GO/NO-GO result.

## Golden path

1. Inspect the current repository and run the agent unchanged.
2. Identify its LangChain/LangGraph version, entry point, agent construction, prompts, tools, model providers, retrievers, callbacks and existing tracing.
3. Add the smallest removable instrumentation layer.
4. Capture model, chain/agent, tool, retrieval, error and timing events to local JSONL.
5. Keep raw prompt, output, tool-argument and tool-result content disabled by default; store metadata, hashes and sanitized summaries.
6. Run representative restaurant scenarios using test data.
7. Generate an evidence-coverage matrix showing captured, missing and annotation-required fields.
8. Discover tools and prompt fingerprints automatically.
9. Generate a draft ACAP and ask a human to confirm only business boundaries.
10. Produce a deterministic finding from a controlled violation or missing-control scenario.
11. Add OTLP/OpenTelemetry export only after local capture works.

## Do not build yet

Do not add a new frontend, dashboard, FastAPI governance backend, PostgreSQL, Redis, Kafka, Qdrant, OPA, Kubernetes, framework scrapers or full LangGraph compliance engine during this objective.

Do not rewrite the restaurant agent, replace LangChain, change its prompt behavior, or introduce a new agent framework merely to make tracing easier.

## Evidence model

Separate three classes of information:

- Automatically observable: run hierarchy, model calls, component names, tool names, tool inputs/results in sanitized form, errors, timings, token usage where available.
- Lightweight technical annotation: system/deployment ID, tool action type, data class, side-effect, reversibility, approval requirement and agent identity.
- Human decision: business purpose, owner, allowed/prohibited actions, approval thresholds, acceptable data use and risk acceptance.

Never treat observed behavior as authorization. The draft ACAP may use discovery to propose a catalog, but a person must approve the allowed operating boundary.

## Privacy and safety rules

- Never read, print, commit or transmit `.env`, secrets, API keys or credentials.
- Never use real customer data for the experiment.
- Raw prompts and responses are OFF by default.
- Hash prompt templates and summarize message shape instead of storing content.
- Sanitize tool arguments and results; redact likely passwords, tokens, authorization headers, card data and personal contact details.
- Store local evidence under `artifacts/governance/`, which must be gitignored.
- Prompt-injection tests are allowed only in local, mocked, sandbox or explicitly approved staging environments.
- Do not cause real orders, reservations, cancellations, messages or payments.

## Instrumentation strategy

Choose the smallest compatible route after inspecting the repository:

1. Reuse existing callbacks/tracing if present.
2. Add a project callback handler for governance enrichment and local JSONL.
3. If OpenInference/OpenTelemetry is already present, enrich rather than duplicate its spans.
4. If LangSmith tracing is enabled, preserve it and correlate its run/trace IDs; do not make LangSmith the governance source of truth.
5. Avoid duplicate events when multiple tracing systems are active.

Prefer instrumentation through the invocation `config`/callbacks path and tool wrappers over invasive edits inside business functions.

## Required evidence fields

At minimum, attempt to capture:

- schema version, event ID and UTC timestamp;
- system ID, deployment ID and environment;
- trace/run ID, span/run ID and parent relationship;
- event type and component kind/name;
- model provider/name where available;
- prompt template ID/hash or message-shape metadata;
- tool name, action classification, sanitized argument summary and outcome;
- retrieval source identifiers where available;
- agent identity or stable logical name;
- approval required/granted when the application has approval logic;
- data classification annotations where known;
- status, error type, duration and token usage where available.

Missing fields must be reported as missing or annotation-required, never fabricated.

## Engineering rules

- Establish a behavioral baseline before instrumentation.
- Keep instrumentation removable and feature-flagged where practical.
- Preserve current public APIs and test behavior.
- Add focused tests for event generation, redaction, run hierarchy and failure paths.
- Prefer one local JSONL sink first. Do not add infrastructure before the event model is validated.
- Use stable schemas and explicit versions.
- Keep raw evidence immutable during one test run; derived reports may be regenerated.
- Record the installed package versions used by the experiment.
- Do not silently upgrade LangChain or other major dependencies.
- Ask before adding a major dependency or changing package versions.

## Working method

1. Read this file and the relevant docs before editing.
2. Inspect first; do not assume Python versus TypeScript, LangChain version, or agent style.
3. Produce a small plan with insertion points, risks and acceptance criteria.
4. Implement one instrumentation slice at a time.
5. Run baseline and instrumented tests.
6. Review privacy, duplicate-event and semantic risks.
7. Report exact files changed, commands run, evidence captured, fields missing and next step.

## Definition of done for this objective

The objective is not complete merely because traces appear. It is complete when:

- one full agent run has a connected parent/child trace;
- model and tool activity can be attributed to a deployment and logical agent;
- a write/external-action tool can be identified and classified;
- prompts are fingerprinted without raw content by default;
- errors and tool outcomes are visible;
- evidence coverage is measured;
- a draft ACAP is generated from discovery plus minimal human confirmation;
- one deterministic rule produces a finding linked to exact event IDs;
- the agent's functional behavior remains unchanged;
- a GO/NO-GO recommendation is written.
