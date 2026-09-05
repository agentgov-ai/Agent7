from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Name-based heuristic patterns
# ---------------------------------------------------------------------------

_HIGH_RISK_NAMES = re.compile(
    r"refund|payment|charge|billing|delete|destroy|drop|truncate",
    re.IGNORECASE,
)
_MEDIUM_RISK_NAMES = re.compile(
    r"send|email|notify|upload|publish|update|write|remove|create_order|place_order",
    re.IGNORECASE,
)
_SENSITIVE_PARAMS = re.compile(
    r"card|cvv|ssn|password|secret|amount|recipient|account_number|routing_number",
    re.IGNORECASE,
)

# HTTP methods that imply a write / delete action
_WRITE_HTTP_METHODS = frozenset({"post", "put", "patch"})
_DELETE_HTTP_METHODS = frozenset({"delete"})


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_candidate(
    *,
    function_name: str,
    param_names: list[str],
    sinks_found: list[dict[str, Any]],
    decorator_meta: dict[str, Any] | None,
    route_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    """Determine action_type, risk, data_classes, approval, confidence, etc.

    Returns a dict with keys:
        suggested_action_type, suggested_data_classes,
        suggested_approval_required, external_side_effect,
        risk, confidence, confidence_source
    """
    signals: list[tuple[float, str]] = []  # (confidence, source)

    # --- sink evidence (strongest) ---
    if sinks_found:
        signals.append((0.90, "sink_reachability"))

    # --- existing @gov.tool decorator ---
    if decorator_meta:
        signals.append((0.85, "existing_decorator"))

    # --- FastAPI route ---
    if route_meta:
        signals.append((0.70, "route_and_name"))

    # --- name heuristic ---
    if _HIGH_RISK_NAMES.search(function_name) or _MEDIUM_RISK_NAMES.search(function_name):
        signals.append((0.50, "name_heuristic"))
    elif any(_SENSITIVE_PARAMS.search(p) for p in param_names):
        signals.append((0.50, "name_heuristic"))

    if not signals:
        return {}  # not a candidate

    # pick highest confidence source, +0.05 per additional signal (cap 0.95)
    signals.sort(key=lambda s: s[0], reverse=True)
    base_conf, best_source = signals[0]
    extra = min(len(signals) - 1, 2) * 0.05  # at most +0.10
    confidence = min(base_conf + extra, 0.95)

    # derive fields from sink evidence first, then decorator, then route, then name
    action_type = _action_type(sinks_found, decorator_meta, route_meta, function_name)
    data_classes = _data_classes(sinks_found, decorator_meta)
    risk = _risk(sinks_found, function_name)
    approval = _approval(sinks_found, decorator_meta)
    side_effect = _side_effect(sinks_found, decorator_meta, route_meta)

    return {
        "suggested_action_type": action_type,
        "suggested_data_classes": data_classes,
        "suggested_approval_required": approval,
        "external_side_effect": side_effect,
        "risk": risk,
        "confidence": confidence,
        "confidence_source": best_source,
    }


# ---------------------------------------------------------------------------
# Field derivation helpers
# ---------------------------------------------------------------------------

_ACTION_PRIORITY = {"delete": 4, "write": 3, "communicate": 2, "execute": 1, "read": 0}


def _action_type(
    sinks: list[dict[str, Any]],
    decorator: dict[str, Any] | None,
    route: dict[str, Any] | None,
    name: str,
) -> str:
    if sinks:
        best = max(sinks, key=lambda s: _ACTION_PRIORITY.get(s.get("action_type", ""), -1))
        return best.get("action_type", "unknown")
    if decorator and decorator.get("action_type"):
        return decorator["action_type"]
    if route:
        method = (route.get("method") or "").lower()
        if method in _DELETE_HTTP_METHODS:
            return "delete"
        if method in _WRITE_HTTP_METHODS:
            return "write"
        return "read"
    if _HIGH_RISK_NAMES.search(name):
        if re.search(r"delete|destroy|drop|truncate", name, re.IGNORECASE):
            return "delete"
        return "write"
    if _MEDIUM_RISK_NAMES.search(name):
        if re.search(r"send|email|notify", name, re.IGNORECASE):
            return "communicate"
        return "write"
    return "unknown"


def _data_classes(
    sinks: list[dict[str, Any]],
    decorator: dict[str, Any] | None,
) -> list[str]:
    classes: set[str] = set()
    for s in sinks:
        classes.update(s.get("data_classes", []))
    if decorator:
        classes.update(decorator.get("data_classes", []))
    return sorted(classes)


def _risk(sinks: list[dict[str, Any]], name: str) -> str:
    _RANK = {"high": 3, "medium": 2, "low": 1}
    if sinks:
        return max(sinks, key=lambda s: _RANK.get(s.get("risk", "low"), 0)).get("risk", "medium")
    if _HIGH_RISK_NAMES.search(name):
        return "high"
    if _MEDIUM_RISK_NAMES.search(name):
        return "medium"
    return "low"


def _approval(sinks: list[dict[str, Any]], decorator: dict[str, Any] | None) -> bool:
    if any(s.get("approval_required") for s in sinks):
        return True
    if decorator and decorator.get("approval_required"):
        return True
    return False


def _side_effect(
    sinks: list[dict[str, Any]],
    decorator: dict[str, Any] | None,
    route: dict[str, Any] | None,
) -> bool:
    if any(s.get("external_side_effect") for s in sinks):
        return True
    if decorator and decorator.get("external_side_effect"):
        return True
    if route:
        method = (route.get("method") or "").lower()
        if method in (_WRITE_HTTP_METHODS | _DELETE_HTTP_METHODS):
            return True
    return False
