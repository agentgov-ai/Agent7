from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "sdk-python"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from ai_governance import GovernanceClient  # noqa: E402

OUT = Path(__file__).resolve().parent / "events.jsonl"

gov = GovernanceClient(
    system_id="custom-python-refund-agent",
    deployment_id="local-test",
    environment="local",
    agent_id="custom-refund-agent-main",
    session_id="custom-refund-session",
    jsonl_path=OUT,
)


@gov.tool(name="refund_lookup", action_type="read", data_classes=["order"])
def refund_lookup(order_id: str) -> dict:
    return {"order_id": order_id, "eligible": True, "amount_cents": 2599}


@gov.tool(
    name="refund_execute",
    action_type="write",
    approval_required=True,
    data_classes=["financial", "order"],
    external_side_effect=True,
    target="payment_gateway",
)
def refund_execute(order_id: str, amount_cents: int, customer_email: str, api_key: str) -> dict:
    return {
        "refund_id": "rfnd_demo_001",
        "order_id": order_id,
        "amount_cents": amount_cents,
        "customer_email": customer_email,
        "status": "approved",
    }


@gov.tool(
    name="send_email",
    action_type="communicate",
    data_classes=["contact"],
    external_side_effect=True,
    target="email_service",
)
def send_email(customer_email: str, subject: str) -> dict:
    return {"customer_email": customer_email, "subject": subject, "status": "queued"}


def main() -> int:
    if OUT.exists():
        OUT.unlink()
    with gov.trace(name="refund_workflow", session_id="demo-session-001", user_id="demo-user"):
        lookup = refund_lookup(order_id="ORD-1001")
        refund = refund_execute(
            order_id=lookup["order_id"],
            amount_cents=lookup["amount_cents"],
            customer_email="customer@example.com",
            api_key="sk-demo-secret",
        )
        notice = send_email(customer_email="customer@example.com", subject="Refund processed")
    print(json.dumps({"lookup": lookup, "refund": refund, "notice": notice, "events": str(OUT)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
