from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "sdk-python"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from ai_governance import GovernanceClient  # noqa: E402
from ai_governance.adapters.fastapi import GovernanceMiddleware  # noqa: E402

OUT = Path(__file__).resolve().parent / "events.jsonl"

gov = GovernanceClient(
    system_id="support-api",
    deployment_id="local-test",
    environment="local",
    session_id="api-demo-session",
    jsonl_path=OUT,
)


@gov.tool(name="refund_execute", action_type="write", approval_required=True, data_classes=["financial"])
def refund_execute(order_id: str, amount_cents: int) -> dict:
    return {"order_id": order_id, "amount_cents": amount_cents, "status": "refunded"}


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        return SimpleNamespace(
            model=kwargs.get("model"),
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3, total_tokens=8),
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="Hello"))],
        )


openai_client = gov.openai_client(client=FakeOpenAIClient())

app = FastAPI()
app.add_middleware(
    GovernanceMiddleware,
    governance_client=gov,
    request_id_header="x-request-id",
    session_header="x-session-id",
    user_header="x-user-id",
)


@app.post("/refund")
def refund_endpoint(payload: dict):
    with gov.trace(name="refund_workflow"):
        result = refund_execute(payload["order_id"], payload["amount_cents"])
    return {"ok": True, "result": result}


@app.post("/chat")
def chat_endpoint():
    openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": "Hello"}],
    )
    return {"ok": True}


@app.get("/boom")
def boom_endpoint():
    raise RuntimeError("demo failure")


def main() -> int:
    if OUT.exists():
        OUT.unlink()
    client = TestClient(app, raise_server_exceptions=False)
    refund = client.post(
        "/refund",
        json={"order_id": "ORD-1001", "amount_cents": 2599},
        headers={"x-request-id": "req-refund-1", "x-session-id": "demo-session", "x-user-id": "demo-user"},
    )
    chat = client.post("/chat", headers={"x-request-id": "req-chat-1"})
    boom = client.get("/boom", headers={"x-request-id": "req-boom-1"})
    print(
        json.dumps(
            {
                "events": str(OUT),
                "refund_status": refund.status_code,
                "chat_status": chat.status_code,
                "boom_status": boom.status_code,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
