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

## Changing the enforcement mode from the dashboard

`governance.yaml`'s `enforcement_mode` is what SkyQuery *sends*; it remains the
local fallback and nothing here replaces it. The dashboard can additionally hold
a per-system override, and the mode actually applied is the **stricter** of the
two:

| governance.yaml | dashboard | effective |
|---|---|---|
| observe | *(none)* | observe |
| observe | enforce | **enforce** |
| enforce | observe | **enforce** (the override is reported as ignored) |

A dashboard override can tighten a system's posture, never switch enforcement
off -- the same principle as local policy being a floor for verdicts.

The control is on the **Governed Actions** tab, above Kill Switches:
`SDK default | Observe | Shadow | Enforce`. The Overview tab shows the effective
mode read-only. "SDK default" clears the override, so `governance.yaml` drives
again.

The mode rides the `/actions/evaluate` response that already happens once per
governed action, so this costs no extra round trip and takes effect on
SkyQuery's **next** action, with no restart and no code change:

```
GET   /systems/{system_id}/enforcement-mode
PATCH /systems/{system_id}/enforcement-mode   {"mode": "enforce"}   # null clears
```

If the Agent7 API is unreachable, no mode is reported and SkyQuery's configured
mode stands -- the local manifest fallback is unchanged.

Pass `respect_remote_mode=False` to `GovernanceClient.from_config(...)` to pin a
deployment to its local mode and ignore the dashboard entirely.

### Validating it against a running SkyQuery

1. Start SkyQuery **once** with `enforcement_mode="observe"` in the bootstrap
   snippet. Do not restart it again during this test.
2. Open the Agent7 dashboard, select the `skyquery` system, and leave the mode
   control on **SDK default**.
3. Run a dangerous SQL prompt in Chat, e.g. one that produces
   `DROP TABLE ...`. The action is **recorded and allowed**: the Governed
   Actions row shows verdict `DENY` with mode `observe`, and the query still ran
   -- observe never blocks.
4. Click **Enforce** in the Governed Actions tab. The badge flips to `enforce`
   and the hint reads "SDK sends observe; dashboard override enforce".
5. Run the **same** prompt again. It is now blocked: verdict `DENY`, reason code
   `argument_pattern_denied`, outcome `denied_blocked`, and the SQL never
   reaches Trino.
6. SkyQuery was not restarted and its code did not change. Click **SDK default**
   to hand control back to `governance.yaml`.

A local dry run of the same loop, without SkyQuery, is
`examples/enforcement-demo-app/run_mode_demo.py --api http://127.0.0.1:8077`.

### One case the dashboard cannot reach

`instrument_from_config()` reads the enforcement mode **once**, at wrap time. In
`observe`, capabilities whose status is `denied` or `rejected` are skipped and
never wrapped, so there is no wrapper for a later `enforce` to consult. Boot in
`shadow` if you want runtime mode control over those too.

This does not affect the dangerous-SQL case above: `execute_generated_sql` is an
*approved* capability guarded by `denied_argument_patterns`, and approved
capabilities are always wrapped.

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
- The enforcement-mode override is unauthenticated for the same reason. Because
  strictest wins, reaching the API cannot *disable* enforcement, but it can
  tighten a system into blocking. Do not expose that port beyond localhost yet.
- The effective mode is resolved per action against the mode the SDK sent on
  that call. There is no caching, so an override applies immediately.
