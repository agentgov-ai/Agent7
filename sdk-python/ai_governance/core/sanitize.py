from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"(api[_-]?key|secret|password|passwd|token|authorization|cookie|cvv|cvc|card[_-]?number|access[_-]?key)",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
_LONG_DIGITS = re.compile(r"(?<!\d)\d{12,19}(?!\d)")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_string(value: str, max_length: int = 512) -> str:
    value = _EMAIL.sub("<redacted-email>", value)
    value = _PHONE.sub("<redacted-phone>", value)
    value = _LONG_DIGITS.sub("<redacted-number>", value)
    if len(value) > max_length:
        return value[:max_length] + "…<truncated>"
    return value


def sanitize(value: Any, *, depth: int = 0, max_depth: int = 6) -> Any:
    if depth > max_depth:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            clean[key_text] = "<redacted>" if _SENSITIVE_KEY.search(key_text) else sanitize(
                item, depth=depth + 1, max_depth=max_depth
            )
        return clean
    if isinstance(value, (list, tuple, set)):
        return [sanitize(item, depth=depth + 1, max_depth=max_depth) for item in list(value)[:100]]
    if hasattr(value, "model_dump"):
        try:
            return sanitize(value.model_dump(), depth=depth + 1, max_depth=max_depth)
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            return sanitize(value.dict(), depth=depth + 1, max_depth=max_depth)
        except Exception:
            pass
    return _sanitize_string(str(value))
