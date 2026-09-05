# AI Governance Python SDK

Reusable governance evidence instrumentation lives in `ai_governance`.

The root `governance_probe` package is a source-tree PoC compatibility shim and
is not part of the published SDK wheel.

## Local Install

From the repository root:

```powershell
python -m pip install -e ./sdk-python
```

Optional integrations are installed with extras:

```powershell
python -m pip install -e "./sdk-python[openai]"
python -m pip install -e "./sdk-python[anthropic]"
python -m pip install -e "./sdk-python[fastapi]"
python -m pip install -e "./sdk-python[all]"
```

Generic SDK primitives are now available from the reusable package layout:

```python
from ai_governance.core import EventBuilder, SessionTracker, fingerprint, sanitize, validate_event
from ai_governance.sinks import HttpSink, JsonlSink
from ai_governance.discovery import discover_tools, write_tool_discovery
from ai_governance import GovernanceClient
```

Optional LangChain callback support remains available when `langchain-core` is
installed:

```python
from ai_governance import GovernanceCallback, GovernanceEventWriter
```

`GovernanceEventWriter` always writes local JSONL first. When
`GOVERNANCE_API_ENDPOINT` is set through `init_governance`, the same finalized
event record is also POSTed to the Evidence API as `{"event": ...}` on a
best-effort, fail-open path.

Custom Python functions can emit governance evidence without LangChain:

```python
gov = GovernanceClient(system_id="custom-refund-agent", jsonl_path="events.jsonl")

@gov.tool(name="refund_execute", action_type="write", approval_required=True)
def refund_execute(order_id: str, amount_cents: int) -> dict:
    return {"refund_id": "rfnd_001", "order_id": order_id}

with gov.trace(name="refund_workflow", session_id="demo-session-001", user_id="demo-user"):
    refund_execute("ORD-1001", 2599)
```

Direct SDK wrappers are optional and instance-scoped:

```python
openai_client = gov.openai_client()
anthropic_client = gov.anthropic_client()
```
