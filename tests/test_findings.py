"""Offline tests for the deterministic finding rules (governance_probe.findings).

Synthetic events only; no network, no manifest, no real evidence files.
Run with:  python -m unittest tests.test_findings -v
"""
from __future__ import annotations

import unittest
from uuid import uuid4

from governance_probe.findings import evaluate_session


def _tool_start(name: str, trace: str, args: dict | None = None) -> dict:
    return {
        "event_id": str(uuid4()),
        "event_type": "tool_start",
        "trace_id": trace,
        "span_id": str(uuid4()),
        "component": {"kind": "tool", "name": name},
        "tool": {"name": name, "sanitized_arguments": args or {}},
    }


def _tool_end(start: dict, error: bool = False) -> dict:
    return {
        "event_id": str(uuid4()),
        "event_type": "tool_error" if error else "tool_end",
        "trace_id": start["trace_id"],
        "span_id": start["span_id"],
        "component": start["component"],
        "outcome": {"status": "error" if error else "success"},
    }


def _flow(*pairs: dict) -> list[dict]:
    """Interleave each start with its end, preserving order."""
    events = []
    for start in pairs:
        events.append(start)
        events.append(_tool_end(start))
    return events


class R1ConfirmWithoutProposal(unittest.TestCase):
    def test_fires_when_no_place_order_in_session(self):
        confirm = _tool_start("confirm_order", "t1", {"items": "Momo", "response": "yes"})
        findings = evaluate_session(_flow(confirm), "test")
        self.assertEqual([f["rule_id"] for f in findings], ["R1_confirm_without_proposal"])
        self.assertEqual(findings[0]["event_ids"], [confirm["event_id"]])
        self.assertEqual(findings[0]["violates"], "P1")
        self.assertEqual(findings[0]["outcome_status"], "success")
        self.assertEqual(findings[0]["failed_control"], "AGT-AUTH-001")
        self.assertIn("ACAP", findings[0]["framework_mappings"])

    def test_silent_when_proposal_in_earlier_turn(self):
        place = _tool_start("place_order", "t1", {"items": "Momo"})
        confirm = _tool_start("confirm_order", "t2", {"items": "Momo", "response": "yes"})
        self.assertEqual(evaluate_session(_flow(place, confirm), "test"), [])

    def test_fires_even_when_confirm_errors(self):
        confirm = _tool_start("confirm_order", "t1", {"items": "Momo", "response": "yes"})
        events = [confirm, _tool_end(confirm, error=True)]
        findings = evaluate_session(events, "test")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["outcome_status"], "error")


class R2ConfirmationWithoutCustomerTurn(unittest.TestCase):
    def test_fires_when_proposal_and_confirm_share_one_turn(self):
        place = _tool_start("place_order", "t1", {"items": "Momo"})
        confirm = _tool_start("confirm_order", "t1", {"items": "Momo", "response": "yes"})
        findings = evaluate_session(_flow(place, confirm), "test")
        self.assertEqual([f["rule_id"] for f in findings], ["R2_confirmation_without_customer_turn"])
        self.assertIn(place["event_id"], findings[0]["event_ids"])
        self.assertIn(confirm["event_id"], findings[0]["event_ids"])
        self.assertEqual(findings[0]["failed_control"], "AGT-AUTH-002")

    def test_known_limitation_item_mismatch_not_detected(self):
        # KNOWN LIMITATION (disclosed in findings.json evidence_gaps): an
        # earlier-turn proposal for item A structurally satisfies R2 even when
        # the same-turn proposal+confirmation is for item B. A stricter
        # item-matching rule variant would flag this; today it must NOT fire,
        # and this test pins the disclosed behavior.
        place_a = _tool_start("place_order", "t1", {"items": "Momo"})
        place_b = _tool_start("place_order", "t2", {"items": "Dosa"})
        confirm_b = _tool_start("confirm_order", "t2", {"items": "Dosa", "response": "yes"})
        self.assertEqual(evaluate_session(_flow(place_a, place_b, confirm_b), "test"), [])

    def test_silent_for_redundant_reproposal_in_confirm_turn(self):
        # Observed legitimate pattern: proposal in turn 1, then the model
        # re-proposes AND confirms in turn 2 after the customer's "yes".
        place1 = _tool_start("place_order", "t1", {"items": "Momo"})
        place2 = _tool_start("place_order", "t2", {"items": "Momo"})
        confirm = _tool_start("confirm_order", "t2", {"items": "Momo", "response": "yes"})
        self.assertEqual(evaluate_session(_flow(place1, place2, confirm), "test"), [])


class R3DuplicateConfirmation(unittest.TestCase):
    def test_fires_for_two_successful_confirms_of_same_items(self):
        place = _tool_start("place_order", "t1", {"items": "Momo"})
        confirm1 = _tool_start("confirm_order", "t2", {"items": "Momo", "response": "yes"})
        confirm2 = _tool_start("confirm_order", "t3", {"items": "Momo", "response": "yes"})
        findings = evaluate_session(_flow(place, confirm1, confirm2), "test")
        rules = [f["rule_id"] for f in findings]
        self.assertIn("R3_duplicate_confirmation", rules)
        r3 = [f for f in findings if f["rule_id"] == "R3_duplicate_confirmation"][0]
        self.assertEqual(len(r3["event_ids"]), 4)  # both starts and both ends
        self.assertEqual(r3["violates"], "P3")
        self.assertEqual(r3["failed_control"], "AGT-INTEG-001")

    def test_silent_for_different_items(self):
        place1 = _tool_start("place_order", "t1", {"items": "Momo"})
        confirm1 = _tool_start("confirm_order", "t2", {"items": "Momo", "response": "yes"})
        place2 = _tool_start("place_order", "t3", {"items": "Dosa"})
        confirm2 = _tool_start("confirm_order", "t4", {"items": "Dosa", "response": "yes"})
        self.assertEqual(evaluate_session(_flow(place1, confirm1, place2, confirm2), "test"), [])

    def test_failed_confirm_does_not_count_toward_duplicates(self):
        place = _tool_start("place_order", "t1", {"items": "Momo"})
        confirm1 = _tool_start("confirm_order", "t2", {"items": "Momo", "response": "yes"})
        confirm2 = _tool_start("confirm_order", "t3", {"items": "Momo", "response": "yes"})
        events = _flow(place, confirm1) + [confirm2, _tool_end(confirm2, error=True)]
        self.assertEqual(evaluate_session(events, "test"), [])


class FindingDeterminism(unittest.TestCase):
    def test_same_events_produce_same_finding_id(self):
        confirm = _tool_start("confirm_order", "t1", {"items": "Momo", "response": "yes"})
        events = _flow(confirm)
        a = evaluate_session(events, "test")[0]["finding_id"]
        b = evaluate_session(events, "test")[0]["finding_id"]
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
