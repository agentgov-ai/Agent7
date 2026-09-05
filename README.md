# AI Governance Restaurant Agent PoC

This repository now separates reusable governance evidence code from the
restaurant-agent demo.

## Layout

- `sdk-python/ai_governance` - reusable Python governance instrumentation.
- `schemas/governance-event.schema.json` - shared governance-event contract.
- `services/evidence_api` - minimal Evidence API and evidence review UI.
- `examples/restaurant-agent` - runnable restaurant ordering demo and local test order log.
- `examples/demo-data` - stable JSONL and reviewed ACAP fixtures for local demos.
- `artifacts/governance` - recorded PoC evidence, reviewed ACAP, findings, and replay manifest.

## Run The Demo

```powershell
python examples\restaurant-agent\Restaurant_agent1.py
```

The root `Restaurant_agent1.py` remains as a compatibility launcher.

## Evidence API

```powershell
python -m uvicorn services.evidence_api.app:app --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000/ui/`.

Reset the demo database from stable seed data:

```powershell
conda run python scripts\run_demo_reset.py
```

The reset loads all bundled demo systems:

- `restaurant-agent`
- `customer-refund-agent`
- `custom-python-refund-agent`
- `openai-direct-agent`
- `anthropic-direct-agent`
- `support-api`

For a no-server smoke check, run:

```powershell
conda run python scripts\run_demo_reset.py --in-process
```

To stream new agent evidence into the API while preserving local JSONL:

```powershell
$env:GOVERNANCE_EVIDENCE="1"
$env:GOVERNANCE_API_ENDPOINT="http://127.0.0.1:8000/evidence/events"
python Restaurant_agent1.py
```

If the API is unavailable, the agent continues and local
`artifacts/governance/events.jsonl` remains the source of truth.
