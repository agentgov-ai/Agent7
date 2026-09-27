"""Tests for the Agent7 enforcement endpoints on the Evidence API.

Run with:  python -m unittest tests.test_enforcement_api -v
"""
from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from services.evidence_api.app import app

SYSTEM_ID = "enforcement-api-test"


def action_payload(capability_name: str, **overrides) -> dict:
    payload = {
        "action_id": f"ACT-{uuid.uuid4().hex[:16]}",
        "system_id": SYSTEM_ID,
        "deployment_id": "local-test",
        "environment": "test",
        "agent_id": "agent7-demo",
        "capability_name": capability_name,
        "capability_id": None,
        "module_path": f"app.{capability_name}",
        "action_type": "write",
        "data_classes": [],
        "external_side_effect": True,
        "approval_required": False,
        "arguments_hash": "sha256:deadbeef",
        "argument_names": ["record_id"],
        "argument_types": {"record_id": "str"},
        "argument_features": {"argument_count": 1, "has_str_args": True},
        "session_id": "session-1",
        "trace_id": None,
        "parent_span_id": None,
        "enforcement_mode": "enforce",
        "created_at": "2026-09-27T00:00:00+00:00",
    }
    payload.update(overrides)
    return payload


class EnforcementApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["EVIDENCE_DB_PATH"] = str(Path(self.tmp.name) / "evidence.db")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.tmp.cleanup()
        os.environ.pop("EVIDENCE_DB_PATH", None)

    # -- helpers -------------------------------------------------------

    def seed_discovery(self, capabilities: list[dict]) -> None:
        """Register the system with reviewed capabilities."""
        discovery = {
            "schema_version": "0.1",
            "scanner_version": "0.1.0",
            "source": "deterministic_scanner",
            "project_hash": "sha256:test",
            "scan_summary": {
                "files_scanned": 1,
                "functions_seen": len(capabilities),
                "candidates_found": len(capabilities),
                "model_surface_found": 0,
                "high_risk_count": 0,
                "medium_risk_count": 0,
                "low_risk_count": 0,
                "ignored_helpers_count": 0,
            },
            "candidates": [
                {
                    "capability_id": cap["capability_id"],
                    "name": cap["name"],
                    "module_path": f"app.{cap['name']}",
                    "file_path": "app.py",
                    "line_start": 1,
                    "line_end": 2,
                    "suggested_action_type": "write",
                    "suggested_data_classes": [],
                    "suggested_approval_required": cap.get("approval_required", False),
                    "external_side_effect": True,
                    "risk": "high",
                    "confidence": 0.9,
                    "confidence_source": "deterministic",
                    "evidence": [],
                    "call_chain": [],
                    "review_status": "pending",
                    "source": "deterministic_scanner",
                }
                for cap in capabilities
            ],
            "model_surface": [],
        }
        response = self.client.post(
            "/discovery/upload", json={"system_id": SYSTEM_ID, "discovery": discovery}
        )
        self.assertEqual(response.status_code, 200, response.text)

        for cap in capabilities:
            verb = cap["decision"]
            response = self.client.post(
                f"/systems/{SYSTEM_ID}/capabilities/{cap['capability_id']}/{verb}"
            )
            self.assertEqual(response.status_code, 200, response.text)

    def evaluate(self, capability_name: str, **overrides) -> dict:
        response = self.client.post(
            "/actions/evaluate", json={"action": action_payload(capability_name, **overrides)}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["decision"]

    # -- tests ---------------------------------------------------------

    def test_evaluate_returns_allow_for_approved_capability(self):
        self.seed_discovery(
            [{"capability_id": "CAP-allow01", "name": "fetch_live_flights", "decision": "approve"}]
        )
        decision = self.evaluate("fetch_live_flights")
        self.assertEqual(decision["verdict"], "ALLOW")
        self.assertEqual(decision["decided_by"], "backend")
        self.assertTrue(decision["decision_id"].startswith("DEC-"))

    def test_evaluate_returns_deny_for_rejected_capability(self):
        self.seed_discovery(
            [{"capability_id": "CAP-deny01", "name": "delete_airspace_record", "decision": "reject"}]
        )
        decision = self.evaluate("delete_airspace_record")
        self.assertEqual(decision["verdict"], "DENY")
        self.assertEqual(decision["reason_code"], "capability_denied")

    def test_kill_switch_forces_deny_on_an_approved_capability(self):
        self.seed_discovery(
            [{"capability_id": "CAP-allow02", "name": "fetch_live_flights", "decision": "approve"}]
        )
        self.assertEqual(self.evaluate("fetch_live_flights")["verdict"], "ALLOW")

        created = self.client.post(
            f"/systems/{SYSTEM_ID}/kill-switches",
            json={
                "kill_switch_id": "disable_live_airspace",
                "target_capabilities": ["fetch_live_flights"],
                "enabled": True,
                "reason": "Live airspace disabled for demo",
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertTrue(created.json()["enabled"])

        decision = self.evaluate("fetch_live_flights")
        self.assertEqual(decision["verdict"], "DENY")
        self.assertEqual(decision["reason_code"], "kill_switch")
        self.assertEqual(decision["kill_switch_id"], "disable_live_airspace")

    def test_kill_switch_can_be_disabled_again(self):
        self.seed_discovery(
            [{"capability_id": "CAP-allow03", "name": "fetch_live_flights", "decision": "approve"}]
        )
        self.client.post(
            f"/systems/{SYSTEM_ID}/kill-switches",
            json={
                "kill_switch_id": "ks1",
                "target_capabilities": ["fetch_live_flights"],
                "enabled": True,
            },
        )
        self.assertEqual(self.evaluate("fetch_live_flights")["verdict"], "DENY")

        patched = self.client.patch(
            f"/systems/{SYSTEM_ID}/kill-switches/ks1", json={"enabled": False}
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertFalse(patched.json()["enabled"])
        self.assertEqual(self.evaluate("fetch_live_flights")["verdict"], "ALLOW")

    def test_patch_unknown_kill_switch_is_404(self):
        response = self.client.patch(
            f"/systems/{SYSTEM_ID}/kill-switches/nope", json={"enabled": False}
        )
        self.assertEqual(response.status_code, 404)

    def test_approval_required_capability_is_held(self):
        self.seed_discovery(
            [
                {
                    "capability_id": "CAP-appr01",
                    "name": "export_query_result",
                    "decision": "approve",
                    "approval_required": True,
                }
            ]
        )
        decision = self.evaluate("export_query_result", approval_required=True)
        self.assertEqual(decision["verdict"], "REQUIRE_APPROVAL")
        self.assertTrue(decision["approval_required"])

    def test_action_list_endpoint_returns_persisted_records(self):
        self.seed_discovery(
            [
                {"capability_id": "CAP-a", "name": "fetch_live_flights", "decision": "approve"},
                {"capability_id": "CAP-b", "name": "delete_airspace_record", "decision": "reject"},
            ]
        )
        allowed = self.evaluate("fetch_live_flights")
        denied = self.evaluate("delete_airspace_record")

        # Report the outcomes the way the SDK does.
        for decision, name, executed, status in (
            (allowed, "fetch_live_flights", True, "allowed_executed"),
            (denied, "delete_airspace_record", False, "denied_blocked"),
        ):
            response = self.client.post(
                "/actions/record",
                json={
                    "record": {
                        "record_id": f"REC-{uuid.uuid4().hex[:16]}",
                        "action_id": decision["action_id"],
                        "decision_id": decision["decision_id"],
                        "system_id": SYSTEM_ID,
                        "request": action_payload(name, action_id=decision["action_id"]),
                        "decision": decision,
                        "executed": executed,
                        "execution_status": status,
                        "would_have_blocked": not executed,
                        "duration_ms": 1.5,
                        "event_ids": [],
                        "evidence_hash": "sha256:abc",
                    }
                },
            )
            self.assertEqual(response.status_code, 200, response.text)

        listing = self.client.get(f"/systems/{SYSTEM_ID}/actions")
        self.assertEqual(listing.status_code, 200, listing.text)
        body = listing.json()

        self.assertEqual(body["count"], 2)
        self.assertEqual(body["summary"]["total"], 2)
        self.assertEqual(body["summary"]["allowed"], 1)
        self.assertEqual(body["summary"]["denied"], 1)
        self.assertEqual(body["summary"]["blocked"], 1)
        self.assertEqual(body["summary"]["executed"], 1)

        by_name = {item["capability_name"]: item for item in body["actions"]}
        self.assertEqual(by_name["fetch_live_flights"]["verdict"], "ALLOW")
        self.assertTrue(by_name["fetch_live_flights"]["executed"])
        self.assertEqual(by_name["delete_airspace_record"]["verdict"], "DENY")
        self.assertFalse(by_name["delete_airspace_record"]["executed"])

    def test_listing_shows_one_row_per_action_using_the_enforced_decision(self):
        """An action carries both the backend decision and the enforced one."""
        self.seed_discovery(
            [{"capability_id": "CAP-two", "name": "run_trino_query", "decision": "approve"}]
        )
        backend_decision = self.evaluate("run_trino_query")
        self.assertEqual(backend_decision["verdict"], "ALLOW")

        # The SDK's local policy was stricter, so it enforced its own DENY.
        enforced = {
            "decision_id": "DEC-local-strict",
            "action_id": backend_decision["action_id"],
            "verdict": "DENY",
            "reason": "Argument matched denied pattern",
            "reason_code": "argument_pattern_denied",
            "decided_by": "sdk_local",
            "matched_pattern_id": "destructive_sql",
        }
        response = self.client.post(
            "/actions/record",
            json={
                "record": {
                    "record_id": "REC-strict",
                    "action_id": backend_decision["action_id"],
                    "decision_id": enforced["decision_id"],
                    "system_id": SYSTEM_ID,
                    "request": action_payload(
                        "run_trino_query", action_id=backend_decision["action_id"]
                    ),
                    "decision": enforced,
                    "executed": False,
                    "execution_status": "denied_blocked",
                    "would_have_blocked": True,
                }
            },
        )
        self.assertEqual(response.status_code, 200, response.text)

        body = self.client.get(f"/systems/{SYSTEM_ID}/actions").json()
        self.assertEqual(body["count"], 1, "the action fanned out into duplicate rows")
        row = body["actions"][0]
        self.assertEqual(row["verdict"], "DENY")
        self.assertEqual(row["reason_code"], "argument_pattern_denied")
        self.assertEqual(row["execution_status"], "denied_blocked")
        self.assertEqual(body["summary"]["total"], 1)
        self.assertEqual(body["summary"]["denied"], 1)
        self.assertEqual(body["summary"]["allowed"], 0)

    def test_shadow_counter_only_counts_shadow_mode_records(self):
        self.seed_discovery(
            [{"capability_id": "CAP-sh", "name": "delete_airspace_record", "decision": "reject"}]
        )
        blocked = self.evaluate("delete_airspace_record")
        self.client.post(
            "/actions/record",
            json={
                "record": {
                    "record_id": "REC-enforced",
                    "action_id": blocked["action_id"],
                    "decision_id": blocked["decision_id"],
                    "system_id": SYSTEM_ID,
                    "request": action_payload(
                        "delete_airspace_record", action_id=blocked["action_id"]
                    ),
                    "decision": blocked,
                    "executed": False,
                    "execution_status": "denied_blocked",
                    "would_have_blocked": True,
                }
            },
        )
        summary = self.client.get(f"/systems/{SYSTEM_ID}/actions").json()["summary"]
        self.assertEqual(summary["blocked"], 1)
        self.assertEqual(
            summary["shadow_would_block"], 0, "an enforce-mode block was counted as shadow"
        )

    def test_action_detail_endpoint(self):
        self.seed_discovery(
            [{"capability_id": "CAP-d1", "name": "fetch_live_flights", "decision": "approve"}]
        )
        decision = self.evaluate("fetch_live_flights")
        detail = self.client.get(f"/systems/{SYSTEM_ID}/actions/{decision['action_id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        body = detail.json()
        self.assertEqual(body["request"]["capability_name"], "fetch_live_flights")
        self.assertEqual(body["decision"]["verdict"], "ALLOW")
        self.assertIsNone(body["record"])

    def test_unknown_action_detail_is_404(self):
        response = self.client.get(f"/systems/{SYSTEM_ID}/actions/ACT-missing")
        self.assertEqual(response.status_code, 404)

    def test_evaluate_requires_system_id_and_capability_name(self):
        response = self.client.post("/actions/evaluate", json={"action": {"system_id": ""}})
        self.assertEqual(response.status_code, 422)
        response = self.client.post("/actions/evaluate", json={"action": {"system_id": "s"}})
        self.assertEqual(response.status_code, 422)

    def test_system_becomes_listable_from_actions_alone(self):
        """An app may post actions before any discovery upload exists."""
        decision = self.evaluate("some_capability")
        self.assertIn(decision["verdict"], {"ALLOW", "DENY"})
        systems = self.client.get("/systems").json()
        self.assertIn(SYSTEM_ID, [item["system_id"] for item in systems["systems"]])

    def test_no_backend_policy_defers_to_local_manifest(self):
        decision = self.evaluate("ungoverned_capability")
        self.assertEqual(decision["verdict"], "ALLOW")
        self.assertIn("deferring to local manifest", decision["reason"])


if __name__ == "__main__":
    unittest.main()
