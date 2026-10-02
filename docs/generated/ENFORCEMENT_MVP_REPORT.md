# Pre-Execution Enforcement MVP Report

**Date:** 2026-09-27
**Milestone:** Agent7 Pre-Execution Enforcement Library
**Schema version:** 0.1 (additive: new `action_decision` event type)

## Purpose

Move Agent7 from post-action evidence to runtime control. The SDK now decides
**before** a governed function runs, and can prevent the function body from
executing at all.

Previously `GovernanceClient.tool()` emitted `tool_start`, called the function,
then emitted `tool_end`/`tool_error`. It could prove what an agent did, never
prevent what it was about to do. `instrument_from_config()` skipped any
capability a human had rejected, so a denied capability was not even wrapped.

## How It Works

```
call governed function
  -> build ActionRequest      (no raw argument values)
  -> authorize                 local policy + backend, most restrictive wins
  -> enforce_decision(mode)    -> (should_execute, execution_status)
       observe  : always run, record observe_only
       shadow   : always run, record would_have_blocked
       enforce  : DENY / unapproved REQUIRE_APPROVAL do not run
  -> ALLOW  : tool_start -> function -> tool_end / tool_error
  -> BLOCK  : action_decision only; function never called
  -> ActionRecord written to its own sink
```

Decision priority is fixed and must not be reordered:

`kill switch -> denied/rejected -> not approved -> argument policy -> approval required -> allow`

### Local policy is a floor

Both the local and backend verdicts are computed, and the **more restrictive**
one wins. This matters because some rules exist only locally:
`denied_argument_patterns` inspects live argument values, which never leave the
process, so a backend ALLOW must not be able to wave them through. An
unreachable backend likewise never downgrades a local DENY.

A verified local approval is the one permitted upgrade: it releases a backend
`REQUIRE_APPROVAL` hold, because the approval token stays in-process and the
backend cannot see it. A DENY is never upgraded.

### Backward compatibility

Default `enforcement_mode` is `observe`, in which the SDK's observable output is
what it was before this milestone, apart from one added dict key:

| | observe (default) | shadow | enforce |
|---|---|---|---|
| Blocks execution | never | never | DENY and unapproved holds |
| `action_decision` events | **none** | on non-ALLOW | on non-ALLOW |
| ActionRecord file | **not created** | written | written |
| Denied capability wrapped | no (skipped, as before) | yes | yes |
| Decision visible | in-band on `tool_start` | in-band + event | in-band + event |

Every existing test passes unedited, including the three that pin this
behaviour: `test_skips_rejected`, `test_double_instrumentation_does_not_double_wrap`
(still exactly 2 events per call) and the `test_custom_function_adapter`
event-sequence assertions.

### Async

The wrapper was sync-only. `inspect.iscoroutinefunction` now selects a parallel
`async def` wrapper that awaits the original. A denied coroutine never runs its
body — proven by a side-effect list, not by its return value.

## Privacy

Action records, decision payloads and the backend tables carry **no raw argument
values**. An ActionRequest persists only:

- `arguments_hash` (sha256 of the sanitized arguments)
- `argument_names`, `argument_types` (type names only)
- `argument_features` (count, has-string-args)
- on a pattern denial, `matched_pattern_id` — never the text that matched

`denied_argument_patterns` is evaluated against live values in-process, before
anything is persisted, then discarded. That is both stricter and more correct
than matching the sanitized summary, which truncates at 512 characters.

Verified end to end: after the demo run, `DROP TABLE flights`, `s3://exports`
and `AREA-TOKYO-01` appear in neither `actions.jsonl` nor any SQLite row.

### A deny rule must never silently never-fire

A double-quoted YAML scalar turns `\b` into a literal backspace, producing a
regex that can never match. Because that is a security control failing open and
silently, `_compile_patterns` rejects any pattern containing a control character
with an error that names the fix. Write regexes in single quotes:

```yaml
denied_argument_patterns:
  - id: destructive_sql
    pattern: '(?i)\b(drop|delete|truncate|alter)\b'
```

### Approvals

`approval.granted` is **not** trusted — it is asserted by the code being
governed and is spoofable. Only `verified`, `trusted` or `token_verified` set to
`True` releases a hold, via a call-time `agent7_approval=` kwarg or the
`gov.approval({...})` context manager. `verify_approval_token()` is the seam for
real signature verification; today it is a deterministic flag check.

## Manifest Schema

```yaml
enforcement_mode: observe | shadow | enforce   # optional, default observe

capabilities:
  - capability_id: CAP-...          # optional
    name: run_trino_query           # required
    module_path: app.run_trino_query # required
    status: approved                # required
    action_type: execute
    approval_required: false
    data_classes: [operational]
    external_side_effect: false
    denied_argument_patterns:       # optional, local-only
      - id: destructive_sql
        pattern: '(?i)\bdrop\b'

kill_switches:                      # optional
  - id: disable_live_airspace
    enabled: false
    target_capabilities: [fetch_live_flights]
    verdict: DENY
    reason: "Live airspace disabled"
```

| Status | Wrapped in observe | Wrapped in shadow/enforce |
|---|---|---|
| `approved`, `approved_for_acap`, `edited` | yes | yes |
| `denied`, `rejected` | no (skipped) | yes, as `wrapped_for_enforcement` |
| `pending` | no | no |
| `false_positive`, `not_a_capability` | never | never |

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/actions/evaluate` | Authorize an action; persists action + decision |
| POST | `/actions/record` | Persist the execution outcome |
| GET | `/systems/{id}/actions` | Governed actions with summary counts |
| GET | `/systems/{id}/actions/{action_id}` | Request + decision + record |
| POST | `/systems/{id}/kill-switches` | Create a kill switch |
| GET | `/systems/{id}/kill-switches` | List kill switches |
| PATCH | `/systems/{id}/kill-switches/{ks_id}` | Enable/disable |
| GET | `/systems/{id}/enforcement-mode` | Effective mode, and how it was resolved |
| PATCH | `/systems/{id}/enforcement-mode` | Set or clear the dashboard override |

`/actions/evaluate` deliberately does not validate the system: a governed app
may post actions before any discovery upload exists. The same applies to the
enforcement-mode endpoints.

`/actions/evaluate` also returns an `enforcement_mode` block beside `decision`:
the effective mode for the system, which is the stricter of the mode the SDK
sent and any dashboard override. The SDK applies it, so a mode set in the
dashboard reaches a running app on its next action without a restart. The
`decision` object itself is unchanged.

One action can carry two decisions — the backend's evaluate result and the
effective decision the SDK enforced. The listing joins on the enforced one, so
each action yields exactly one row.

## Test Coverage

| Suite | Tests | Covers |
|---|---|---|
| `tests/test_enforcement.py` | 35 | ALLOW executes; DENY does not execute (sync **and** async); REQUIRE_APPROVAL held; `granted` alone rejected; `verified` released; observe never blocks and writes no record file; shadow records would-have-blocked; kill switch; manifest wrapping per mode; argument policy; no raw values persisted; blocked-result shape; `on_deny="raise"`; endpoint normalisation; backend DENY honoured; unreachable backend falls back to local DENY; backend ALLOW cannot bypass local argument policy; YAML control-character guard |
| `tests/test_enforcement_api.py` | 14 | evaluate ALLOW/DENY; kill switch forces DENY and can be disabled; approval held; action list and summary; one row per action; shadow counter accuracy; action detail; 404s; validation |

```
python -m unittest discover -v
python -m pytest tests -q
```

Result: **257 passed, 29 failed**. The 29 failures are pre-existing and
unrelated — they require `artifacts/governance/events.jsonl`, a gitignored
fixture absent from this working copy. Verified by stashing all changes and
re-running: the baseline is identical at 29 failed / 210 passed, so this
milestone adds 47 tests and breaks none.

## Files

| File | Purpose |
|---|---|
| `sdk-python/ai_governance/core/actions.py` | `ActionRequest`, `ActionRecord`, modes, execution statuses |
| `sdk-python/ai_governance/core/decisions.py` | `Decision`, verdicts, reason codes |
| `sdk-python/ai_governance/enforcement.py` | Policy compilation, local engine, mode semantics, transport, recorder |
| `sdk-python/ai_governance/client.py` | Constructor options, `authorize`, sync + async wrappers, denied-capability wrapping |
| `sdk-python/ai_governance/manifest.py` | `enforcement_mode` / `kill_switches` validation, new status constants |
| `sdk-python/ai_governance/core/{schema,events}.py` | `action_decision` event type; `_final` override |
| `services/evidence_api/enforcement.py` | Backend decision engine |
| `services/evidence_api/db.py` | 4 tables + helpers |
| `services/evidence_api/app.py` | 7 endpoints |
| `services/evidence_api/static/*` | Governed Actions tab, kill-switch UI, seven-pillar ribbon |
| `examples/enforcement-demo-app/` | Runnable demo |
| `docs/generated/SKYQUERY_AGENT7_INTEGRATION_GUIDE.md` | SkyQuery integration |
| `docs/generated/ENFORCEMENT_MVP_REPORT.md` | This report |

## What This Proves

- A denied capability does not execute its function body — sync or async.
- An approved capability still executes and emits the same evidence as before.
- A kill switch created in the dashboard blocks a **separately running** app on
  its next call, with no restart and no code change.
- Governed actions, decisions and records are persisted and visible via API and UI.
- No raw arguments, prompts or secrets reach any record or table.

Verified against a live server: 12 governed actions, 5 allowed, 5 denied,
2 held, and `fetch_live_flights` flipping from `allowed_executed` to
`denied_blocked` with reason code `kill_switch` after a UI toggle.

## Limitations

- Remote decisions cost one synchronous HTTP call per governed action (1s
  timeout, local fallback). No caching, batching or connection reuse.
- Approval verification is a flag check, not cryptography.
- `denied_argument_patterns` is a regex guard, not a SQL parser, and only
  inspects string arguments at the top level of the call signature.
- Local policy is a floor, so a stale local manifest can block something the
  backend would allow. An unknown capability is denied in enforce mode.
- Instrumentation rebinds module attributes only. A caller that did
  `from app import fn` before `instrument_from_config()` keeps an ungoverned
  reference. Pre-existing property of the mechanism, but it now decides whether
  a control applies at all.
- Kill switches are per-system and unauthenticated; the API has no CORS and no
  RBAC. Do not expose it beyond localhost.
- The evidence-event HTTP sink and the enforcement endpoints use separate
  connections; a slow Agent7 API adds latency to the governed app.

## Next Recommended Milestone

**Make the control trustworthy and affordable under load**, in this order:

1. **Real approval verification.** Replace the flag check with a signed,
   short-lived, action-bound approval token. Until this lands, an
   approval-gated capability is only as strong as the process calling it.
2. **Decision caching and a policy version stamp.** Cache the kill-switch and
   capability snapshot with a short TTL and an explicit policy version, so the
   hot path does not pay an HTTP round trip per action and every record can name
   the exact policy version it was decided under.
3. **Authenticated kill switches with an audit trail.** Who disabled a control,
   when, and why — a kill switch is itself a privileged action and should be a
   governed action in its own right.
4. **Enforcement findings.** A deterministic rule over the action tables
   ("a denied capability was attempted N times", "an action executed while the
   backend was unreachable") to close the PROVE → COMPLY → LEARN loop.
