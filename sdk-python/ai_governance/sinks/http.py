from __future__ import annotations

import json
from typing import Any, Callable
from urllib.request import Request, urlopen


class HttpSink:
    """Best-effort HTTP exporter for already-sanitized governance events."""

    def __init__(
        self,
        endpoint: str,
        *,
        timeout_seconds: float = 0.5,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        endpoint = endpoint.strip()
        if not endpoint:
            raise ValueError("endpoint must not be empty")
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self._opener = opener or urlopen

    def emit(self, event: dict[str, Any]) -> None:
        body = json.dumps({"event": event}, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        request = Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        response = self._opener(request, timeout=self.timeout_seconds)
        try:
            status = int(getattr(response, "status", getattr(response, "code", 200)))
            if status >= 400:
                raise RuntimeError(f"Evidence API returned HTTP {status}")
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None
