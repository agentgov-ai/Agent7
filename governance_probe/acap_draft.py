"""Generate a draft ACAP from discovery, overrides and local runtime evidence.

Inputs (all local):
- artifacts/governance/discovery.json   (code discovery: tools, prompt/model fingerprints)
- governance-tool-overrides.yaml        (human technical annotations)
- artifacts/governance/events.jsonl     (observed runtime behavior)
- templates/restaurant-acap.example.yaml (shape reference only)

Output: artifacts/governance/acap-draft.yaml

Discovery/observation never implies authorization: every authorization field
is emitted as ``unresolved`` and every auto-filled value carries provenance.

Usage: python -m governance_probe.acap_draft
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
ART = REPO_ROOT / "artifacts" / "governance"
DISCOVERY = ART / "discovery.json"
EVENTS = ART / "events.jsonl"
OVERRIDES = REPO_ROOT / "governance-tool-overrides.yaml"
TEMPLATE = REPO_ROOT / "templates" / "restaurant-acap.example.yaml"
OUTPUT = ART / "acap-draft.yaml"

# Reviewer-facing caveats that the overrides file carries only as comments,
# plus semantic gaps flagged by governance review. Keyed by (tool, field).
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
        "question": "What is this restaurant agent intended to do, and for whom? (Discovered capability: menu Q&A, order drafting, order confirmation to a staff-verification log, receipt display.)",
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
        "question": "Which discovered tools are ALLOWED in normal operation? (greet_customer, get_user_name, get_menu, place_order, confirm_order, show_receipt — all currently unresolved.)",
        "fills": ["tools[*].authorization"],
    },
    {
        "id": "Q4",
        "topic": "prohibited_actions",
        "question": "Which actions must be PROHIBITED (e.g., confirming an order the customer never proposed, adding unrequested items, any future payment/messaging capability)?",
        "fills": ["tools[*].authorization", "prohibited_actions"],
    },
    {
        "id": "Q5",
        "topic": "approval_requirements",
        "question": "Should confirm_order require evidence of a prior place_order proposal AND an explicit customer 'yes' turn in the same session before it may write, while all read-only/local-display tools require no approval? (Runtime evidence: event bef3e128-513d-4484-86d2-603c8916e220 shows confirm_order invoked with a model-supplied response='yes' argument and no prior place_order tool_start in the same trace. This occurred during the controlled adversarial test s5_adversarial — see artifacts/governance/scenarios/manifest.json — demonstrating the argument-derived approval signal is spoofable and must not be trusted.)",
        "fills": ["tools[confirm_order].approval"],
    },
    {
        "id": "Q6",
        "topic": "sensitive_data",
        "question": "Which customer data may the agent process or store? (Currently observed: customer first name in-session [redacted in evidence], order items in a local log. No payment, contact-detail or address capability discovered.)",
        "fills": ["data_policy"],
    },
    {
        "id": "Q7",
        "topic": "reassessment_triggers",
        "question": "Besides the defaults (tool added, model changed, prompt changed, approval logic changed, external API changed, incident), what business changes require reassessment (e.g., real payment integration, real customer data, non-local deployment)?",
        "fills": ["reassess_when"],
    },
]


def _load_events() -> list[dict]:
    if not EVENTS.exists():
        return []
    return [json.loads(l) for l in EVENTS.open(encoding="utf-8")]


def _observed_tool_stats(events: list[dict]) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for e in events:
        if e.get("component", {}).get("kind") != "tool":
            continue
        name = e["component"]["name"]
        entry = stats.setdefault(name, {"starts": 0, "successes": 0, "errors": 0, "error_types": Counter(), "evidence_fields": set()})
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


def build_draft() -> dict:
    discovery = json.loads(DISCOVERY.read_text(encoding="utf-8"))
    overrides = (yaml.safe_load(OVERRIDES.read_text(encoding="utf-8")) or {}).get("tools", {}) if OVERRIDES.exists() else {}
    events = _load_events()
    stats = _observed_tool_stats(events)

    observed_models = sorted(
        {(e.get("model") or {}).get("name") for e in events if e["event_type"] in ("llm_start", "llm_end")} - {None}
    )
    observed_shape_hashes = sorted(
        {(e.get("prompt") or {}).get("template_hash") for e in events if e["event_type"] == "llm_start"} - {None}
    )

    tools = []
    for t in discovery["tools"]:
        name = t["name"]
        o = overrides.get(name, {})
        observed = stats.get(name)
        approval_meta = o.get("approval") or {}
        entry = {
            "name": name,
            "discovered": True,
            "observed": observed is not None,
            "description_hash": {"value": t["description_hash"], "provenance": "code_discovery"},
            "implementation": {"value": t["implementation"], "provenance": "code_discovery"},
            "args_schema": {"value": t["args_schema"], "provenance": "code_discovery",
                            "note": None if t["args_schema"] else "plain function; no pydantic args schema attached"},
            "proposed_action_type": {"value": o.get("action_type", "unknown"),
                                     "provenance": "tool_override" if "action_type" in o else "code_discovery",
                                     **({"note": TOOL_FIELD_NOTES[(name, "proposed_action_type")]}
                                        if (name, "proposed_action_type") in TOOL_FIELD_NOTES else {})},
            "proposed_external_side_effect": {"value": o.get("external_side_effect"),
                                              "provenance": "tool_override" if "external_side_effect" in o else "unresolved"},
            "proposed_reversible": {"value": o.get("reversible"),
                                    "provenance": "tool_override" if "reversible" in o else "unresolved",
                                    **({"note": TOOL_FIELD_NOTES[(name, "proposed_reversible")]}
                                       if (name, "proposed_reversible") in TOOL_FIELD_NOTES else {})},
            "proposed_data_classes": {"value": o.get("data_classes", []),
                                      "provenance": "tool_override" if "data_classes" in o else "unresolved"},
            "proposed_target": {"value": o.get("target"), "provenance": "tool_override" if "target" in o else "unresolved"},
            "authorization": "unresolved",
            "approval": {
                "required": {"value": approval_meta.get("required", "unresolved"),
                             "provenance": "tool_override" if approval_meta else "unresolved"},
                "condition": approval_meta.get("condition"),
                "note": ("approval.required is annotation-only; approval.granted is not derived from model-supplied "
                         "tool arguments. Trusted approval must be established structurally by the reviewed ACAP "
                         "and findings rules; see review question Q5") if approval_meta else None,
            },
            "observed_usage": {
                "provenance": "runtime_event",
                "starts": observed["starts"] if observed else 0,
                "successes": observed["successes"] if observed else 0,
                "errors": observed["errors"] if observed else 0,
                "error_types": dict(observed["error_types"]) if observed else {},
            } if observed else {"provenance": "runtime_event", "note": "not observed in any recorded run"},
            "evidence_fields_available": sorted(observed["evidence_fields"]) if observed else [],
        }
        tools.append(entry)

    return {
        "schema_version": "0.1",
        "acap_id": "restaurant-agent-local-draft",
        "status": "draft",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation_inputs": {
            "discovery": str(DISCOVERY.relative_to(REPO_ROOT)),
            "overrides": str(OVERRIDES.name),
            "events": str(EVENTS.relative_to(REPO_ROOT)),
            "template_shape_reference": str(TEMPLATE.relative_to(REPO_ROOT)),
        },
        "system": {
            "system_id": "restaurant-agent",
            "deployment_id": "local-test",
            "environment": "local",
            "framework": {"value": {k: v for k, v in discovery.get("package_versions", {}).items()},
                          "provenance": "code_discovery"},
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
                "template_hash": {"value": (discovery.get("prompt") or {}).get("template_hash"), "provenance": "code_discovery"},
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
            "tool_added",
            "model_changed",
            "prompt_changed",
            "approval_logic_changed",
            "external_api_changed",
            "incident",
        ],
        "review_questions": REVIEW_QUESTIONS,
    }


def validate_shape(draft: dict) -> list[str]:
    """Template is a shape reference: every top-level template key must exist."""
    template = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    problems = [f"missing top-level key: {key}" for key in template if key not in draft]
    for tool in draft["tools"]:
        if tool.get("authorization") != "unresolved":
            problems.append(f"tool {tool['name']}: authorization must remain unresolved in a draft")
    if len(draft["review_questions"]) > 7:
        problems.append("more than seven review questions")
    return problems


def main() -> int:
    draft = build_draft()
    problems = validate_shape(draft)
    OUTPUT.write_text(yaml.safe_dump(draft, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    print(f"wrote {OUTPUT}")
    if problems:
        print("shape validation problems:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("shape validation: OK (template keys present, authorization unresolved, <=7 questions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
