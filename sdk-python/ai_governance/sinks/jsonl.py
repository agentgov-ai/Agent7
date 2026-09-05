from __future__ import annotations

import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any

from ai_governance.core.sanitize import utc_now
from ai_governance.sinks.http import HttpSink

logger = logging.getLogger(__name__)


class JsonlSink:
    """Append-only local JSONL writer for governance evidence."""

    def __init__(
        self,
        path: str | Path,
        *,
        api_endpoint: str | None = None,
        api_timeout_seconds: float = 0.5,
        api_sink: HttpSink | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.api_sink = api_sink or (HttpSink(api_endpoint, timeout_seconds=api_timeout_seconds) if api_endpoint else None)
        self.api_dropped_events = 0

    def emit(self, event: dict[str, Any]) -> dict[str, Any]:
        record = {
            "schema_version": "0.1",
            "event_id": event.get("event_id") or str(uuid.uuid4()),
            "timestamp": event.get("timestamp") or utc_now(),
            **event,
        }
        line = json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        if self.api_sink is not None:
            try:
                self.api_sink.emit(record)
            except Exception:
                self.api_dropped_events += 1
                logger.warning("governance API export failed; continuing with local JSONL", exc_info=True)
        return record

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None
