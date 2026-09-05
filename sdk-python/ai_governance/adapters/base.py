from __future__ import annotations

from typing import Any, Protocol


class FrameworkAdapter(Protocol):
    """Minimal protocol for framework adapters that install governance hooks."""

    def install(self, target: Any = None) -> Any:
        ...
