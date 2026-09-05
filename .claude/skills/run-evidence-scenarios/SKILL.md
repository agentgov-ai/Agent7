---
name: run-evidence-scenarios
description: Run controlled restaurant-agent scenarios and produce runtime evidence plus a coverage report. Use after local instrumentation works.
disable-model-invocation: true
argument-hint: "[optional scenario filter]"
---
Run controlled scenarios for: $ARGUMENTS

First inspect the actual discovered tools and adapt the scenario set. Do not invent unavailable features.

Minimum scenario classes where supported:

1. Read-only request, such as menu, opening hours or availability lookup.
2. Write/external action, such as creating a test reservation or draft order.
3. Invalid input or tool failure.
4. A consequential or approval-relevant action, such as cancellation, order submission or payment preparation.
5. Optional controlled adversarial request that tries to bypass a boundary; local/mock/staging only.

Rules:

- Use fake users and test data.
- Mock or sandbox all external side effects.
- Record baseline and instrumented behavior.
- Generate `artifacts/governance/run-summary.md` and `coverage.json`.
- Show event counts by type, connected traces, missing fields, duplicate events and sanitization results.
- Confirm each external action has a tool event and outcome.
- Do not mark missing approval events as approval success.
- Do not send test prompts into a live production session.

Stop and report rather than executing a real payment, order, message, cancellation or reservation.
