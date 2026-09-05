from __future__ import annotations

import threading
import time
from typing import Any


class SessionTracker:
    """Trace/span/session bookkeeping independent of any AI framework."""

    def __init__(self, *, default_session_id: str) -> None:
        self.default_session_id = default_session_id
        self._lock = threading.Lock()
        self._trace_for_run: dict[str, str] = {}
        self._session_for_run: dict[str, str] = {}
        self._started: dict[str, float] = {}
        self._component_names: dict[str, str] = {}

    @property
    def trace_for_run(self) -> dict[str, str]:
        return self._trace_for_run

    @property
    def session_for_run(self) -> dict[str, str]:
        return self._session_for_run

    def ids(self, run_id: Any, parent_run_id: Any | None, *, final: bool = False) -> tuple[str, str, str | None]:
        run = str(run_id)
        parent = str(parent_run_id) if parent_run_id else None
        with self._lock:
            trace = self._trace_for_run.get(parent) if parent else None
            trace = trace or self._trace_for_run.get(run) or run
            if final:
                self._trace_for_run.pop(run, None)
            else:
                self._trace_for_run[run] = trace
        return trace, run, parent

    @staticmethod
    def session_candidate(kwargs: dict[str, Any]) -> str | None:
        metadata = kwargs.get("metadata") or {}
        configurable = kwargs.get("configurable") or {}
        for source in (metadata, configurable):
            if not isinstance(source, dict):
                continue
            value = source.get("session_id") or source.get("thread_id")
            if value is not None:
                return str(value)
        return None

    def session_id(self, run_id: Any, parent_run_id: Any | None, kwargs: dict[str, Any], *, final: bool) -> str:
        run = str(run_id)
        parent = str(parent_run_id) if parent_run_id else None
        with self._lock:
            session = (
                self.session_candidate(kwargs)
                or (self._session_for_run.get(parent) if parent else None)
                or self._session_for_run.get(run)
                or self.default_session_id
            )
            if final:
                self._session_for_run.pop(run, None)
            else:
                self._session_for_run[run] = session
        return session

    def start(self, run_id: Any, component_name: str | None = None) -> None:
        with self._lock:
            self._started[str(run_id)] = time.perf_counter()
            if component_name:
                self._component_names[str(run_id)] = component_name

    def duration(self, run_id: Any) -> float | None:
        with self._lock:
            start = self._started.pop(str(run_id), None)
        return None if start is None else round((time.perf_counter() - start) * 1000, 3)

    def name_for(self, run_id: Any, fallback: str | None) -> str | None:
        with self._lock:
            return self._component_names.pop(str(run_id), None) or fallback
