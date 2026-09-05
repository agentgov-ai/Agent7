# Instrumentation plan — Restaurant Agent (generated 2026-07-17)

Based on `REPO_INVENTORY.md`. Route chosen per `docs/INSTRUMENTATION_DECISION_TREE.md` Step 2 (**no existing tracing**): a local LangChain callback handler attached through the invocation `config`, writing privacy-safe JSONL to `artifacts/governance/`.

## 1. Minimum code insertion points

| # | Insertion point | Location | Change |
|---|---|---|---|
| 1 | **Root callbacks** | `agent.invoke(...)` call, `Restaurant_agent1.py:319` (inside `main()`) | Add `"callbacks": [governance_callback]`, `"tags": ["governance-poc"]`, and `"metadata": {"system_id", "deployment_id", "environment"}` to the existing `config` dict. Callbacks propagate to all child chat-model and tool runs — one insertion covers the whole hierarchy. |
| 2 | **Tool discovery** | Tool list at `Restaurant_agent1.py:274` | Pass the same 6-function list to `write_tool_discovery(...)` at startup (feature-flagged). No tool code changes. |
| 3 | **Approval evidence** | `confirm_order` tool events | No in-function edit needed for v1: the callback's `tool_start` for `confirm_order` carries the sanitized `response` argument ("yes"/"no"), which *is* the customer-confirmation event. Pair rule: `place_order` start must precede `confirm_order` in the same trace. Annotate `approval.required: true, condition: customer_confirmation` via override file. |
| 4 | **Prompt fingerprint** | `SYSTEM_PROMPT`, lines 241-266 | Hash at startup (discovery output), plus message-shape metadata from `on_chat_model_start`. No raw content. |
| 5 | **Feature flag** | Wherever the callback is constructed | `GOVERNANCE_EVIDENCE=1` env var; when unset, zero instrumentation objects are created and the invoke config is unchanged. |

**Prerequisite refactor (DONE 2026-07-17):** the interactive loop, the `Mo.invoke("hello")` smoke test and `review_orders()` are now inside `main()` (`Restaurant_agent1.py:292`) under `if __name__ == "__main__":` (line 341); the dead Colab `os.rename` was removed. Module-level construction (loader, FAISS, agent) is unchanged. Import verified: no LLM call, no `input()` block. Residual: full baseline-transcript diff of `python Restaurant_agent1.py` is still pending Slice 0 (currently blocked on `.env` UTF-8 re-save).

## 2. Field-by-field evidence matrix

Legend: **captured** (automatic) · **partial** · **annotation** (needs override/human input) · **unavailable** · **disabled** (privacy choice, not a gap).

| Field | Status | Source / note |
|---|---|---|
| schema_version, event_id, UTC timestamp | captured | writer |
| system_id, deployment_id, environment | annotation | constants in callback config (`restaurant-agent` / `local-test` / `local`) |
| trace_id / span_id / parent_span_id | captured | callback `run_id`/`parent_run_id`; root = trace |
| event_type, component kind/name | captured | callback method + serialized name |
| model provider/name | captured | `invocation_params` on chat-model start (`qwen/qwen-2.5-7b-instruct`); provider annotated as `openrouter` (base_url not exposed in params — verify, else annotation) |
| prompt template id/hash | captured | SHA-256 of `SYSTEM_PROMPT` + docstring hashes at discovery |
| message shape (count/roles) | captured | `on_chat_model_start` |
| raw prompts/outputs | **disabled** | hashes only, by design |
| tool name | captured | `on_tool_start` |
| tool action classification | annotation | override file: `get_menu`=read, `place_order`=draft, `confirm_order`=**write**, etc. |
| sanitized tool arguments/results | captured | `sanitize()` redaction (emails, phones, long digits, secret-like keys) |
| tool outcome/error, duration | captured | `on_tool_end`/`on_tool_error` + timers |
| retrieval source identifiers | **partial/unavailable** | FAISS is called *inside* `get_menu`/`show_receipt`, not as a retriever → no retriever callbacks. Visible only as tool-level evidence. Upgrade path (later slice, optional): wrap `db` as retriever or add in-tool annotation. Must be reported honestly as a gap. |
| agent identity | annotation | logical name `restaurant-agent-main` |
| session/user reference | partial | `thread_id` from config (pseudonymous); `Name_User` context is PII → excluded |
| approval required/granted | partial + annotation | derivable from `confirm_order` args + override rule; no separate app approval event exists |
| data classification | annotation | override file (`public_menu`, `order`, `contact`) |
| token usage | captured (**verified live 2026-07-17**) | real input/output/total tokens on every `llm_end` in live runs |
| status/error type | captured | error callbacks + agent's own try/except (exceptions inside the loop are also caught by app; callback sees them first) |

## 3. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Committed API key** | **resolved** (2026-07-17) | Key externalized: `get_model` reads `os.environ.get("API_KEY")` (line 65) via `python-dotenv`; `.env` is gitignored; user rotated (revoked) the old key still visible in git history/notebook. Standing rule: instrumentation must never serialize `api_key` kwargs — sanitizer redacts `api[_-]key` keys; verify `invocation_params` never includes it; never print the key in any artifact. Residual: `.env` must be UTF-8 (UTF-16 parses to zero vars → startup error). |
| Menu filename mismatch | **resolved** (2026-07-17) | `Restaurant_agent1.py:20` now loads the existing `Indian_restaurant_menu_Extract.xlsx` (absolute path); load verified. Residual: absolute path makes the script machine-specific. |
| Script not importable / interactive-only | **resolved** (2026-07-17) | `main()` + `__main__` guard in place; import verified without LLM call or `input()` block. Baseline-transcript validation of the script path pending Slice 0. |
| Live LLM call at import (`Mo.invoke("hello")`) | **resolved** (2026-07-17) | Smoke-test call moved inside `main()` (line 294) — still runs on `python Restaurant_agent1.py` (behavior preserved), never on import. |
| Behavior change from instrumentation | high | Callbacks are passive; feature flag off by default; run identical scripted conversation with flag on/off and diff visible output. |
| Duplicate events | low | No other tracing active; keep LangSmith unconfigured; assert one `llm_start` per model call in tests. |
| Raw content leakage via sanitized summaries | medium | Content capture = hash/shape by default; sanitized summaries only for tool args/results; add redaction unit tests (dish names are public data; `Name_User` treated as PII). |
| Real-world side effects | low | Only side effect is local `orders_log.json` append. No payment/reservation/messaging APIs exist. Back up `orders_log.json` before scenario runs. |
| Python 3.14 vs recommended ≤3.10 | medium | Record versions in evidence; if runtime failures appear, ask user before changing environments. |
| Callback signature drift (reference probe vs langchain-core 1.2.17 / `create_agent` LangGraph runs) | medium | Verify `on_chat_model_start`, `on_tool_start(inputs=...)` signatures against installed version in a smoke test before full scenarios. |
| stdout-printed tool output (`confirm_order`, `show_receipt`) invisible to trace | medium | Outcome still captured via tool events; note in coverage that "final user-visible text" is partially out-of-band. |
| Performance overhead | low | Local JSONL append with lock; measure per-turn latency delta in scenario run. |

## 4. Ordered implementation plan

Each slice is small, feature-flagged, and reviewed before the next.

**Slice 0 — Baseline (DONE 2026-07-17, live)**
Menu-file name resolved, API key externalized to `.env` and fixed by user; OpenRouter routing pinned (`require_parameters: true`) after intermittent text-tool-call providers broke orchestration. Canonical scripted conversation recorded flag-off: `artifacts/governance/baseline/transcript_baseline_live.txt` + `orders_log` pre/post backups.
*Accept:* agent runs end-to-end — **verified**; transcript recorded; package versions logged in `discovery.json`.

**Slice 1 — Import-safe entry point (DONE 2026-07-17)**
`main()` + `__main__` guard implemented; smoke-test LLM call moved into `main()`; dead Colab `os.rename` (unconditional `FileNotFoundError` at exit) removed.
*Accept:* module importable without starting the loop or making an LLM call — **verified**; module-level init still runs on import — documented. Identical-behavior check of `python Restaurant_agent1.py` against the baseline transcript remains with Slice 0.

**Slice 2 — Local JSONL capture (IMPLEMENTED 2026-07-17; live verification pending)**
`governance_probe/` package created (writer, fail-open callback, discovery, bootstrap); callback attached via `merge_invoke_config` behind `GOVERNANCE_EVIDENCE=1`; `.gitignore.additions` merged into `.gitignore` (`artifacts/governance/` ignored — verified). Offline verification done: 15 unit tests pass (hierarchy correlation, redaction, tool error, fail-open, no-raw-content, required schema fields); flag-off import creates zero governance objects.
*Accept (live, 2026-07-17):* **verified** — two full live conversations with connected root→model→tool hierarchy (0 orphan events), no raw content, token usage captured; no instrumentation-caused behavior difference vs baseline. See `docs/generated/LIVE_VALIDATION_REPORT.md`.

**Slice 3 — Discovery + enrichment (IMPLEMENTED 2026-07-17)**
`discovery.json` generated for the 6 real tools (from the same `TOOLS` list passed to `create_agent`, plain-function aware) with system-prompt SHA-256, model annotation and package versions; `governance-tool-overrides.yaml` written with real names (`confirm_order` = write + `approval.required` + `granted_when: response == "yes"`); callback consumes overrides (unit-tested: read vs write distinguished, approval granted derived, `authorization: unresolved` preserved).
*Accept (live, 2026-07-17):* **verified** — live `confirm_order` tool_start carries `action_type: write`, `external_side_effect: true`, `approval {required: true, granted: true, policy_id: customer_confirmation}`, preceded by `place_order` in the same trace, matching real order `194235`.

**Slice 4 — Scenarios + coverage**
Scripted scenario runner (A read-only menu query; C invalid/error input; D confirm without "yes" path; E local adversarial "skip confirmation" input). Generate `coverage.json` + `run-summary.md` using the matrix statuses above.
*Accept:* every required field reported as captured/partial/annotation/unavailable/disabled; `orders_log.json` restored after runs; events immutable during a run.

**Slice 5 — Draft ACAP + human confirmation**
Generate `acap-draft.yaml` from discovery + overrides; ask the user only the 7 business questions from `docs/MINIMAL_ACAP.md`. Discovered ≠ observed ≠ authorized kept separate.
*Accept:* ACAP lists real tools/model/prompt fingerprints; authorization fields remain `unresolved` until human answers.

**Slice 6 — Deterministic finding**
Rule: *a `confirm_order` write event whose trace lacks a preceding `place_order` proposal, or whose `response` argument ≠ "yes", constitutes an unapproved write.* Drive Scenario D/E to trigger it; emit `findings.json` linked to exact event IDs + rule version.
*Accept:* at least one finding with event-ID citations; re-running the checker on the same events is deterministic.

**Slice 7 — GO/NO-GO report**
Write recommendation per `docs/FIRST_OBJECTIVE.md` criteria; likely **CONDITIONAL GO** shape (action type, data class, approval semantics require annotation — expected). OTLP export only after this, as a separate decision.

## 5. Out of scope (reconfirmed)

No dashboard/FastAPI/DB/Kafka/OPA, no agent rewrite, no dependency upgrades, no LangSmith activation, no OTel until local capture is proven, no raw-content capture mode.
