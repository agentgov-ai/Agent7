# Instrumentation decision tree

## Step 1 — Is tracing already enabled?

### Existing LangSmith

- Keep it running.
- Inspect whether the application already passes tags, metadata, run names and trace IDs.
- Add governance metadata and a local evidence adapter rather than replacing LangSmith.
- Store LangSmith identifiers as references only; the local governance record remains independently testable.

### Existing OpenTelemetry/OpenInference

- Reuse the tracer provider and OTLP pipeline.
- Add governance attributes through callbacks, span attributes or a processor.
- Avoid creating a second root span for the same request.
- Verify content-capture defaults before running test data.

### Existing custom callbacks/logging

- Extend or adapt them if they already cover the real execution path.
- Normalize their output instead of emitting a parallel duplicate stream.

## Step 2 — If there is no tracing

Start with a local LangChain callback handler:

```text
root invocation config
  → chain/agent callbacks
  → model callbacks
  → tool/retriever callbacks
  → privacy-safe JSONL writer
```

This is the fastest way to prove extractability. After the schema is stable, add OpenInference/OpenTelemetry as the transport.

## Step 3 — Tool enrichment

Auto-discover name, description and argument schema. Add only a small override file for facts that code cannot prove:

```yaml
tools:
  create_reservation:
    action_type: write
    external_side_effect: true
    data_classes: [contact, reservation]
    approval_required: false
```

Do not make developers re-enter every tool.

## Step 4 — Approval events

A generic trace cannot prove human approval unless the application emits an explicit event. If the restaurant agent has confirmation or approval logic, instrument that exact point. Otherwise report approval evidence as unavailable and add it later.

## Step 5 — Standardize with OTLP

Only after local JSONL is verified:

```text
LangChain/OpenInference instrumentation
        ↓ OTLP
Customer/local OTel Collector
        ↓ process/redact/enrich
Future governance ingestion endpoint
```

The collector should be vendor-neutral and customer-controlled in later deployments.
