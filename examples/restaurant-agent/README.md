# Restaurant Agent Example

This directory contains the restaurant-agent demo that generated the current
governance evidence artifacts.

Run from the repository root:

```powershell
python examples\restaurant-agent\Restaurant_agent1.py
```

The legacy command still works through the root compatibility launcher:

```powershell
python Restaurant_agent1.py
```

The demo writes test orders to `examples/restaurant-agent/orders_log.json`.
When `GOVERNANCE_EVIDENCE=1` is set, governance events are still written to the
shared root artifact directory: `artifacts/governance`.

Optional live API ingestion is enabled by adding `GOVERNANCE_API_ENDPOINT`:

```powershell
$env:GOVERNANCE_EVIDENCE="1"
$env:GOVERNANCE_API_ENDPOINT="http://127.0.0.1:8000/evidence/events"
python Restaurant_agent1.py
```

The API export is best-effort. If the API is down, local JSONL writes continue.
