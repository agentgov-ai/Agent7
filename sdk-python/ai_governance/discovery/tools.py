from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Iterable

from ai_governance.core import fingerprint, utc_now


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


def _tool_name(tool: Any) -> str:
    name = getattr(tool, "name", None)
    if isinstance(name, str) and name:
        return name
    name = getattr(tool, "__name__", None)
    if isinstance(name, str) and name:
        return name
    return tool.__class__.__name__


def _tool_description(tool: Any) -> str | None:
    description = getattr(tool, "description", None)
    if isinstance(description, str) and description:
        return description
    return inspect.getdoc(tool)


def _implementation(tool: Any) -> str:
    if inspect.isfunction(tool) or inspect.ismethod(tool):
        return f"{tool.__module__}.{tool.__qualname__}"
    return f"{tool.__class__.__module__}.{tool.__class__.__name__}"


def discover_tools(tools: Iterable[Any]) -> list[dict[str, Any]]:
    """Automatic, provenance-tagged tool discovery."""
    discovered: list[dict[str, Any]] = []
    for tool in tools:
        description = _tool_description(tool)
        discovered.append(
            {
                "name": _tool_name(tool),
                "description": description,
                "description_hash": fingerprint(description) if description else None,
                "args_schema": _schema_for(tool),
                "implementation": _implementation(tool),
                "proposed_action_type": "unknown",
                "external_side_effect": None,
                "reversible": None,
                "data_classes": [],
                "approval_required": None,
                "authorization": "unresolved",
                "provenance": [
                    "langchain_tool_object" if hasattr(tool, "invoke") else "plain_function",
                ],
            }
        )
    return discovered


def write_tool_discovery(
    tools: Iterable[Any],
    path: str | Path,
    *,
    system_prompt: str | None = None,
    model: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    records = discover_tools(tools)
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "generated_at": utc_now(),
        "tools": records,
    }
    if system_prompt is not None:
        payload["prompt"] = {
            "template_id": "system_prompt",
            "template_hash": fingerprint(system_prompt),
            "length_chars": len(system_prompt),
            "content_capture": "hash",
        }
    if model:
        payload["model"] = model
    if extra:
        payload.update(extra)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return records
