# Agent7 Enforcement Demo

Proves that Agent7 decides **before** a function runs: a denied capability never
executes its body, an approval-gated capability is held, and a kill switch can
stop a working capability without redeploying the app.

## What the app contains

`app.py` is a small airspace-style backend with no external dependencies. Every
function appends to a module-level `SIDE_EFFECTS` list on entry, so the demo can
prove a blocked call never ran rather than just inspecting what it returned.

| Function | Manifest status | Expected outcome |
|---|---|---|
| `fetch_live_flights` | `approved` | Runs — until the kill switch is enabled |
| `run_trino_query` | `approved` + `denied_argument_patterns` | `SELECT` runs, `DROP` is denied |
| `export_query_result` | `approved`, `approval_required: true` | Held unless a verified approval is present |
| `delete_airspace_record` | `denied` | Never executes |

## Run it

Local policy only — no backend required:

```powershell
cd examples\enforcement-demo-app
python run_demo.py
```

With the dashboard, so actions are persisted and the kill switch is live:

```powershell
# terminal 1
python -m uvicorn services.evidence_api.app:app --host 127.0.0.1 --port 8000

# terminal 2
cd examples\enforcement-demo-app
python run_demo.py --api http://127.0.0.1:8000
```

Then open `http://127.0.0.1:8000/ui/` and select the **Governed Actions** tab.

Try the other modes to see the difference:

```powershell
python run_demo.py --mode observe   # never blocks, evidence identical to pre-enforcement releases
python run_demo.py --mode shadow    # never blocks, but records what it would have blocked
python run_demo.py --mode enforce   # actually blocks
```

## The kill switch

In the dashboard's **Governed Actions** tab, create a kill switch with id
`disable_live_airspace` targeting `fetch_live_flights`, then re-run the demo.
`fetch_live_flights` flips from `allowed_executed` to `denied_blocked` with
reason code `kill_switch` — the app was not restarted and its code did not change.

The same switch can be pre-declared in `governance.yaml`; it ships disabled:

```yaml
kill_switches:
  - id: disable_live_airspace
    enabled: false
    target_capabilities: [fetch_live_flights]
```

A manifest kill switch is evaluated locally, so it works with no backend at all.
A dashboard kill switch needs `--api`, because it is toggled after the app started.

## What it writes

| File | Contents |
|---|---|
| `events.jsonl` | Evidence events: `tool_start` / `tool_end` / `tool_error`, plus `action_decision` in shadow and enforce modes |
| `actions.jsonl` | Action records: request metadata, decision, execution status, evidence hash |

Neither file contains raw argument values. An action record carries only
`arguments_hash`, `argument_names`, `argument_types` and — on a pattern
denial — the id of the pattern that matched. The SQL text that triggered the
deny is inspected in-process and discarded. Verify it:

```powershell
findstr /C:"DROP TABLE" actions.jsonl   # no matches
```

## Writing deny patterns

`denied_argument_patterns` is matched against live argument values before
anything is persisted. Write the regex in **single** quotes — a double-quoted
YAML scalar turns `\b` into a literal backspace, and the SDK rejects such a
pattern rather than letting a rule silently never fire:

```yaml
denied_argument_patterns:
  - id: destructive_sql
    pattern: '(?i)\b(drop|delete|truncate|alter)\b'
```

This is a coarse guard, not a SQL parser. It is a demonstration of
argument-level policy, not a complete injection defence.
