# OTLP Export Mapping

Generated for Milestone 5 from `artifacts/governance/events.jsonl`.

## Scope

- Source of truth: local JSONL only.
- Transport target: local OpenTelemetry Collector OTLP/HTTP endpoint `http://127.0.0.1:4318/v1/traces`.
- Excluded by design: dashboard, FastAPI, database, OPA, LangSmith and framework-specific mapping.

## Mapping

- Governance events are grouped by `(trace_id, span_id)` into OTel spans.
- Every JSONL event is represented as an OTel span event named `governance.<event_type>`.
- OTel wire IDs are deterministic valid hex IDs derived from governance IDs.
- Original `trace_id`, `span_id` and `parent_span_id` are preserved as `governance.*` attributes because governance span IDs are UUID-shaped while OTel span IDs are 8-byte values.
- Preserved attributes include session, event, component, tool name, action type, approval metadata, status, error type/message, token usage, prompt hash/capture metadata and data/privacy classification fields.

## Privacy

The exporter uses a whitelist. It does not export raw prompt, response, stdin or adversarial input text.

Privacy-filtered fields:

- `tool.sanitized_arguments`: replaced by `tool.arguments_hash` plus `governance.tool.sanitized_arguments_exported=false`.
- `attributes.result_summary`: replaced by result/response/output hashes plus `governance.attributes.result_summary_exported=false`.

Latest generated verification:

- Source events: 376
- OTel spans: 188
- OTel span events: 376
- Mapped events: 376
- Not applicable events: 0
- Raw text export hits: none

Machine-readable artifacts:

- `artifacts/governance/otel/otlp-traces.json`
- `artifacts/governance/otel/mapping-report.json`

Collector send status: success. The one-span connectivity probe and full 376-event OTLP JSON export both received HTTP 200 from `http://127.0.0.1:4318/v1/traces`.
