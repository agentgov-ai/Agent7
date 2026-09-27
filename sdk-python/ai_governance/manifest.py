"""Governance manifest parser and dynamic function resolution."""
from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Instrumentation status constants
STATUS_WRAPPED = "wrapped"
STATUS_FAILED_IMPORT = "failed_import"
STATUS_MISSING_ATTRIBUTE = "missing_attribute"
STATUS_UNSUPPORTED_TARGET = "unsupported_target"
STATUS_SKIPPED_NOT_APPROVED = "skipped_not_approved"
STATUS_ALREADY_WRAPPED = "already_wrapped"
STATUS_WRAPPED_FOR_ENFORCEMENT = "wrapped_for_enforcement"

# Statuses that permit instrumentation
_APPROVED_STATUSES = frozenset({"approved", "approved_for_acap", "edited"})

# Statuses a human explicitly refused. These are wrapped only in shadow/enforce
# mode, so that Agent7 can block them before execution. In observe mode they
# stay skipped, preserving historical behaviour.
_DENIED_STATUSES = frozenset({"denied", "rejected"})

# Never wrapped: the scanner or a reviewer said these are not real capabilities.
_NEVER_WRAP_STATUSES = frozenset({"false_positive", "not_a_capability"})

# Marker attribute set on wrapped functions to prevent double-wrapping
WRAPPED_MARKER = "__ai_governance_wrapped__"


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Parse a ``governance.yaml`` manifest and validate required fields.

    Raises ``SystemExit`` if PyYAML is not installed.
    Raises ``ValueError`` on missing required fields.
    """
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SystemExit(
            "Install agent-governance-sdk[acap] or PyYAML to use "
            "governance.yaml manifests."
        ) from exc

    text = Path(path).read_text(encoding="utf-8")
    config: dict[str, Any] = yaml.safe_load(text) or {}

    if not config.get("system_id"):
        raise ValueError("governance manifest must contain 'system_id'")
    capabilities = config.get("capabilities")
    if not isinstance(capabilities, list):
        raise ValueError("governance manifest must contain a 'capabilities' list")

    for i, cap in enumerate(capabilities):
        if not cap.get("name"):
            raise ValueError(f"capability {i} must have a 'name'")
        if not cap.get("module_path"):
            raise ValueError(f"capability '{cap.get('name', i)}' must have a 'module_path'")
        if not cap.get("status"):
            raise ValueError(f"capability '{cap['name']}' must have a 'status'")

    _validate_enforcement(config)
    return config


def _validate_enforcement(config: dict[str, Any]) -> None:
    """Validate the optional enforcement_mode and kill_switches blocks."""
    from ai_governance.core.actions import ENFORCEMENT_MODES

    mode = config.get("enforcement_mode")
    if mode is not None and str(mode).strip().lower() not in ENFORCEMENT_MODES:
        raise ValueError(
            f"enforcement_mode must be one of {sorted(ENFORCEMENT_MODES)}, got {mode!r}"
        )

    switches = config.get("kill_switches")
    if switches is None:
        return
    if not isinstance(switches, list):
        raise ValueError("governance manifest 'kill_switches' must be a list")
    for i, switch in enumerate(switches):
        if not isinstance(switch, dict):
            raise ValueError(f"kill switch {i} must be a mapping")
        if not switch.get("id"):
            raise ValueError(f"kill switch {i} must have an 'id'")
        targets = switch.get("target_capabilities")
        if targets is not None and not isinstance(targets, list):
            raise ValueError(
                f"kill switch '{switch['id']}' target_capabilities must be a list"
            )


def resolve_function(
    module_path: str,
) -> tuple[Any, str, Any, str] | None:
    """Resolve a dotted ``module_path`` to ``(module_obj, attr_name, func, error_hint)``.

    Returns ``None`` with a logged warning on failure.
    The fourth tuple element is always ``""`` on success (used only in error reporting).
    """
    # Split into module + attribute: "app.payments.refund_execute"
    # → module="app.payments", attr="refund_execute"
    dot = module_path.rfind(".")
    if dot < 0:
        logger.warning("module_path '%s' has no dotted module component", module_path)
        return None

    mod_name = module_path[:dot]
    attr_name = module_path[dot + 1:]

    try:
        mod = importlib.import_module(mod_name)
    except Exception as exc:
        logger.warning("Cannot import module '%s': %s", mod_name, exc)
        return None

    func = getattr(mod, attr_name, None)
    if func is None:
        logger.warning("Module '%s' has no attribute '%s'", mod_name, attr_name)
        return None

    return (mod, attr_name, func, "")


def replace_function(module_obj: Any, attr_name: str, wrapped: Any) -> None:
    """Replace a function in its module's namespace."""
    setattr(module_obj, attr_name, wrapped)
