from __future__ import annotations

from typing import Any


def get_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def message_count(messages: Any) -> int:
    return len(messages) if isinstance(messages, list) else 0


def message_roles(messages: Any) -> list[str]:
    if not isinstance(messages, list):
        return []
    roles: set[str] = set()
    for message in messages:
        role = get_value(message, "role", None)
        if role is not None:
            roles.add(str(role))
    return sorted(roles)


def token_usage(value: Any) -> dict[str, Any]:
    usage = get_value(value, "usage", value) or {}
    return {
        "prompt_tokens": get_value(usage, "prompt_tokens", get_value(usage, "input_tokens", None)),
        "completion_tokens": get_value(usage, "completion_tokens", get_value(usage, "output_tokens", None)),
        "total_tokens": get_value(usage, "total_tokens", None),
    }


def finish_reasons(response: Any) -> list[str]:
    reasons: list[str] = []
    for choice in get_value(response, "choices", []) or []:
        reason = get_value(choice, "finish_reason", None)
        if reason is not None:
            reasons.append(str(reason))
    return reasons
