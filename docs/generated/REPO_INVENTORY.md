# Repository inventory — Restaurant Agent (generated 2026-07-17)

Read-only inspection. No code was changed. Companion document: `INSTRUMENTATION_PLAN.md`.

## 1. Language, packaging and versions

- **Language:** Python. Interpreter found on PATH: **Python 3.14.0** (INSTALL.md recommends ≤ 3.10; 3.14 may produce compatibility warnings).
- **Package manager:** pip, installed globally (no `.venv` detected in repo). **No dependency manifest exists** — no `requirements.txt`, `pyproject.toml` or lockfile. The only dependency record is the pip commands in `INSTALL.md`.
- **Installed versions relevant to the experiment** (from `pip list`, 2026-07-17):

| Package | Version |
|---|---|
| langchain | 1.2.10 |
| langchain-core | 1.2.17 |
| langchain-classic | 1.0.2 |
| langchain-community | 0.4.1 |
| langchain-openai | 1.1.10 |
| langchain-huggingface | 1.2.1 |
| langchain-text-splitters | 1.1.1 |
| langgraph | 1.0.10 |
| langgraph-checkpoint | 4.0.1 |
| langgraph-prebuilt | 1.0.8 |
| langsmith | 0.7.14 (transitive; no tracing configured) |
| faiss-cpu | 1.13.2 |
| sentence-transformers | 5.2.3 |
| unstructured | 0.18.32 |
| pydantic | 2.12.5 |
| python-dotenv | 1.2.2 |

- **Not installed:** opentelemetry-*, openinference-*, arize/phoenix, pytest.
- Verified imports: `from langchain.agents import create_agent` and `from langchain.tools import tool, ToolRuntime` both resolve — the script targets the **LangChain 1.x `create_agent` (LangGraph prebuilt) API**.

## 2. Entry points and commands

| Purpose | Command | Notes |
|---|---|---|
| Run agent (CLI) | `python Restaurant_agent1.py` | Interactive `input()` loop; exit with `exit`/`quit`/`bye` |
| Notebook | `Restaurant_Agent.ipynb` | Colab-era original of the same agent; contains the same hardcoded API key |
| Tests | **none exist** | No test files anywhere in the repo |

**Blocking run issue (RESOLVED 2026-07-17):** the script previously loaded `indian_restaurant_menu_50_items.xlsx`, which does not exist in the repo. `Restaurant_agent1.py:23` now loads the existing `Indian_restaurant_menu_Extract.xlsx`; load verified with `UnstructuredExcelLoader` (1 element). Note: the path is absolute (`C:\Users\shrey\Downloads\Restaurant_Agent\...`), so the script is machine-specific.

**Import-safety issue (RESOLVED 2026-07-17):** the interactive loop, the smoke-test model call (`Mo.invoke("hello")`) and `review_orders()` now live in `main()` (`Restaurant_agent1.py:292`) under an `if __name__ == "__main__":` guard (line 341); the dead Colab `os.rename` (which always raised `FileNotFoundError` after the loop) was removed. Importing the module makes **no LLM call** and does not block on `input()`; module-level init (Excel load, two FAISS builds, embedding demo prints, one client construction) still runs on import — documented, per plan Slice 1. Import verified 2026-07-17.

## 3. Agent construction style

`langchain.agents.create_agent` (LangChain 1.x prebuilt LangGraph ReAct-style agent), `Restaurant_agent1.py:271`:

- `model=get_model()` (fresh `ChatOpenAI` instance)
- `system_prompt=SYSTEM_PROMPT` (inline string, lines 241-266)
- `tools=[show_receipt, place_order, greet_customer, get_user_name, get_menu, confirm_order]` — plain functions, not `@tool`-decorated; `create_agent` converts them using docstrings as descriptions
- `context_schema=Context` (pydantic model with `Name_User`, `Receipt_User`)
- A `MemorySaver` checkpointer is instantiated (line 238) but **never passed to `create_agent`** — the `thread_id` in `config` is inert; conversation memory is a manually windowed list (last 6 messages).

## 4. Real invocation path

```
main() (line 292, runs only under __main__ guard)
  → Mo.invoke("hello") smoke test (line 294)
  → while True (line 302)
  → input("You: ")
  → conversation_history.append(user msg); window to 6
  → agent.invoke({"messages": conversation_history},
                 config={"configurable": {"thread_id": "1"}},
                 context=Context(Name_User=None, Receipt_User=None))   # line 319
  → LangGraph agent loop: chat model call → tool call(s) → chat model call → ...
  → response['messages'][-1].content printed via print_wrapped
  → on exception: generic apology + DEBUG print of the exception
```

Note: `confirm_order` and `show_receipt` **print their user-visible output directly to stdout and return ""**, so part of the user experience bypasses the model response entirely. `greet_customer()` is also called once directly (line 297, inside `main()`) outside the agent.

## 5. Model providers

| Role | Class | Model | Endpoint |
|---|---|---|---|
| Chat/agent LLM | `langchain_openai.ChatOpenAI` | `qwen/qwen-2.5-7b-instruct` | OpenRouter (`https://openrouter.ai/api/v1`) |
| Embeddings (line 31) | `HuggingFaceEmbeddings` | `all-MiniLM-L6-v2` | local CPU |
| Embeddings (line 46) | `HuggingFaceEmbeddings` | `sentence-transformers/all-mpnet-base-v2` | local CPU |

The FAISS index is built **twice**: line 39 with MiniLM (`db`), then line 269 rebinds `db` with mpnet embeddings. Tools resolve `db` at call time via module global, so **mpnet is the effective retrieval model**.

**Security finding (RESOLVED 2026-07-17):** the hardcoded OpenRouter API key was removed from `Restaurant_agent1.py`; `get_model` now reads `os.environ.get("API_KEY")` (line 65) loaded via `python-dotenv` (`load_dotenv()`, line 22) from a gitignored `.env`. The user rotated (revoked) the old key, which still appears in git history (commit 73a40a8) and the notebook — inert once revoked. Residual: `.env` must be saved as UTF-8 (a UTF-16 `.env` parses to zero variables and the client raises at startup); the key value must never be echoed into evidence artifacts or reports.

## 6. Prompt sources

- **One inline system prompt**: `SYSTEM_PROMPT`, `Restaurant_agent1.py:241-266`. Mandatory tool-order rules, prohibitions. No templates, no hub, no files, no dynamic construction.
- **Tool docstrings** act as secondary prompt surface (they instruct the model when to call each tool).
- User messages come from `input()` only.
- Fingerprinting target: hash of `SYSTEM_PROMPT` + per-tool docstring hashes.

## 7. Tools

| Tool | Lines | Proposed action type | Side effect | Notes |
|---|---|---|---|---|
| `greet_customer` | 86-91 | read (static) | none | Returns fixed greeting; also called directly outside agent |
| `get_user_name` | 93-106 | read (context) | none | Uses `ToolRuntime[Context]`; reads `Name_User` (PII-adjacent, always `None` in current wiring) |
| `get_menu` | 108-120 | read (retrieval) | none | `db.similarity_search(query, k=5)` — direct FAISS call, **not** a LangChain retriever |
| `place_order` | 123-139 | draft/propose | none | Only echoes items + asks for confirmation |
| `confirm_order` | 142-171 | **write** | **appends to `orders_log.json`** | The single consequential action; gated on `response == "yes"`; sets global `current_order_id`; prints confirmation, returns "" |
| `show_receipt` | 173-207 | read/compute | none | FAISS lookup per item, price regex, prints receipt, returns "" |

`review_orders` (lines 209-233) is a staff-facing function called after the loop (inside `main()`); **not** an agent tool. No external APIs: the only write target is a local JSON-lines file. The natural **approval semantic** already exists in-app: `place_order` (proposal) → customer "yes"/"no" → `confirm_order(items, response)`.

## 8. Retrievers, memory, databases, APIs

- **Retrieval:** FAISS in-memory vector store over the menu Excel (UnstructuredExcelLoader, `mode="elements"`). Accessed only via direct `similarity_search` inside tools — **retriever callbacks will never fire**.
- **Memory:** manual 6-message window list; `MemorySaver` created but unused.
- **Database:** none. Persistence = `orders_log.json` append (fixture-like data already present).
- **External APIs:** OpenRouter chat completions only. HuggingFace models are downloaded/cached locally at first run.

## 9. Existing callbacks / tracing / logging

**None.** No callbacks, no `LANGCHAIN_TRACING_V2`/LangSmith configuration, no OpenTelemetry/OpenInference, no logging module usage — only `print()`. The `langsmith` package is present as a transitive dependency but inactive. Per the decision tree this is the "no tracing" branch → a local callback handler via the invocation `config` is the correct, duplicate-free route.

## 10. Tests and safe fixture options

- No tests, no pytest. **Behavioral baseline must be created first** (scripted transcript of a canonical conversation).
- Safe fixtures already available: menu Excel (public data), `orders_log.json` (fake orders). The only side effect (local file append) is inherently sandboxed; no payment/reservation/messaging APIs exist, so scenarios B (reservation) and payment cases from `docs/RESTAURANT_SCENARIOS.md` **do not apply** — the consequential-boundary scenario (D) maps to `confirm_order`.
- Scenario driving is now possible via import: the module is import-safe (2026-07-17) — a scenario runner can `import Restaurant_agent1` and call `agent.invoke(...)` directly without the interactive loop or any live LLM call at import time (module-level FAISS/embedding init still runs).

## Reference assets in-repo (not yet wired)

- `reference/python/governance_probe/` — reference `GovernanceCallback` (langchain-core `BaseCallbackHandler`), JSONL `GovernanceEventWriter` with redaction (`writer.py`), and `discover_tools`. Callback signatures must be verified against langchain-core 1.2.17 before use.
- `schemas/governance-event.schema.json` — event schema v0.1.
- `templates/governance-tool-overrides.example.yaml`, `templates/restaurant-acap.example.yaml` — must be regenerated with the **real** tool names above (examples reference reservation/payment tools this app does not have).
