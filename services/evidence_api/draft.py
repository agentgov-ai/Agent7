"""Generate a draft ACAP from discovery, overrides and DB-stored runtime events.

Adapts governance_probe.acap_draft logic to work with events already in the
Evidence API database rather than reading from a JSONL file.

Discovery/observation never implies authorization: every authorization field
is emitted as ``unresolved`` and every auto-filled value carries provenance.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DISCOVERY = REPO_ROOT / "artifacts" / "governance" / "discovery.json"
OVERRIDES = REPO_ROOT / "governance-tool-overrides.yaml"

TOOL_FIELD_NOTES: dict[tuple[str, str], str] = {
    ("place_order", "proposed_action_type"): (
        "closest schema-valid type; function returns an in-session string to the "
        "customer, no external channel"
    ),
    ("confirm_order", "proposed_reversible"): (
        "reversal requires manual staff removal from orders_log.json; no automated "
        "rollback function discovered"
    ),
}

REVIEW_QUESTIONS = [
    {
        "id": "Q1",
        "topic": "intended_purpose",
        "question": "What is this restaurant agent intended to do, and for whom?",
        "fills": ["system.purpose"],
    },
    {
        "id": "Q2",
        "topic": "accountable_owner",
        "question": "Who is the accountable owner for this agent and its order log (name/role)?",
        "fills": ["system.owner"],
    },
    {
        "id": "Q3",
        "topic": "allowed_actions",
        "question": "Which discovered tools are ALLOWED in normal operation?",
        "fills": ["tools[*].authorization"],
    },
    {
        "id": "Q4",
        "topic": "prohibited_actions",
        "question": "Which actions must be PROHIBITED?",
        "fills": ["tools[*].authorization", "prohibited_actions"],
    },
    {
        "id": "Q5",
        "topic": "approval_requirements",
        "question": "Should confirm_order require evidence of a prior place_order proposal AND an explicit customer 'yes' turn?",
        "fills": ["tools[confirm_order].approval"],
    },
    {
        "id": "Q6",
        "topic": "sensitive_data",
        "question": "Which customer data may the agent process or store?",
        "fills": ["data_policy"],
    },
    {
        "id": "Q7",
        "topic": "reassessment_triggers",
        "question": "What business changes require reassessment?",
        "fills": ["reassess_when"],
    },
]


def _observed_tool_stats(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for e in events:
        if e.get("component", {}).get("kind") != "tool":
            continue
        name = e["component"]["name"]
        entry = stats.setdefault(
            name,
            {"starts": 0, "successes": 0, "errors": 0,
             "error_types": Counter(), "evidence_fields": set()},
        )
        if e["event_type"] == "tool_start":
            entry["starts"] += 1
            tool = e.get("tool") or {}
            for field, present in (
                ("sanitized_arguments", "sanitized_arguments" in tool),
                ("arguments_hash", bool(tool.get("arguments_hash"))),
                ("action_type", tool.get("action_type") not in (None, "unknown")),
                ("approval.required", (e.get("approval") or {}).get("required") is not None),
                ("approval.granted_legacy_untrusted", (e.get("approval") or {}).get("granted") is not None),
                ("data.classifications", bool((e.get("data") or {}).get("classifications"))),
            ):
                if present:
                    entry["evidence_fields"].add(field)
        elif e["event_type"] == "tool_end":
            entry["successes"] += 1
            attrs = e.get("attributes") or {}
            if "result_summary" in attrs:
                entry["evidence_fields"].add("result_summary")
            if "result_hash" in attrs:
                entry["evidence_fields"].add("result_hash")
            if (e.get("outcome") or {}).get("duration_ms") is not None:
                entry["evidence_fields"].add("duration_ms")
        elif e["event_type"] == "tool_error":
            entry["errors"] += 1
            error_type = (e.get("outcome") or {}).get("error_type")
            if error_type:
                entry["error_types"][error_type] += 1
                entry["evidence_fields"].add("error_type")
    return stats


def build_draft_from_db_events(
    events: list[dict[str, Any]],
    system_id: str,
) -> dict[str, Any]:
    """Build a draft ACAP from discovery, overrides and DB events.

    All authorization fields are ``"unresolved"`` — discovery and runtime
    observation never imply authorization.
    """
    if not DISCOVERY.exists():
        return {"error": "discovery.json not found", "status": "draft"}
    discovery = json.loads(DISCOVERY.read_text(encoding="utf-8"))
    overrides: dict[str, Any] = {}
    if OVERRIDES.exists():
        overrides = (yaml.safe_load(OVERRIDES.read_text(encoding="utf-8")) or {}).get("tools", {})

    stats = _observed_tool_stats(events)

    observed_models = sorted(
        {(e.get("model") or {}).get("name")
         for e in events if e["event_type"] in ("llm_start", "llm_end")} - {None}
    )
    observed_shape_hashes = sorted(
        {(e.get("prompt") or {}).get("template_hash")
         for e in events if e["event_type"] == "llm_start"} - {None}
    )

    tools = []
    for t in discovery["tools"]:
        name = t["name"]
        o = overrides.get(name, {})
        observed = stats.get(name)
        approval_meta = o.get("approval") or {}
        entry: dict[str, Any] = {
            "name": name,
            "discovered": True,
            "observed": observed is not None,
            "description_hash": {"value": t["description_hash"], "provenance": "code_discovery"},
            "implementation": {"value": t["implementation"], "provenance": "code_discovery"},
            "args_schema": {
                "value": t["args_schema"], "provenance": "code_discovery",
                "note": None if t["args_schema"] else "plain function; no pydantic args schema attached",
            },
            "proposed_action_type": {
                "value": o.get("action_type", "unknown"),
                "provenance": "tool_override" if "action_type" in o else "code_discovery",
                **({"note": TOOL_FIELD_NOTES[(name, "proposed_action_type")]}
                   if (name, "proposed_action_type") in TOOL_FIELD_NOTES else {}),
            },
            "proposed_external_side_effect": {
                "value": o.get("external_side_effect"),
                "provenance": "tool_override" if "external_side_effect" in o else "unresolved",
            },
            "proposed_reversible": {
                "value": o.get("reversible"),
                "provenance": "tool_override" if "reversible" in o else "unresolved",
                **({"note": TOOL_FIELD_NOTES[(name, "proposed_reversible")]}
                   if (name, "proposed_reversible") in TOOL_FIELD_NOTES else {}),
            },
            "proposed_data_classes": {
                "value": o.get("data_classes", []),
                "provenance": "tool_override" if "data_classes" in o else "unresolved",
            },
            "proposed_target": {
                "value": o.get("target"),
                "provenance": "tool_override" if "target" in o else "unresolved",
            },
            "authorization": "unresolved",
            "approval": {
                "required": {
                    "value": approval_meta.get("required", "unresolved"),
                    "provenance": "tool_override" if approval_meta else "unresolved",
                },
                "condition": approval_meta.get("condition"),
                "note": (
                    "approval.required is annotation-only; approval.granted is not derived "
                    "from model-supplied tool arguments. Trusted approval must be established "
                    "structurally by the reviewed ACAP and findings rules"
                ) if approval_meta else None,
            },
            "observed_usage": (
                {
                    "provenance": "runtime_event",
                    "starts": observed["starts"],
                    "successes": observed["successes"],
                    "errors": observed["errors"],
                    "error_types": dict(observed["error_types"]),
                } if observed else {
                    "provenance": "runtime_event",
                    "note": "not observed in any recorded run",
                }
            ),
            "evidence_fields_available": sorted(observed["evidence_fields"]) if observed else [],
        }
        tools.append(entry)

    return {
        "schema_version": "0.1",
        "acap_id": f"{system_id}-local-draft",
        "status": "draft",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation_inputs": {
            "discovery": str(DISCOVERY.relative_to(REPO_ROOT)),
            "overrides": str(OVERRIDES.name),
            "events_source": "evidence_api_database",
            "event_count": len(events),
        },
        "system": {
            "system_id": system_id,
            "deployment_id": "local-test",
            "environment": "local",
            "framework": {
                "value": {k: v for k, v in discovery.get("package_versions", {}).items()},
                "provenance": "code_discovery",
            },
            "purpose": "unresolved",
            "owner": "unresolved",
        },
        "content_policy": {
            "raw_prompts": False,
            "raw_outputs": False,
            "tool_values": "sanitized_summary",
        },
        "agents": [
            {
                "agent_id": discovery.get("agent_id", "restaurant-agent-main"),
                "discovered": True,
                "framework": "langchain.create_agent on LangGraph",
                "authorization": "unresolved",
                "provenance": "code_discovery",
            }
        ],
        "models": [
            {
                "provider": {"value": (discovery.get("model") or {}).get("provider"), "provenance": "code_discovery"},
                "name": {"value": (discovery.get("model") or {}).get("name"), "provenance": "code_discovery"},
                "observed_names": {"value": observed_models, "provenance": "runtime_event"},
                "authorization": "unresolved",
            }
        ],
        "prompts": [
            {
                "template_id": "system_prompt",
                "template_hash": {
                    "value": (discovery.get("prompt") or {}).get("template_hash"),
                    "provenance": "code_discovery",
                },
                "length_chars": (discovery.get("prompt") or {}).get("length_chars"),
                "content_capture": "hash",
            },
            {
                "template_id": "observed_message_shapes",
                "distinct_shape_hashes": {"value": len(observed_shape_hashes), "provenance": "runtime_event"},
                "note": "per-turn chat message-shape fingerprints, content never captured",
            },
        ],
        "tools": tools,
        "reassess_when": [
            "tool_added", "model_changed", "prompt_changed",
            "approval_logic_changed", "external_api_changed", "incident",
        ],
        "review_questions": REVIEW_QUESTIONS,
    }
