# AgentGov: Runbook and Testing

All commands below use Windows PowerShell and absolute paths for this development machine.

## Prerequisites

- Python 3.10+ at `C:\Users\shrey\anaconda4\python.exe`
- Repository at `C:\Users\shrey\Downloads\Restaurant_Agent`

## Start the Evidence API and Dashboard

```powershell
C:\Users\shrey\anaconda4\python.exe -m uvicorn services.evidence_api.app:app --host 127.0.0.1 --port 8000 --reload
```

Once running, open these links:

| URL | What |
|-----|------|
| http://127.0.0.1:8000/ui/ | Governance dashboard |
| http://127.0.0.1:8000/product/ | Product website |
| http://127.0.0.1:8000/docs | FastAPI auto-generated API docs |

## Install the SDK Locally

```powershell
C:\Users\shrey\anaconda4\python.exe -m pip install -e .\sdk-python
```

This installs `agent-governance-sdk` in editable mode and registers the `agent-governance` CLI command.

## Scan a Codebase

```powershell
C:\Users\shrey\anaconda4\python.exe -m ai_governance scan examples\scanner-demo-app --system-id scanner-demo-real --output governance-discovery.json
```

This runs the local deterministic scanner (AST-based, no AI/LLM calls) against the demo app and writes `governance-discovery.json` to the current directory.

## Upload Discovery to the Platform

```powershell
C:\Users\shrey\anaconda4\python.exe -m ai_governance upload-discovery governance-discovery.json --api http://127.0.0.1:8000
```

The system is auto-registered if it does not already exist. Only capability metadata is uploaded, not source code.

## Dashboard Walkthrough

After uploading discovery:

1. Open http://127.0.0.1:8000/ui/
2. Select **scanner-demo-real** from the system dropdown.
3. Go to the **Discovery** tab — review candidate capabilities.
4. For each candidate, click **Approve**, **Reject**, **Edit**, or **Not a capability**.
5. Go to the **ACAP** tab — click **Generate ACAP** to create an immutable ACAP version.
6. Click **Download governance.yaml** to export the manifest.
7. Click **Run ACAP Rules** to compare runtime evidence against the ACAP.
8. Go to the **Findings** tab to see any violations.
9. Go to the **Assessment** tab and run an assessment for a governance summary.

## Run the Full Governance Loop Demo

This script runs the entire workflow in-process (no separate server needed):

```powershell
C:\Users\shrey\anaconda4\python.exe scripts\run_full_governance_loop_demo.py
```

**What it does (8 steps):**

1. Scans `examples/scanner-demo-app` for capabilities.
2. Uploads discovery to an in-process Evidence API.
3. Simulates human review (approves 2 candidates, rejects 1).
4. Generates an ACAP version.
5. Downloads the governance manifest.
6. Ingests simulated runtime events (one approved tool, one denied tool).
7. Runs ACAP rules against the events.
8. Prints a summary with findings (e.g., `R_ACAP_denied_observed`, `R_ACAP_approval_required_missing`).

No AI calls are made. No external services are contacted.

## Reset Demo Data

To reload all bundled demo systems (restaurant-agent, refund-agent, etc.) into the database:

```powershell
C:\Users\shrey\anaconda4\python.exe scripts\run_demo_reset.py
```

Or from the dashboard: go to **Settings** tab and click **Reset Demo**.

## Run Tests

```powershell
C:\Users\shrey\anaconda4\python.exe -m unittest discover -v
```

**Expected:** 239 tests across 14 files. All should pass.

### Test Coverage by Area

| File | Tests | What it covers |
|------|-------|----------------|
| `test_evidence_api.py` | 99 | API endpoints, discovery, ACAP, capability review, rules, findings |
| `test_codebase_scanner.py` | 51 | Scanner detection, sink matching, classification, confidence |
| `test_governance_probe.py` | 21 | Probe initialization, event collection |
| `test_manifest_instrumentation.py` | 18 | Manifest parsing, function wrapping, status filtering |
| `test_findings.py` | 10 | Finding creation, severity, rule linkage |
| `test_custom_function_adapter.py` | 8 | Custom function adapter |
| `test_anthropic_adapter.py` | 7 | Anthropic adapter |
| `test_openai_adapter.py` | 6 | OpenAI adapter |
| `test_otel_export.py` | 6 | OpenTelemetry export |
| `test_fastapi_adapter.py` | 5 | FastAPI middleware |
| `test_demo_data.py` | 4 | Demo fixture loading |
| `test_evidence_ui.py` | 2 | UI interactions |
| `test_full_loop_demo.py` | 1 | End-to-end governance loop |
| `test_sdk_layout.py` | 1 | SDK package structure |

## Troubleshooting

### Dashboard is empty after starting the server

The database may have no data loaded. Either:
- Run the demo reset script (see above), or
- Click **Reset Demo** in the Settings tab, or
- Upload a discovery and ingest events manually.

### System not showing in the dropdown

Systems are registered when discovery is uploaded or when demo data is loaded. Make sure you have either:
- Uploaded discovery with `upload-discovery`, or
- Run the demo reset script.

### Upload not working

- Confirm the server is running on `http://127.0.0.1:8000`.
- Check that `governance-discovery.json` exists and is valid JSON.
- Check the terminal running uvicorn for error messages.

### No runtime evidence showing

Runtime evidence requires either:
- An instrumented backend actively sending events via the SDK, or
- Replayed JSONL data via `POST /evidence/replay-jsonl`, or
- Demo data loaded via reset.

The scanner does not produce runtime evidence — it only produces discovery metadata.

### ACAP rules button is disabled

ACAP rules require at least one ACAP version to exist. Generate an ACAP first:
1. Go to Discovery tab, review candidates.
2. Go to ACAP tab, click Generate ACAP.
3. The Run ACAP Rules button should now be enabled.

### governance.yaml not generated

The governance manifest is only available after an ACAP version exists. Generate an ACAP version first, then download the manifest from the ACAP tab.

### No findings showing

Findings are generated by running rules. Check that:
- Runtime events exist for the selected system.
- An ACAP version exists (for ACAP rules).
- You have clicked **Run ACAP Rules** in the ACAP tab or triggered rules via the API.
- If using pre-ACAP rules (restaurant-agent), events must contain the specific patterns those rules check for.

## Quick Verification Checklist

After a fresh setup, verify end-to-end in this order:

1. Start the server.
2. Run the full governance loop demo script.
3. Open http://127.0.0.1:8000/ui/ and select **scanner-demo-real**.
4. Confirm Discovery tab shows candidates.
5. Confirm ACAP tab shows a version.
6. Confirm Findings tab shows findings.
7. Run the test suite — expect 239 passing.
