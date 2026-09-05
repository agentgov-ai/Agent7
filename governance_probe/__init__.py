"""Compatibility imports for the original PoC package name.

Reusable instrumentation now lives in `sdk-python/ai_governance`. This package
keeps existing `governance_probe` imports working for the restaurant PoC.
"""
from __future__ import annotations

from ._compat import ensure_sdk_path

ensure_sdk_path()

from ai_governance import (  # noqa: E402
    GovernanceCallback,
    GovernanceEventWriter,
    discover_tools,
    fingerprint,
    sanitize,
    write_tool_discovery,
)

__all__ = [
    "GovernanceCallback",
    "GovernanceEventWriter",
    "discover_tools",
    "write_tool_discovery",
    "fingerprint",
    "sanitize",
]
