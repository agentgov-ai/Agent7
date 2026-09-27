from __future__ import annotations

REQUIRED_FIELDS = [
    "schema_version",
    "event_id",
    "timestamp",
    "system_id",
    "deployment_id",
    "environment",
    "event_type",
    "trace_id",
    "span_id",
    "source",
    "outcome",
]

EVENT_TYPES = {
    "chain_start",
    "chain_end",
    "chain_error",
    "agent_action",
    "agent_finish",
    "llm_start",
    "llm_end",
    "llm_error",
    "tool_start",
    "tool_end",
    "tool_error",
    "retriever_start",
    "retriever_end",
    "retriever_error",
    "approval_requested",
    "approval_decision",
    "action_decision",
    "custom",
}

OUTCOME_STATUSES = {"started", "success", "error", "unknown"}
ACTION_TYPES = {"read", "write", "communicate", "execute", "unknown", None}
PROMPT_CAPTURE = {"none", "hash", "sanitized", "full"}
