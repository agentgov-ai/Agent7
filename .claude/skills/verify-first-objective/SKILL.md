---
name: verify-first-objective
description: Verify that the restaurant-agent codebase can produce sufficient governance evidence without changing behavior or exposing sensitive content.
disable-model-invocation: true
---
Verify the first objective without adding new product features.

1. Discover and run the repository's existing lint, type-check and test commands.
2. Run focused instrumentation tests.
3. Run the controlled restaurant scenarios if safe fixtures exist.
4. Validate all events against `schemas/governance-event.schema.json`.
5. Verify trace parentage, timestamps, event IDs and no duplicate terminal events.
6. Confirm raw prompt/response content is absent by default.
7. Confirm likely secrets and personal fields are redacted from tool arguments/results.
8. Confirm discovery contains actual tools and prompt fingerprints.
9. Confirm ACAP draft separates discovered/observed facts from authorization decisions.
10. Confirm one deterministic rule produces an evidence-linked finding, such as:
    - unapproved/unknown tool;
    - write/external action outside the draft policy;
    - required approval missing;
    - unknown agent identity;
    - incomplete evidence.
11. Compare baseline and instrumented behavior and report latency/overhead where measurable.
12. Ask the instrumentation-reviewer, privacy-reviewer and governance-reviewer to inspect the relevant diff.

Write `artifacts/governance/GO_NO_GO.md` with:

- GO, CONDITIONAL GO or NO-GO;
- fields captured reliably;
- fields needing lightweight annotation;
- fields unavailable from this integration;
- privacy/performance concerns;
- exact next step, normally OTLP export or a minimal ingestion API.

Do not weaken tests or enable raw content merely to obtain a GO result.
