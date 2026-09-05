# Live validation report — governance evidence layer (2026-07-17)

Closes the two open acceptance items from `INSTRUMENTATION_PLAN.md` Slices 0 and 2/3:
live baseline (flag off) and the same canonical conversation with
`GOVERNANCE_EVIDENCE=1`. OpenRouter key fixed by user; provider routing pinned
earlier the same day (`require_parameters: true` in `get_model()`).

## Runs

Canonical scripted conversation (stdin-piped): greet with name → menu query →
order one masala dosa → confirm → receipt → exit.

| Run | Flag | Transcript | Result |
|---|---|---|---|
| Baseline | off | `artifacts/governance/baseline/transcript_baseline_live.txt` | Full flow; orders `193652`, `193654` written |
| Instrumented #1 | on | `artifacts/governance/transcript_instrumented.txt` | Model variance: re-called `place_order` on "yes", never called `confirm_order`; no order written |
| Instrumented #2 | on (explicit "yes confirm my order") | `artifacts/governance/transcript_instrumented_run2.txt` | Full flow incl. `confirm_order`; order `194235` written |

`orders_log.json` was backed up before the runs
(`baseline/orders_log.pre_live.json`) and restored afterward; the post-run
state is archived as `baseline/orders_log.post_live.json`.

## Verification results

| Check | Result |
|---|---|
| **Behavior diff vs baseline** | **No instrumentation-caused difference.** Both runs completed the app loop identically (greet → menu → order → confirm path reachable → receipt → `review_orders()` on exit; exit code 0 in all runs). Observed differences are model stochasticity, not instrumentation: wording varies per run, and run-to-run tool choice varies (baseline itself called `confirm_order` twice on the receipt "yes"; instrumented #1 skipped confirmation). The callback is passive — it never alters `messages`, tools or model params — and the identical variance class appears with the flag off. |
| **events.jsonl exists** | Yes — `artifacts/governance/events.jsonl`, 134 events (62 run #1 + 72 run #2), append-only, gitignored. |
| **Root→model→tool hierarchy connected** | Yes — 0 orphan events across all traces (every `parent_span_id` resolves to a span in the same trace). One trace per user turn, each containing root `chain_start` (parent `null`) → LangGraph node chains → `llm_start/end` → `tool_start/end`. Example trace `019f706c…`: `place_order` → `confirm_order` under the same root. |
| **confirm_order enrichment** | Yes — live `tool_start` event: `action_type: "write"`, `external_side_effect: true`, `target: "orders_log.json"`, `data.classifications: ["order"]`, `sanitized_arguments: {items: "masala dosa", response: "yes"}`, `approval: {required: true, granted: true, policy_id: "customer_confirmation"}`. A `place_order` start precedes it in the same trace (pair rule for Slice 6 satisfied). The event corresponds to real side effect order `194235` in `orders_log.json`. |
| **No raw prompt/response content** | Yes — probes for system-prompt fragments (`restaurant waiter bot`, `MANDATORY ORDER`) and response fragments (`Welcome to our restaurant`, `YOUR RECEIPT`, etc.): none found. All `llm_start` events have `content_capture: "hash"` + message shape/roles only. Customer name `Shrey` appears nowhere in events; `get_user_name` result persisted as `<redacted-data-class:contact>` (hash only). |
| **Package versions logged** | Yes — `discovery.json` records langchain 1.2.10, langchain-core 1.2.17, langchain-openai 1.1.10, langgraph 1.0.10, faiss-cpu 1.13.2, sentence-transformers 5.2.3, plus system-prompt SHA-256 (`sha256:d6dc9689…`, capture=hash) and model `qwen/qwen-2.5-7b-instruct` @ openrouter. |

## Additional live observations

- **Token usage captured**: every `llm_end` carries real input/output/total tokens
  (e.g. 945/26/971 … 2268/22/2290) — the "verify in first instrumented run" item
  from the evidence matrix is now confirmed **captured**.
- **Model name captured live** from `invocation_params` on every `llm_start`.
- **Durations** present on all `*_end` events; JSONL cost is a single local
  append per event (~55 KB per full conversation). No user-visible latency
  difference; turns remain dominated by OpenRouter latency (seconds).
- **Event types observed live**: `chain_start/end`, `llm_start/end`,
  `tool_start/end`. Not observed (as predicted): `retriever_*` (FAISS runs
  inside tools), `agent_action/finish` (not emitted by LangGraph
  `create_agent`), and no error events (no failures occurred).
- **Governance-relevant behavior quirk (both modes)**: after an order is
  confirmed, a follow-up "yes" (meant for the receipt) can cause the model to
  call `place_order`+`confirm_order` again, writing a duplicate order
  (baseline orders `193652`+`193654`). This is a real candidate violation for
  the Slice 6 deterministic rule and is now visible in evidence.
- Instrumented #1 shows the flip side: `confirm_order` may be skipped
  entirely. Scenario runs for Slice 4/6 should use explicit confirmation
  wording, as run #2 did.

## Verdict

All six acceptance checks pass. Slices 0, 2 and 3 are now **live-verified**.
Next step per plan: Slice 4 (scenario runner + coverage report).
