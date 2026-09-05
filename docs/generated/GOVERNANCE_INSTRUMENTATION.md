# Governance instrumentation — usage and removal (generated 2026-07-17)

The restaurant agent carries a **removable, feature-flagged** evidence layer
(`governance_probe/`). It is passive: a LangChain callback handler attached
through the invocation `config` at `Restaurant_agent1.py` `main()`. It never
modifies prompts, tools or model behavior.

## Enable

```bash
GOVERNANCE_EVIDENCE=1 python Restaurant_agent1.py      # bash
set GOVERNANCE_EVIDENCE=1 && python Restaurant_agent1.py   # cmd
$env:GOVERNANCE_EVIDENCE="1"; python Restaurant_agent1.py  # PowerShell
```

## Disable

Unset the variable (or set anything other than `1`). When the flag is off:
- `GOVERNANCE` stays `None`, the `governance_probe` package is **never imported**,
- the invoke `config` is byte-identical to the uninstrumented app,
- zero instrumentation objects are created (verified by import check).

## Remove entirely

1. Delete the `GOVERNANCE` block in `Restaurant_agent1.py` (the `if os.environ.get("GOVERNANCE_EVIDENCE")…` stanza) and the two `merge_invoke_config` lines in `main()`.
2. Delete `governance_probe/`, `governance-tool-overrides.yaml`, `tests/test_governance_probe.py`, `artifacts/governance/`.

## What is written (all under gitignored `artifacts/governance/`)

| File | Content |
|---|---|
| `events.jsonl` | Append-only evidence events, schema v0.1 (`schemas/governance-event.schema.json`) |
| `discovery.json` | Auto-discovered tool catalog (from the same `TOOLS` list passed to `create_agent` — never retyped), system-prompt SHA-256 fingerprint, model annotation, package versions |
| `baseline/` | Baseline transcripts + `orders_log.json` backup |

## Event types captured

`chain_start/end/error`, `llm_start/end/error` (chat-model runs incl. message
shape, roles, token usage), `tool_start/end/error` (sanitized args/results,
action classification, approval enrichment), `retriever_*` (implemented but
will not fire — FAISS is called inside tools, not as a retriever; known gap),
`agent_action`/`agent_finish` (legacy AgentExecutor hooks; not emitted by
LangGraph `create_agent`).

## Privacy defaults

- Raw prompts/responses: **never** persisted — SHA-256 hashes + message shape only.
- Tool arguments/results: sanitized (`sanitize()`): emails, phones, 12–19-digit
  numbers redacted; `api_key`/`token`/`password`/card-like dict keys redacted;
  strings truncated at 512 chars.
- Tools whose catalog entry declares a sensitive data class (currently
  `contact`, e.g. `get_user_name`) persist results **hash-only** — the
  `result_summary` is replaced by `<redacted-data-class:contact>` because
  free-text personal names cannot be reliably pattern-redacted.
- Evidence failure is non-fatal: callback is fail-open (`dropped_events` counter);
  `init_governance` returns `None` on any construction failure.

## Annotations (human-maintained)

`governance-tool-overrides.yaml` — action type, side effect, reversibility,
data classes and approval semantics per tool. `confirm_order` is the single
write action (`approval.required: true`, granted derived from its `response`
argument). Discovered ≠ observed ≠ authorized: `discovery.json` keeps
`authorization: unresolved` until the ACAP step.

## Tests

```bash
python -m unittest tests.test_governance_probe -v
```

Offline (no network/FAISS): fake chat-model run, tool run + catalog enrichment,
tool error, redaction, parent/child trace correlation, approval enrichment
(yes/no), writer-failure fail-open, plain-function discovery, config merge.
