"""Generate mock governance evidence for the customer-refund-agent demo.

Produces events.jsonl with two sessions:
- s1_normal: proper flow (lookup → eligibility check → refund with approval)
- s2_bypass: refund_execute without eligibility check (triggers R_write_no_approval)

Usage: python -m examples.refund-agent.generate_evidence
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent / "events.jsonl"

SYSTEM_ID = "customer-refund-agent"
DEPLOYMENT_ID = "local-test"
ENVIRONMENT = "local"
AGENT_ID = "refund-agent-main"


def _event(
    event_type: str,
    trace_id: str,
    span_id: str | None = None,
    parent_span_id: str | None = None,
    session_id: str = "1",
    component_kind: str = "tool",
    component_name: str = "",
    tool_name: str | None = None,
    action_type: str | None = None,
    status: str = "started",
    duration_ms: float | None = None,
    error_type: str | None = None,
    approval_required: bool | None = None,
    approval_granted: bool | None = None,
    external_side_effect: bool | None = None,
    data_classes: list[str] | None = None,
    target: str | None = None,
    ts: datetime | None = None,
) -> dict:
    span = span_id or str(uuid.uuid4())
    event = {
        "schema_version": "0.1",
        "event_id": str(uuid.uuid4()),
        "timestamp": (ts or datetime.now(timezone.utc)).isoformat(),
        "system_id": SYSTEM_ID,
        "deployment_id": DEPLOYMENT_ID,
        "environment": ENVIRONMENT,
        "session_id": session_id,
        "event_type": event_type,
        "trace_id": trace_id,
        "span_id": span,
        "parent_span_id": parent_span_id,
        "source": {"type": "langchain_callback", "library": "langchain-core", "library_version": "1.2.17"},
        "actor": {"agent_id": AGENT_ID, "identity_type": "logical_agent"},
        "component": {"kind": component_kind, "name": component_name},
        "outcome": {"status": status, "duration_ms": duration_ms, "error_type": error_type},
    }
    if tool_name:
        event["tool"] = {
            "name": tool_name,
            "action_type": action_type,
            "arguments_hash": f"sha256:{uuid.uuid4().hex[:16]}",
            "sanitized_arguments": {"order_id": "ORD-XXXX"},
            "external_side_effect": external_side_effect,
            "target": target,
        }
    if approval_required is not None:
        event["approval"] = {"required": approval_required, "granted": approval_granted}
    if data_classes:
        event["data"] = {"classifications": data_classes}
    return event


def generate() -> list[dict]:
    events = []
    base_time = datetime(2026, 7, 30, 10, 0, 0, tzinfo=timezone.utc)
    t = 0

    def ts():
        nonlocal t
        t += 1
        return base_time + timedelta(seconds=t)

    # ── Session 1: Normal flow (approved refund) ──
    s1_trace = str(uuid.uuid4())
    s1_root = str(uuid.uuid4())

    # Chain start
    events.append(_event("chain_start", s1_trace, s1_root, session_id="s1_normal",
                         component_kind="chain", component_name="AgentExecutor", status="started", ts=ts()))

    # LLM call
    llm_span = str(uuid.uuid4())
    events.append(_event("llm_start", s1_trace, llm_span, s1_root, session_id="s1_normal",
                         component_kind="chat_model", component_name="ChatOpenAI", status="started", ts=ts()))
    events.append(_event("llm_end", s1_trace, llm_span, s1_root, session_id="s1_normal",
                         component_kind="chat_model", component_name="ChatOpenAI", status="success", duration_ms=450, ts=ts()))

    # lookup_order
    span1 = str(uuid.uuid4())
    events.append(_event("tool_start", s1_trace, span1, s1_root, session_id="s1_normal",
                         tool_name="lookup_order", action_type="read", component_name="lookup_order",
                         data_classes=["order"], ts=ts()))
    events.append(_event("tool_end", s1_trace, span1, s1_root, session_id="s1_normal",
                         tool_name="lookup_order", action_type="read", component_name="lookup_order",
                         status="success", duration_ms=120, ts=ts()))

    # check_eligibility
    span2 = str(uuid.uuid4())
    events.append(_event("tool_start", s1_trace, span2, s1_root, session_id="s1_normal",
                         tool_name="check_eligibility", action_type="read", component_name="check_eligibility",
                         data_classes=["order", "policy"], ts=ts()))
    events.append(_event("tool_end", s1_trace, span2, s1_root, session_id="s1_normal",
                         tool_name="check_eligibility", action_type="read", component_name="check_eligibility",
                         status="success", duration_ms=95, ts=ts()))

    # refund_execute (with approval — normal flow)
    span3 = str(uuid.uuid4())
    events.append(_event("tool_start", s1_trace, span3, s1_root, session_id="s1_normal",
                         tool_name="refund_execute", action_type="write", component_name="refund_execute",
                         approval_required=True, approval_granted=True,
                         external_side_effect=True, target="payment_gateway",
                         data_classes=["financial", "order"], ts=ts()))
    events.append(_event("tool_end", s1_trace, span3, s1_root, session_id="s1_normal",
                         tool_name="refund_execute", action_type="write", component_name="refund_execute",
                         status="success", duration_ms=800, ts=ts()))

    # send_notification
    span4 = str(uuid.uuid4())
    events.append(_event("tool_start", s1_trace, span4, s1_root, session_id="s1_normal",
                         tool_name="send_notification", action_type="communicate", component_name="send_notification",
                         data_classes=["contact"], external_side_effect=True, ts=ts()))
    events.append(_event("tool_end", s1_trace, span4, s1_root, session_id="s1_normal",
                         tool_name="send_notification", action_type="communicate", component_name="send_notification",
                         status="success", duration_ms=200, ts=ts()))

    # Chain end
    events.append(_event("chain_end", s1_trace, s1_root, session_id="s1_normal",
                         component_kind="chain", component_name="AgentExecutor",
                         status="success", duration_ms=2100, ts=ts()))

    # ── Session 2: Bypass (refund without eligibility check) ──
    s2_trace = str(uuid.uuid4())
    s2_root = str(uuid.uuid4())

    # Chain start
    events.append(_event("chain_start", s2_trace, s2_root, session_id="s2_bypass",
                         component_kind="chain", component_name="AgentExecutor", status="started", ts=ts()))

    # LLM call
    llm2 = str(uuid.uuid4())
    events.append(_event("llm_start", s2_trace, llm2, s2_root, session_id="s2_bypass",
                         component_kind="chat_model", component_name="ChatOpenAI", status="started", ts=ts()))
    events.append(_event("llm_end", s2_trace, llm2, s2_root, session_id="s2_bypass",
                         component_kind="chat_model", component_name="ChatOpenAI", status="success", duration_ms=380, ts=ts()))

    # refund_execute DIRECTLY — no lookup, no eligibility check, no approval granted
    bypass_span = str(uuid.uuid4())
    events.append(_event("tool_start", s2_trace, bypass_span, s2_root, session_id="s2_bypass",
                         tool_name="refund_execute", action_type="write", component_name="refund_execute",
                         approval_required=True, approval_granted=None,
                         external_side_effect=True, target="payment_gateway",
                         data_classes=["financial", "order"], ts=ts()))
    events.append(_event("tool_end", s2_trace, bypass_span, s2_root, session_id="s2_bypass",
                         tool_name="refund_execute", action_type="write", component_name="refund_execute",
                         status="success", duration_ms=750, ts=ts()))

    # Chain end
    events.append(_event("chain_end", s2_trace, s2_root, session_id="s2_bypass",
                         component_kind="chain", component_name="AgentExecutor",
                         status="success", duration_ms=1500, ts=ts()))

    return events


def main() -> int:
    events = generate()
    OUTPUT.write_text(
        "\n".join(json.dumps(e, sort_keys=True, ensure_ascii=False, default=str) for e in events) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(events)} events to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
