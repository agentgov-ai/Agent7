"""Compute evidence field coverage from DB-stored governance events.

Adapts governance_probe.coverage_report._field_presence() to work with
events already loaded from the Evidence API database.
"""
from __future__ import annotations

from typing import Any


def compute_field_coverage(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return per-field coverage entries for the governance evidence model.

    Each entry has: field, status, presence (0.0-1.0), and optional note.
    Status is one of: captured, captured_for_new_events, captured_with_annotation,
    annotation_required, partial, missing.
    """
    llm_end = [e for e in events if e["event_type"] == "llm_end"]
    llm_start = [e for e in events if e["event_type"] == "llm_start"]
    tool_start = [e for e in events if e["event_type"] == "tool_start"]
    terminal = [e for e in events if e["event_type"].endswith(("_end", "_error"))]

    def rate(items: list[dict[str, Any]], fn) -> float | None:  # noqa: ANN001
        if not items:
            return None
        return round(sum(1 for i in items if fn(i)) / len(items), 3)

    return [
        {
            "field": "schema_version/event_id/timestamp",
            "status": "captured",
            "presence": rate(events, lambda e: all(k in e for k in ("schema_version", "event_id", "timestamp"))),
        },
        {
            "field": "system_id/deployment_id/environment",
            "status": "captured",
            "presence": rate(events, lambda e: all(e.get(k) for k in ("system_id", "deployment_id", "environment"))),
        },
        {
            "field": "session_id",
            "status": "captured_for_new_events",
            "presence": rate(events, lambda e: bool(e.get("session_id"))),
            "note": "historical scenario events may predate first-class session_id",
        },
        {
            "field": "trace_id/span_id/parent link",
            "status": "captured",
            "presence": rate(events, lambda e: bool(e.get("trace_id") and e.get("span_id"))),
        },
        {
            "field": "event_type + component kind/name",
            "status": "captured",
            "presence": rate(events, lambda e: bool(e.get("event_type") and (e.get("component") or {}).get("kind"))),
        },
        {
            "field": "model provider/name",
            "status": "captured",
            "presence": rate(
                llm_start + llm_end,
                lambda e: bool((e.get("model") or {}).get("name") and (e.get("model") or {}).get("provider")),
            ),
        },
        {
            "field": "prompt template_hash / message shape",
            "status": "captured",
            "presence": rate(llm_start, lambda e: bool((e.get("prompt") or {}).get("template_hash"))),
        },
        {
            "field": "prompt template_id",
            "status": "annotation_required",
            "presence": rate(llm_start, lambda e: (e.get("prompt") or {}).get("template_id") is not None),
            "note": "no template registry exists; hash only",
        },
        {
            "field": "tool name + action classification",
            "status": "captured_with_annotation",
            "presence": rate(
                tool_start,
                lambda e: (e.get("tool") or {}).get("action_type") not in (None, "unknown"),
            ),
            "note": "action_type from governance-tool-overrides.yaml",
        },
        {
            "field": "tool sanitized arguments + outcome",
            "status": "captured",
            "presence": rate(tool_start, lambda e: "sanitized_arguments" in (e.get("tool") or {})),
        },
        {
            "field": "retrieval source identifiers",
            "status": "missing",
            "presence": 0.0,
            "note": "FAISS similarity_search is called inside get_menu/show_receipt, not via a retriever run",
        },
        {
            "field": "agent identity",
            "status": "captured",
            "presence": rate(events, lambda e: bool((e.get("actor") or {}).get("agent_id"))),
        },
        {
            "field": "approval required/granted",
            "status": "captured_with_annotation",
            "presence": rate(
                [e for e in tool_start if (e.get("approval") or {}).get("required") is not None],
                lambda e: (e.get("approval") or {}).get("required") is not None,
            ),
            "note": "approval.required declared in overrides for write tools; approval.granted is not derived from model-supplied arguments",
        },
        {
            "field": "data classification",
            "status": "annotation_required",
            "presence": rate(tool_start, lambda e: bool((e.get("data") or {}).get("classifications"))),
            "note": "from overrides file only",
        },
        {
            "field": "status + duration",
            "status": "captured",
            "presence": rate(terminal, lambda e: (e.get("outcome") or {}).get("duration_ms") is not None),
        },
        {
            "field": "error type on failures",
            "status": "captured",
            "presence": rate(
                [e for e in events if e["event_type"].endswith("_error")],
                lambda e: bool((e.get("outcome") or {}).get("error_type")),
            ),
        },
        {
            "field": "token usage",
            "status": "partial",
            "presence": rate(llm_end, lambda e: (e.get("outcome") or {}).get("total_tokens") is not None),
            "note": "depends on provider returning usage metadata",
        },
    ]
