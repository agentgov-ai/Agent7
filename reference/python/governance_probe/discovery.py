from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def _schema_for(tool: Any) -> dict[str, Any] | None:
    schema = getattr(tool, "args_schema", None)
    if schema is None:
        return None
    if hasattr(schema, "model_json_schema"):
        try:
            return schema.model_json_schema()
        except Exception:
            return None
    if hasattr(schema, "schema"):
        try:
            return schema.schema()
        except Exception:
            return None
    return None


def discover_tools(tools: Iterable[Any]) -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    for tool in tools:
        discovered.append(
            {
                "name": getattr(tool, "name", tool.__class__.__name__),
                "description": getattr(tool, "description", None),
                "args_schema": _schema_for(tool),
                "implementation": f"{tool.__class__.__module__}.{tool.__class__.__name__}",
                "proposed_action_type": "unknown",
                "external_side_effect": None,
                "reversible": None,
                "data_classes": [],
                "approval_required": None,
                "authorization": "unresolved",
                "provenance": ["langchain_tool_object"],
            }
        )
    return discovered


def write_tool_discovery(tools: Iterable[Any], path: str | Path) -> list[dict[str, Any]]:
    records = discover_tools(tools)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({"schema_version": "0.1", "tools": records}, indent=2), encoding="utf-8")
    return records
