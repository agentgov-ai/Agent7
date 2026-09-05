from __future__ import annotations

from typing import Any, Protocol


class EventSink(Protocol):
    def emit(self, event: dict[str, Any]) -> Any:
        ...

    def flush(self) -> None:
        ...

    def close(self) -> None:
        ...
