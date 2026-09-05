# Stable Demo Data

This directory contains frozen JSONL evidence and reviewed ACAP fixtures for
the local Evidence API demo reset flow.

`POST /demo/reset` replays these files directly instead of using the mutable
runtime artifact at `artifacts/governance/events.jsonl`. The restaurant seed is
the current 394-event PoC artifact frozen at the time this demo data was added.

Included systems:

- `restaurant-agent`
- `customer-refund-agent`
- `custom-python-refund-agent`
- `openai-direct-agent`
- `anthropic-direct-agent`
- `support-api`

The JSONL files keep the existing governance-event schema. Prompt and response
content are represented by hashes only; API keys and emails are not present.
