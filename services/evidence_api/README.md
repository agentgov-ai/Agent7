# Evidence Ingestion API

Minimal FastAPI service for the restaurant-agent governance evidence PoC.

## Run

```powershell
C:\Users\shrey\anaconda4\python.exe -m uvicorn services.evidence_api.app:app --host 127.0.0.1 --port 8000
```

## Demo Reset

```powershell
conda run python scripts\run_demo_reset.py
Invoke-WebRequest -Uri http://127.0.0.1:8000/findings
Invoke-WebRequest -Uri http://127.0.0.1:8000/systems
Invoke-WebRequest -Uri http://127.0.0.1:8000/systems/restaurant-agent/acap
```

The demo reset source is `examples/demo-data`. It replays stable JSONL
fixtures for the restaurant, refund, custom Python, OpenAI direct, Anthropic
direct, and FastAPI middleware demos.

The lower-level replay endpoint still defaults to
`artifacts/governance/events.jsonl`:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/evidence/replay-jsonl -Method Post -ContentType application/json -Body '{"reset":true}'
Invoke-WebRequest -Uri http://127.0.0.1:8000/rules/run -Method Post -ContentType application/json -Body '{"rule_ids":["R1_confirm_without_proposal"]}'
```

## Live Agent Ingestion

With the API running, the restaurant agent can POST each newly emitted
governance event while still appending the same event to local JSONL:

```powershell
$env:GOVERNANCE_EVIDENCE="1"
$env:GOVERNANCE_API_ENDPOINT="http://127.0.0.1:8000/evidence/events"
python Restaurant_agent1.py
```

After a live run, verify ingestion and rerun R1:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/health
Invoke-WebRequest -Uri http://127.0.0.1:8000/rules/run -Method Post -ContentType application/json -Body '{"rule_ids":["R1_confirm_without_proposal"]}'
Invoke-WebRequest -Uri http://127.0.0.1:8000/findings
```

## Scope

This service only ingests validated governance events, stores them in SQLite,
replays local JSONL, runs `R1_confirm_without_proposal`, exposes findings, and
serves a minimal read-only system/ACAP registry from the reviewed ACAP artifact.
It intentionally does not add a dashboard, OPA, Kafka, auth, multi-tenancy,
LangSmith, or framework mapping.
