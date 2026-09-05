"""Merge the draft ACAP with recorded human answers into a reviewed ACAP.

Authorization fields are resolved ONLY from artifacts/governance/acap-human-answers.yaml
(provenance: human_decision). Discovery and runtime evidence never authorize.

Inputs:
- artifacts/governance/acap-draft.yaml
- artifacts/governance/acap-human-answers.yaml

Output: artifacts/governance/acap-reviewed.yaml

Usage: python -m governance_probe.acap_review
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ART = REPO_ROOT / "artifacts" / "governance"
DRAFT = ART / "acap-draft.yaml"
ANSWERS = ART / "acap-human-answers.yaml"
OUTPUT = ART / "acap-reviewed.yaml"

# Mapping from each discovered tool to the human answer that authorizes it.
# Anything not mapped stays unresolved.
TOOL_AUTHORIZATION = {
    "get_menu": {
        "authorization": "allowed",
        "basis": "Q3_allowed_actions: 'Read menu information'",
    },
    "place_order": {
        "authorization": "allowed",
        "basis": "Q3_allowed_actions: 'Prepare an order proposal'",
    },
    "show_receipt": {
        "authorization": "allowed",
        "basis": "Q3_allowed_actions: 'Show receipt/order summary'",
    },
    "confirm_order": {
        "authorization": "allowed_with_approval",
        "basis": "Q3_allowed_actions: 'Confirm an order only after trusted customer confirmation' + Q5_approval_boundary",
    },
    "get_user_name": {
        "authorization": "allowed_conditional",
        "basis": "Q6_permitted_data: 'basic contact data only when needed'",
        "condition": "collect basic contact data only when needed for the order flow",
    },
    "greet_customer": {
        "authorization": "allowed",
        "basis": "Q3_allowed_actions: 'Greet customers and communicate local in-session greetings'",
    },
}

# Prohibited actions from Q4, with the deterministic rule (if any) that
# detects violations from runtime evidence.
PROHIBITED_ACTIONS = [
    {
        "id": "P1",
        "action": "Confirm an order without a prior place_order proposal in the same session",
        "detected_by_rule": "R1_confirm_without_proposal",
    },
    {
        "id": "P2",
        "action": "Treat model-generated response='yes' as customer approval",
        "detected_by_rule": "R2_confirmation_without_customer_turn",
        "note": "the customer's actual text is not captured (privacy-by-default), so trust is enforced "
                "structurally: the confirmation must arrive in a later invoke turn than the proposal",
    },
    {
        "id": "P3",
        "action": "Create duplicate orders from the same confirmation flow",
        "detected_by_rule": "R3_duplicate_confirmation",
    },
    {
        "id": "P4",
        "action": "Execute real payment",
        "detected_by_rule": None,
        "note": "no payment capability discovered in the codebase; reassess if added",
    },
    {
        "id": "P5",
        "action": "Send external messages",
        "detected_by_rule": None,
        "note": "no messaging capability discovered in the codebase; reassess if added",
    },
]


def main() -> int:
    draft = yaml.safe_load(DRAFT.read_text(encoding="utf-8"))
    answers = yaml.safe_load(ANSWERS.read_text(encoding="utf-8"))

    reviewed = dict(draft)
    reviewed["acap_id"] = "restaurant-agent-local-reviewed"
    reviewed["status"] = "reviewed"
    reviewed["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    reviewed["reviewed_by"] = {"value": answers["answered_by"], "provenance": "human_decision"}
    reviewed["generation_inputs"] = {
        **draft.get("generation_inputs", {}),
        "draft": str(DRAFT.relative_to(REPO_ROOT)),
        "human_answers": str(ANSWERS.relative_to(REPO_ROOT)),
    }

    reviewed["system"] = dict(draft["system"])
    reviewed["system"]["purpose"] = {"value": answers["Q1_intended_purpose"], "provenance": "human_decision"}
    reviewed["system"]["owner"] = {"value": answers["Q2_accountable_owner"], "provenance": "human_decision"}

    agents = []
    for agent in draft.get("agents", []):
        agent = dict(agent)
        agent["authorization"] = {
            "value": "allowed",
            "provenance": "human_decision",
            "basis": "Q1_intended_purpose + Q3_allowed_actions",
        }
        agents.append(agent)
    reviewed["agents"] = agents

    models = []
    for model in draft.get("models", []):
        model = dict(model)
        model["authorization"] = {
            "value": "allowed",
            "provenance": "human_decision",
            "basis": "Q3_model_authorization",
            "scope": "local-test only",
            "condition": answers["Q3_model_authorization"],
        }
        models.append(model)
    reviewed["models"] = models

    tools = []
    for tool in draft["tools"]:
        tool = dict(tool)
        decision = TOOL_AUTHORIZATION.get(tool["name"])
        if decision:
            tool["authorization"] = {
                "value": decision["authorization"],
                "provenance": decision.get("provenance", "human_decision"),
                "basis": decision["basis"],
                **({"condition": decision["condition"]} if "condition" in decision else {}),
            }
        approval_required = (answers.get("Q5_approval_required") or {}).get(tool["name"])
        if approval_required is False:
            tool["approval"] = {
                **tool.get("approval", {}),
                "required": {
                    "value": False,
                    "provenance": "human_decision",
                    "basis": "Q5_approval_required",
                },
                "condition": None,
                "note": "read-only/local-display action; no trusted approval required for local-test scope",
            }
        if tool["name"] == "confirm_order":
            tool["approval"] = {
                **tool.get("approval", {}),
                "required": {"value": True, "provenance": "human_decision", "basis": "Q5_approval_boundary"},
                "policy": {
                    "provenance": "human_decision",
                    "rules": [
                        "a place_order tool event must exist earlier in the same session",
                        "the confirmation must arrive in a later invoke turn (trusted human input 'yes'), "
                        "not the same model turn as the proposal",
                        "the model-supplied tool argument response='yes' is NOT trusted approval evidence",
                    ],
                    "known_limitations": [
                        "R2 accepts any earlier-turn place_order in the session as satisfying the "
                        "human-approval boundary regardless of item identity; a proposal for item A "
                        "is not evidence that a human approved item B (see findings.json evidence_gaps)",
                    ],
                },
            }
        tools.append(tool)
    reviewed["tools"] = tools

    reviewed["prohibited_actions"] = {
        "provenance": "human_decision",
        "items": PROHIBITED_ACTIONS,
    }
    reviewed["data_policy"] = {
        "provenance": "human_decision",
        "permitted": answers["Q6_permitted_data"],
    }
    # Union of the draft defaults and the reviewer's triggers, order-preserving.
    triggers = list(draft.get("reassess_when", []))
    for t in answers["Q7_reassessment_triggers"]:
        if t not in triggers:
            triggers.append(t)
    # Verbatim union of machine defaults and the reviewer's free-text triggers;
    # semantic duplicates (e.g. 'tool_added' / 'new tool') are intentionally kept.
    reviewed["reassess_when"] = {"normalization_status": "raw_union", "items": triggers}
    reviewed["review_questions"] = [
        {**q, "answered": True, "answer_ref": str(ANSWERS.relative_to(REPO_ROOT))}
        for q in draft.get("review_questions", [])
    ]

    unresolved = [t["name"] for t in tools if t.get("authorization") == "unresolved"]
    unresolved_approval = [
        t["name"] for t in tools
        if ((t.get("approval") or {}).get("required") or {}).get("value") == "unresolved"
    ]
    OUTPUT.write_text(yaml.safe_dump(reviewed, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    print(f"wrote {OUTPUT}")
    if unresolved:
        print(f"still unresolved tools: {unresolved}")
    if unresolved_approval:
        print(f"tools with unresolved approval.required (open review item): {unresolved_approval}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
