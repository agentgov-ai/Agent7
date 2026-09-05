---
name: generate-acap-draft
description: Generate a minimal draft ACAP from discovered tools and observed evidence, while keeping authorization decisions human-owned.
disable-model-invocation: true
---
Generate `artifacts/governance/acap-draft.yaml` from the repository inventory, tool discovery and local evidence.

The draft should auto-fill:

- system/deployment identifiers;
- detected logical agent and framework;
- model and prompt fingerprints;
- discovered tools and argument schemas;
- observed tool usage;
- proposed action type: read, write, communicate, execute or unknown;
- proposed data classes, side effects and reversibility where inferable;
- evidence fields available for each tool.

Do not infer authorization merely because a tool exists or was used.

Create no more than seven human-review questions, focusing on:

1. intended purpose;
2. accountable owner;
3. which proposed actions should be allowed;
4. which actions must be prohibited;
5. which actions require confirmation or approval;
6. sensitive data allowed/prohibited;
7. reassessment triggers.

Mark uncertain fields as `unresolved`. Include provenance for every auto-filled value. Validate the draft against `templates/restaurant-acap.example.yaml` as a shape reference, not as the customer's final policy.
