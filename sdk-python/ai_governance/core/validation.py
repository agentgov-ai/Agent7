from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from .schema import ACTION_TYPES, EVENT_TYPES, OUTCOME_STATUSES, PROMPT_CAPTURE, REQUIRED_FIELDS

RAW_TEXT_PROBES = {
    "system_prompt_text": re.compile(r"restaurant waiter bot", re.IGNORECASE),
    "stdin_order_text": re.compile(r"I want to order", re.IGNORECASE),
    "adversarial_input_text": re.compile(r"ignore (all|previous) instructions", re.IGNORECASE),
    "known_fake_prompt": re.compile(r"SECRET-PROMPT-TEXT", re.IGNORECASE),
    "known_fake_response": re.compile(r"SECRET-RESPONSE-TEXT", re.IGNORECASE),
}


def validate_event(event: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if not isinstance(event, dict):
        return ["event must be a JSON object"]
    for field in REQUIRED_FIELDS:
        if field not in event:
            problems.append(f"missing required field: {field}")
    for field in (
        "event_id",
        "timestamp",
        "system_id",
        "deployment_id",
        "environment",
        "event_type",
        "trace_id",
        "span_id",
    ):
        if field in event and not isinstance(event.get(field), str):
            problems.append(f"{field} must be a string")
        elif field in event and field != "timestamp" and not event.get(field):
            problems.append(f"{field} must not be empty")
    if event.get("event_type") not in EVENT_TYPES:
        problems.append(f"invalid event_type: {event.get('event_type')!r}")
    source = event.get("source")
    if not isinstance(source, dict) or not source.get("type"):
        problems.append("source.type is required")
    outcome = event.get("outcome")
    if not isinstance(outcome, dict) or outcome.get("status") not in OUTCOME_STATUSES:
        problems.append("outcome.status is invalid or missing")
    tool = event.get("tool")
    if isinstance(tool, dict) and tool.get("action_type") not in ACTION_TYPES:
        problems.append(f"invalid tool.action_type: {tool.get('action_type')!r}")
    prompt = event.get("prompt")
    if isinstance(prompt, dict):
        capture = prompt.get("content_capture")
        if capture not in PROMPT_CAPTURE:
            problems.append(f"invalid prompt.content_capture: {capture!r}")
        if capture in {"full", "sanitized"}:
            problems.append(f"prompt.content_capture={capture} violates privacy policy")
    if event.get("timestamp"):
        try:
            parsed = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                problems.append("timestamp must include timezone")
        except Exception:
            problems.append(f"timestamp is not ISO datetime: {event.get('timestamp')!r}")
    problems.extend(raw_text_problems(event))
    return problems


def raw_text_problems(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return [f"raw text probe matched: {name}" for name, pattern in RAW_TEXT_PROBES.items() if pattern.search(text)]


def public_event(event: dict[str, Any]) -> dict[str, Any]:
    """Return an API-safe event projection."""
    cleaned = json.loads(json.dumps(event, ensure_ascii=False, default=str))
    tool = cleaned.get("tool")
    if isinstance(tool, dict) and "sanitized_arguments" in tool:
        tool.pop("sanitized_arguments", None)
        tool["arguments_exposed"] = False
    attrs = cleaned.get("attributes")
    if isinstance(attrs, dict) and "result_summary" in attrs:
        attrs.pop("result_summary", None)
        attrs["summary_exposed"] = False
    return cleaned
