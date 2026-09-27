# SkyQuery Agent7 Integration Guide

**Date:** 2026-09-27
**Milestone:** Pre-Execution Enforcement
**Applies to:** SkyQuery FastAPI backend (`localhost:8000`), Next.js frontend (`localhost:3000`)

## Purpose

Show where Agent7 belongs in SkyQuery and how to add pre-execution enforcement
with one bootstrap snippet and a `governance.yaml`, without editing the body of
any SkyQuery function.

## Where Agent7 integrates

**The FastAPI backend, not the Next.js frontend.**

Every consequential SkyQuery action happens server-side: natural-language SQL
execution, Trino query execution, OpenSky live-flight fetches, Open-Meteo
weather calls, Redis session and auth work, and exports. The frontend only
renders results.

Instrumenting the browser would be both unenforceable and pointless: a control
that runs in the client can be bypassed by anyone who can call the API directly.
Agent7 sits in the backend process, between the agent's decision to act and the
code that performs the action.

```
Next.js (:3000)  ──HTTP──>  FastAPI (:8000)
                                │
                                ├── GovernanceMiddleware   (request trace)
                                │
                                └── @gov.tool / manifest wrapper
                                        │
                                        ├─ ActionRequest  ─> decision engine
                                        │                    (local + Agent7 API)
                                        ├─ ALLOW    -> run the function
                                        ├─ DENY     -> body never runs
                                        └─ HOLD     -> body never runs
                                                 │
                                                 └─> Agent7 (:8077) evidence + action records
```

Run the Agent7 Evidence API on a **different port** from SkyQuery — both default
to 8000. The examples below use 8077 for Agent7.

## Install

```powershell
python -m pip install -e .\sdk-python
```

The SDK has no required runtime dependencies. `PyYAML` is needed for manifests:

```powershell
python -m pip install "agent-governance-sdk[acap]"
```

## governance.yaml

Place this at the SkyQuery backend root, beside the module that defines the
governed functions.

```yaml
system_id: skyquery
deployment_id: local-dev
environment: local
agent_id: skyquery-copilot

# Start at observe. Move to shadow, then enforce, once the action list looks right.
enforcement_mode: observe

capabilities:
  - name: execute_generated_sql
    module_path: app.services.query.execute_generated_sql
    action_type: execute
    status: approved
    data_classes: [flight, operational]
    external_side_effect: false
    denied_argument_patterns:
      - id: destructive_sql
        pattern: '(?i)\b(drop|delete|truncate|alter|grant|insert|update)\b'

  - name: run_trino_query
    module_path: app.services.trino.run_trino_query
    action_type: execute
    status: approved
    data_classes: [flight, operational]
    external_side_effect: false

  - name: fetch_live_flights
    module_path: app.services.opensky.fetch_live_flights
    action_type: read
    status: approved
    data_classes: [flight]
    external_side_effect: true

  - name: fetch_weather_context
    module_path: app.services.weather.fetch_weather_context
    action_type: read
    status: approved
    data_classes: [weather]
    external_side_effect: true

  - name: compute_proximity_risk
    module_path: app.services.risk.compute_proximity_risk
    action_type: read
    status: approved
    data_classes: [flight]
    external_side_effect: false

  - name: export_query_result
    module_path: app.services.export.export_query_result
    action_type: communicate
    status: approved
    approval_required: true
    data_classes: [flight, export]
    external_side_effect: true

  # Observed but never blocked: session restore is not a consequential action.
  - name: restore_copilot_session
    module_path: app.services.session.restore_copilot_session
    action_type: read
    status: approved
    data_classes: [session]
    external_side_effect: false

kill_switches:
  - id: disable_live_airspace
    enabled: false
    target_capabilities: [fetch_live_flights]
    verdict: DENY
    reason: "Live airspace feed disabled by operator"
```

Write regexes in **single** quotes. A double-quoted YAML scalar turns `\b` into
a literal backspace; the SDK rejects such a pattern rather than letting a deny
rule silently never fire.

## Bootstrap snippet

Add to the SkyQuery FastAPI app module, after `app = FastAPI(...)`:

```python
from ai_governance import GovernanceClient
from ai_governance.adapters.fastapi import GovernanceMiddleware

gov = GovernanceClient.from_config(
    "governance.yaml",
    api_endpoint="http://127.0.0.1:8077",
    enforcement_mode="enforce",   # observe | shadow | enforce
)

gov.instrument_from_config()

app.add_middleware(
    GovernanceMiddleware,
    governance_client=gov,
)
```

That is the whole integration. No `if`/`else` goes inside a SkyQuery function —
the wrapper decides and enforces before the body runs.

### Import-order requirement

`instrument_from_config()` rebinds the function in **its own module's**
namespace. A module that did `from app.services.opensky import fetch_live_flights`
before instrumentation keeps an unwrapped reference and will not be governed.
Either call `gov.instrument_from_config()` before importing those routers, or
have call sites use the module attribute:

```python
from app.services import opensky
...
flights = opensky.fetch_live_flights(region)   # governed
```

### Async functions

SkyQuery's service functions are mostly `async def`. That is supported: the
wrapper detects coroutine functions and awaits the original. A denied coroutine
never runs its body.

### Turning a block into an HTTP 403

By default a blocked call returns `{"agent7_blocked": True, "verdict": ..., ...}`.
For a FastAPI route, raising is usually cleaner:

```python
from ai_governance import Agent7Blocked

gov = GovernanceClient.from_config("governance.yaml", api_endpoint="...",
                                   enforcement_mode="enforce", on_deny="raise")

@app.exception_handler(Agent7Blocked)
async def agent7_blocked_handler(request, exc):
    return JSONResponse(
        status_code=403,
        content={"error": "blocked_by_governance", "reason": exc.reason,
                 "action_id": exc.action_id},
    )
```

### Approvals

`approval.granted` is **not** trusted — it is asserted by the code being
governed. Only `verified`, `trusted` or `token_verified` set to `True` releases
an approval-gated action:

```python
with gov.approval({"verified": True, "approver_id": reviewer_id}):
    result = export.export_query_result(dataset, destination)
```

For this milestone that is a deterministic flag check, not cryptographic
verification. Wire it to your real approval service before relying on it.

## Demo flow

1. **Run SkyQuery normally.** Confirm Chat and Discover work: `localhost:3000`.
2. **Add the bootstrap snippet** and `governance.yaml` to the FastAPI backend.
   Start with `enforcement_mode="observe"` — behaviour is unchanged.
3. **Start the Agent7 dashboard** on a free port:
   ```powershell
   python -m uvicorn services.evidence_api.app:app --host 127.0.0.1 --port 8077
   ```
   Open `http://127.0.0.1:8077/ui/`.
4. **Run a Chat query** in SkyQuery. The natural-language SQL executes as usual.
5. **Show the governed SQL action** in the Governed Actions tab: capability
   `execute_generated_sql`, verdict `ALLOW`, outcome `allowed_executed`. Open the
   row to show the argument hash and argument names — the SQL text itself is not
   stored.
6. **Open "Discover flights near Tokyo."** `fetch_live_flights` appears, allowed.
7. **Enable the kill switch** for `fetch_live_flights` in the Governed Actions
   tab and set a reason.
8. **Refresh the Discover view.** The fetch is now blocked: verdict `DENY`,
   reason code `kill_switch`, and the OpenSky call never leaves the process.
   SkyQuery was not restarted and its code did not change.
9. **Show the evidence.** The action detail carries the action id, decision id,
   enforced verdict, kill switch id and evidence hash; `events.jsonl` carries the
   matching `action_decision` event.

Switch `enforcement_mode` to `enforce` before step 7 — in `observe` the kill
switch is recorded but nothing is blocked.

## Suggested governed capabilities

| Capability | Action type | Why it is governed |
|---|---|---|
| `execute_generated_sql` | execute | Model-authored SQL against live data; argument policy blocks destructive statements |
| `run_trino_query` | execute | Direct query execution and cost exposure |
| `fetch_live_flights` | read | External OpenSky call; the kill-switch target |
| `fetch_weather_context` | read | External Open-Meteo call |
| `compute_proximity_risk` | read | Safety-relevant derived output |
| `export_query_result` | communicate | Data leaves the system; approval required |
| `restore_copilot_session` | read | Observe-only; session state, not a consequential action |

## Rollout order

1. `observe` — evidence only; nothing blocks. Confirm the action list is complete
   and no capability is missing from the manifest.
2. `shadow` — decisions computed and recorded as `would_have_blocked`. Review
   these before enforcing; anything unexpected here would be an outage in enforce.
3. `enforce` — blocks take effect.

Going straight to `enforce` risks blocking a legitimate capability that was
simply absent from the manifest: an unknown capability is denied in enforce mode.

## Limitations to know before relying on this

- Remote decisions add one synchronous HTTP call per governed action (1s
  timeout, falls back to local policy). Fine on localhost; measure before
  putting it on a hot path.
- Local policy is a floor: the result is the more restrictive of the local and
  backend verdicts. A stale local manifest can therefore block something the
  backend would allow.
- Approval verification is a flag check, not cryptography.
- `denied_argument_patterns` is a regex guard, not a SQL parser.
- Kill switches are per-system and unauthenticated — anyone who can reach the
  Agent7 API can toggle one. Do not expose that port beyond localhost yet.
