# First objective: prove evidence extraction from the restaurant agent

## Question we are answering

Can an existing LangChain restaurant agent produce enough structured runtime evidence to support the future governance workflow without requiring source-code upload, a long developer questionnaire or a full platform rebuild?

## Scope

The experiment covers the current codebase only. It inspects and instruments real model, chain/agent, tool, retrieval and error paths, then creates local governance artifacts.

## Out of scope

- Full AI-system registration UI
- Production database or dashboard
- Full EU/NIST/ISO compliance audit
- Legal classification or certification
- Inline tool blocking
- Real customer data
- Real payment, reservation or order side effects
- Production prompt injection
- Broad codebase refactoring

## Required outputs

1. Repository inventory
2. Instrumentation plan
3. Discovered tool catalog
4. Prompt/model fingerprints
5. Canonical JSONL evidence
6. Evidence-coverage report
7. Draft ACAP
8. At least one evidence-linked deterministic finding
9. GO/NO-GO report

## Minimum evidence success criteria

| Area | Required result |
|---|---|
| Traceability | A complete root run with parent/child model, tool and chain/agent relationships |
| Model | Provider/name where exposed, timing, outcome and token usage where available |
| Prompt | Template or message fingerprint and structure; raw text disabled by default |
| Tools | Tool name, sanitized input summary, result/error, timing and trace linkage |
| Actions | At least one tool classified as read and one as write/external if the app has them |
| Identity | Stable logical agent name and pseudonymous session/user reference where available |
| Approval | Captured when implemented; otherwise explicitly marked unavailable |
| Data | Tool-level data classification through discovery or minimal override |
| Coverage | Field-by-field captured/missing/annotation-required report |
| Finding | Deterministic finding linked to exact event IDs and policy/control version |
| Privacy | No credentials, raw production data or unapproved prompt/output content |
| Behavior | Existing tests pass and user-visible agent behavior remains unchanged |

## GO criteria

Issue **GO** when the integration reliably captures the full model-to-tool execution path, identifies consequential actions, preserves privacy defaults and produces an evidence-linked finding.

Issue **CONDITIONAL GO** when the core path works but one or more important fields require lightweight application annotations, such as approval status or data classification.

Issue **NO-GO** when tool actions cannot be attributed to a trace/agent, evidence is materially incomplete, instrumentation changes behavior, or sensitive content cannot be controlled.

## Likely conclusion

LangChain callbacks or compatible OpenTelemetry instrumentation should expose much of the technical execution path. Business meaning—such as whether `create_reservation` is allowed, what customer data it may use, or whether cancellation requires approval—will still require a small policy annotation or human confirmation. That is expected and is not a failure of the experiment.
