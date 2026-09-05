---
name: instrument-langchain-evidence
description: Add the smallest approved LangChain runtime instrumentation path and emit privacy-safe governance events. Use after repository inspection.
disable-model-invocation: true
argument-hint: "[local-jsonl|otel]"
---
Implement the approved instrumentation mode: $ARGUMENTS

Requirements:

- Re-read CLAUDE.md and `docs/generated/INSTRUMENTATION_PLAN.md`.
- Establish or preserve a baseline test before changing the invocation path.
- Reuse existing tracing where appropriate; avoid duplicate spans.
- For `local-jsonl`, prefer a removable callback/adapter that writes normalized events under `artifacts/governance/events.jsonl`.
- For `otel`, add OTLP export only after local JSONL extraction has passed verification.
- Attach stable system/deployment/environment metadata at the root invocation.
- Preserve run ID, parent run ID and trace correlation.
- Capture chain/agent, LLM/chat model, tool, retriever, agent action/finish and error events supported by the installed version.
- Keep prompt/output content off by default; record template/message fingerprints and shape metadata.
- Sanitize tool arguments and results before persistence.
- Enrich tools through an automatically generated catalog plus a small override file; do not ask developers to manually retype the tool list.
- Make evidence-writer failure non-fatal to the restaurant-agent request unless the repository explicitly chooses fail-closed behavior for tests.
- Add tests for a normal model/tool run, a tool error, redaction and parent/child correlation.
- Document how to disable instrumentation.

At completion report files changed, commands run, event types captured, fields still missing, overhead observed and any required human annotations.
