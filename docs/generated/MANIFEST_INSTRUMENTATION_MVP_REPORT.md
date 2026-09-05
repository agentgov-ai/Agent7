# Manifest-Based Instrumentation MVP Report

**Date:** 2026-08-29
**Milestone:** Manifest-Based Instrumentation

## Purpose

Allow reviewed capabilities to be instrumented from a `governance.yaml` manifest so users do not need to manually decorate every function. Functions declared as approved in the manifest are dynamically wrapped at startup to emit governance events.

**Usage:**
```python
from ai_governance import GovernanceClient
gov = GovernanceClient.from_config("governance.yaml")
gov.instrument_from_config()
# Now call functions normally — approved ones emit events automatically
```

## How It Works

1. `GovernanceClient.from_config("governance.yaml")` parses the manifest and creates a configured client
2. `gov.instrument_from_config()` iterates capabilities in the manifest:
   - **approved / approved_for_acap / edited** → dynamically imported, wrapped using the existing `gov.tool()` decorator, replaced in the module's namespace
   - **pending / rejected / false_positive** → skipped
3. Wrapped functions emit the same `tool_start` / `tool_end` / `tool_error` events as manual `@gov.tool()` decorators
4. Failed imports or resolution errors are reported but never raise (fail-open)

## Manifest Schema

```yaml
system_id: my-system            # required
deployment_id: local-test       # optional
environment: local              # optional
agent_id: my-agent              # optional
jsonl_path: events.jsonl        # optional
api_endpoint: null              # optional

capabilities:
  - name: refund_execute        # required
    module_path: app.payments.refund_execute  # required (dotted path)
    action_type: write          # optional
    approval_required: true     # optional
    data_classes: [financial]   # optional
    external_side_effect: true  # optional
    status: approved            # required (approved|pending|rejected|false_positive)
```

## Instrumentation Status Values

| Status | Meaning |
|--------|---------|
| `wrapped` | Function successfully instrumented |
| `skipped_not_approved` | Status is not approved/approved_for_acap/edited |
| `failed_import` | Module could not be imported |
| `missing_attribute` | Module imported but function not found |
| `unsupported_target` | Target exists but is not callable |
| `already_wrapped` | Function already has governance wrapper (prevents double-wrapping) |

## Double-Wrap Prevention

A marker attribute `__ai_governance_wrapped__` is set on wrapped functions. If `instrument_from_config()` is called twice, already-wrapped functions are skipped with `already_wrapped` status.

## Known Limitations

- **Import order dependency:** If another module imports a function via `from app.payments import refund_execute` before `instrument_from_config()` runs, that local reference will not be replaced. The function must be called through the module attribute (e.g., `app.payments.refund_execute()`) for the wrapper to be active.
- **Python functions only:** Class methods, static methods, and property descriptors are not supported in this MVP.
- **No source code modification:** This is runtime monkey-patching only — the original source files are never changed.

## PyYAML Dependency

PyYAML remains optional. If not installed, `from_config()` raises a clear error:
> "Install agent-governance-sdk[acap] or PyYAML to use governance.yaml manifests."

## Files

| File | Purpose |
|------|---------|
| `sdk-python/ai_governance/manifest.py` | YAML parser, function resolver, module replacement |
| `sdk-python/ai_governance/client.py` | `from_config()` classmethod + `instrument_from_config()` method |
| `examples/manifest-instrumentation/` | Demo app + governance.yaml + run script |
| `tests/test_manifest_instrumentation.py` | 18 tests |

## Test Coverage

18 tests across 3 classes:
- `TestLoadManifest` (5 tests) — valid parsing, missing required fields
- `TestFromConfig` (2 tests) — client creation, jsonl_path override
- `TestInstrumentFromConfig` (11 tests) — wrap approved, skip pending/rejected/false_positive, event emission (start+end), error emission (start+error), failed import, unsupported target, double-wrap prevention, manual decorator compatibility, approved_for_acap status

Total suite: 215 tests, all passing.

## What This Does NOT Do

- Rewrite source code or codemods
- Block runtime execution
- Call AI/LLM
- Change event schema
- Break existing `@gov.tool()` usage
- Add new required dependencies
