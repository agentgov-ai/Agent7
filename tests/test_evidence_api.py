from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from services.evidence_api.app import app

REPO_ROOT = Path(__file__).resolve().parents[1]
EVENTS = REPO_ROOT / "artifacts" / "governance" / "events.jsonl"
DEMO_DATA = REPO_ROOT / "examples" / "demo-data"
DEMO_SYSTEM_IDS = {
    "restaurant-agent",
    "customer-refund-agent",
    "custom-python-refund-agent",
    "openai-direct-agent",
    "anthropic-direct-agent",
    "support-api",
}


def event_count() -> int:
    return sum(1 for line in EVENTS.read_text(encoding="utf-8").splitlines() if line.strip())


def demo_event_count() -> int:
    return sum(
        1
        for path in DEMO_DATA.glob("*/events.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


SAMPLE_DISCOVERY = {
    "schema_version": "0.1",
    "scanner_version": "0.1.0",
    "source": "deterministic_scanner",
    "project_hash": "sha256:abc123",
    "scan_summary": {
        "files_scanned": 1, "functions_seen": 5,
        "candidates_found": 2, "model_surface_found": 1,
        "high_risk_count": 1, "medium_risk_count": 1,
        "low_risk_count": 0, "ignored_helpers_count": 3,
        "unenumerated_surface": [],
    },
    "candidates": [
        {
            "capability_id": "CAP-test-001",
            "name": "refund_execute",
            "module_path": "app",
            "file_path": "app.py",
            "line_start": 46, "line_end": 49,
            "suggested_action_type": "write",
            "suggested_data_classes": ["financial"],
            "suggested_approval_required": True,
            "external_side_effect": True,
            "risk": "high",
            "confidence": 0.95,
            "confidence_source": "sink_reachability",
            "evidence": [{"type": "sink_call", "detail": "stripe.refunds.create", "line": 48}],
            "call_chain": ["refund_execute -> stripe.refunds.create"],
            "review_status": "pending",
            "source": "deterministic_scanner",
        },
        {
            "capability_id": "CAP-test-002",
            "name": "get_report",
            "module_path": "app",
            "file_path": "app.py",
            "line_start": 10, "line_end": 15,
            "suggested_action_type": "read",
            "suggested_data_classes": [],
            "suggested_approval_required": False,
            "external_side_effect": False,
            "risk": "medium",
            "confidence": 0.50,
            "confidence_source": "name_heuristic",
            "evidence": [{"type": "name_heuristic", "detail": "function name matches", "line": 10}],
            "call_chain": [],
            "review_status": "pending",
            "source": "deterministic_scanner",
        },
    ],
    "model_surface": [
        {
            "name": "generate_reply", "module_path": "app", "file_path": "app.py",
            "line": 79, "provider": "openai",
            "call_chain": ["generate_reply -> openai.chat.completions.create"],
            "category": "model_usage",
        },
    ],
}


class EvidenceApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["EVIDENCE_DB_PATH"] = str(Path(self.tmp.name) / "evidence.db")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.tmp.cleanup()
        os.environ.pop("EVIDENCE_DB_PATH", None)

    def replay_events(self) -> dict:
        response = self.client.post("/evidence/replay-jsonl", json={"path": str(EVENTS), "reset": True})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def upload_discovery(self, system_id: str = "test-system") -> dict:
        response = self.client.post("/discovery/upload", json={
            "system_id": system_id,
            "discovery": SAMPLE_DISCOVERY,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_system_registry_exposes_reviewed_acap_summary(self):
        systems = self.client.get("/systems")
        self.assertEqual(systems.status_code, 200, systems.text)
        body = systems.json()
        self.assertGreaterEqual(body["count"], 1)
        system = next(s for s in body["systems"] if s["system_id"] == "restaurant-agent")
        self.assertEqual(system["acap_id"], "restaurant-agent-local-reviewed")
        self.assertEqual(system["acap_status"], "reviewed")

        acap = self.client.get("/systems/restaurant-agent/acap")
        self.assertEqual(acap.status_code, 200, acap.text)
        summary = acap.json()["acap"]
        self.assertEqual(summary["acap_id"], "restaurant-agent-local-reviewed")
        self.assertEqual(summary["status"], "reviewed")
        self.assertIn("confirm_order", summary["approval_required_tools"])
        self.assertGreaterEqual(summary["prohibited_action_count"], 3)
        self.assertEqual(summary["contract"]["governance_event_schema"], "schemas\\governance-event.schema.json")

    def test_replay_jsonl_stores_all_events(self):
        result = self.replay_events()
        expected_count = event_count()
        self.assertEqual(result["accepted"], expected_count)
        self.assertEqual(result["duplicates"], 0)
        self.assertEqual(result["rejected_count"], 0)

        events_response = self.client.get("/evidence/events", params={"limit": 5000})
        self.assertEqual(events_response.status_code, 200)
        payload = events_response.json()
        self.assertEqual(payload["count"], expected_count)
        text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("I want to order", text)
        self.assertNotIn("ignore all", text.lower())
        self.assertNotIn("restaurant waiter bot", text.lower())
        self.assertNotIn("sanitized_arguments", text)
        self.assertNotIn("result_summary", text)

    def test_run_r1_reproduces_existing_finding(self):
        self.replay_events()
        run = self.client.post("/rules/run", json={"rule_ids": ["R1_confirm_without_proposal"]})
        self.assertEqual(run.status_code, 200, run.text)
        body = run.json()
        self.assertEqual(body["events_evaluated"], event_count())
        self.assertEqual(body["findings_created"], 1)
        finding = body["findings"][0]
        self.assertEqual(finding["finding_id"], "F-06236c96da2c")
        self.assertEqual(finding["rule_id"], "R1_confirm_without_proposal")
        self.assertEqual(finding["event_ids"], ["bef3e128-513d-4484-86d2-603c8916e220"])
        self.assertEqual(finding["failed_control"], "AGT-AUTH-001")
        self.assertEqual(finding["failed_control_title"], "Agent must obtain human approval before executing write actions")
        self.assertIn("ACAP", finding["framework_mappings"])
        self.assertIn("NIST_AI_RMF", finding["framework_mappings"])
        self.assertIn("EU_AI_Act", finding["framework_mappings"])
        self.assertIn("ISO_42001", finding["framework_mappings"])
        self.assertIn("potential relevance", finding["framework_mappings"]["EU_AI_Act"]["note"])

        findings = self.client.get("/findings")
        self.assertEqual(findings.status_code, 200)
        self.assertEqual(findings.json()["count"], 1)
        self.assertEqual(findings.json()["findings"][0]["finding_id"], "F-06236c96da2c")

    def test_run_rules_accepts_no_body(self):
        self.replay_events()
        run = self.client.post("/rules/run")
        self.assertEqual(run.status_code, 200, run.text)
        body = run.json()
        self.assertEqual(body["rules"], ["R1_confirm_without_proposal"])
        self.assertEqual(body["findings"][0]["finding_id"], "F-06236c96da2c")
        self.assertEqual(body["findings"][0]["event_ids"], ["bef3e128-513d-4484-86d2-603c8916e220"])

    def test_run_rules_accepts_empty_json_body(self):
        self.replay_events()
        run = self.client.post("/rules/run", json={})
        self.assertEqual(run.status_code, 200, run.text)
        body = run.json()
        self.assertEqual(body["rules"], ["R1_confirm_without_proposal"])
        self.assertEqual(body["findings"][0]["finding_id"], "F-06236c96da2c")
        self.assertEqual(body["findings"][0]["event_ids"], ["bef3e128-513d-4484-86d2-603c8916e220"])

    def test_invalid_event_rejected_with_explanation(self):
        event = json.loads(EVENTS.read_text(encoding="utf-8").splitlines()[0])
        event.pop("event_id")
        response = self.client.post("/evidence/events", json={"event": event})
        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(detail["accepted"], 0)
        self.assertIn("missing required field: event_id", detail["rejected"][0]["errors"])

    def test_raw_prompt_text_rejected(self):
        event = json.loads(EVENTS.read_text(encoding="utf-8").splitlines()[0])
        event["attributes"] = {"unsafe": "restaurant waiter bot"}
        response = self.client.post("/evidence/events", json={"event": event})
        self.assertEqual(response.status_code, 422)
        errors = response.json()["detail"]["rejected"][0]["errors"]
        self.assertIn("raw text probe matched: system_prompt_text", errors)


    # ---- ACAP draft / review / coverage tests ----

    def test_acap_draft_generates_from_db_events(self):
        self.replay_events()
        response = self.client.get("/systems/restaurant-agent/acap/draft")
        self.assertEqual(response.status_code, 200, response.text)
        draft = response.json()
        self.assertEqual(draft["status"], "draft")
        self.assertIn("tools", draft)
        self.assertTrue(len(draft["tools"]) >= 1)
        # Observed tools should have usage stats
        observed_any = False
        for tool in draft["tools"]:
            usage = tool.get("observed_usage") or {}
            if isinstance(usage.get("starts"), int) and usage["starts"] > 0:
                observed_any = True
        self.assertTrue(observed_any, "at least one tool should have observed usage")

    def test_draft_never_authorizes(self):
        self.replay_events()
        response = self.client.get("/systems/restaurant-agent/acap/draft")
        self.assertEqual(response.status_code, 200)
        for tool in response.json()["tools"]:
            self.assertEqual(
                tool["authorization"], "unresolved",
                f"tool {tool['name']}: authorization must be unresolved in draft",
            )

    def test_acap_review_stores_and_retrieves_decisions(self):
        self.replay_events()
        review = self.client.post(
            "/systems/restaurant-agent/acap/review",
            json={
                "reviewed_by": "test-reviewer",
                "decisions": [
                    {"tool_name": "get_menu", "authorization": "allowed", "basis": "test"},
                    {"tool_name": "confirm_order", "authorization": "allowed_with_approval",
                     "basis": "test-approval", "approval_required": True},
                ],
            },
        )
        self.assertEqual(review.status_code, 200, review.text)
        body = review.json()
        self.assertEqual(body["reviewed_by"], "test-reviewer")
        self.assertGreaterEqual(body["decisions_stored"], 2)

        reviewed = self.client.get("/systems/restaurant-agent/acap/reviewed")
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        tools = {t["name"]: t for t in reviewed.json().get("tools", [])}
        menu_auth = tools.get("get_menu", {}).get("authorization", {})
        self.assertEqual(menu_auth.get("value"), "allowed")
        self.assertEqual(menu_auth.get("provenance"), "human_decision")
        confirm_auth = tools.get("confirm_order", {}).get("authorization", {})
        self.assertEqual(confirm_auth.get("value"), "allowed_with_approval")

    def test_acap_reviewed_falls_back_to_yaml(self):
        # No review decisions posted — should return YAML as-is
        reviewed = self.client.get("/systems/restaurant-agent/acap/reviewed")
        self.assertEqual(reviewed.status_code, 200)
        data = reviewed.json()
        self.assertEqual(data["acap_id"], "restaurant-agent-local-reviewed")
        self.assertEqual(data["status"], "reviewed")

    def test_existing_finding_preserved_after_review(self):
        self.replay_events()
        self.client.post(
            "/systems/restaurant-agent/acap/review",
            json={
                "reviewed_by": "test",
                "decisions": [{"tool_name": "get_menu", "authorization": "allowed"}],
            },
        )
        run = self.client.post("/rules/run")
        self.assertEqual(run.status_code, 200)
        self.assertEqual(run.json()["findings"][0]["finding_id"], "F-06236c96da2c")

    def test_coverage_reports_field_presence(self):
        self.replay_events()
        response = self.client.get("/systems/restaurant-agent/coverage")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["system_id"], "restaurant-agent")
        self.assertEqual(body["event_count"], event_count())
        self.assertEqual(len(body["fields"]), 17)
        for entry in body["fields"]:
            self.assertIn("field", entry)
            self.assertIn("status", entry)
            self.assertIn("presence", entry)
        # No raw text in coverage response
        text = json.dumps(body, ensure_ascii=False)
        self.assertNotIn("restaurant waiter bot", text.lower())
        self.assertNotIn("I want to order", text)



    # ---- Facts-driven applicability for discovery-only systems ----

    def _seed_discovery_only_system(self, system_id: str, capabilities: list[dict]) -> None:
        """Register a system the way a scanner upload does -- no reviewed ACAP."""
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
                "low_risk_count": len(capabilities),
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
                    "suggested_action_type": cap.get("action_type", "read"),
                    "suggested_data_classes": [],
                    "suggested_approval_required": False,
                    "external_side_effect": cap.get("external_side_effect", False),
                    "risk": "low",
                    "confidence": 0.7,
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
            "/discovery/upload", json={"system_id": system_id, "discovery": discovery}
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_acap_applicable_from_approved_capabilities_without_reviewed_acap(self):
        """A discovery-only system with an approved boundary must not read as not_applicable."""
        sid = "facts-acap-system"
        self._seed_discovery_only_system(
            sid,
            [
                {"capability_id": "CAP-facts01", "name": "get_live_flights"},
                {"capability_id": "CAP-facts02", "name": "read_airports"},
            ],
        )
        response = self.client.get(f"/systems/{sid}/framework-applicability")
        frameworks = {f["framework"]: f for f in response.json()["frameworks"]}
        # Discovered but unapproved: no authorization boundary exists yet.
        self.assertFalse(frameworks["ACAP"]["applicable"])
        # ...but tool/API behaviour was discovered, so OWASP Agentic applies.
        self.assertTrue(frameworks["OWASP Agentic"]["applicable"])

        self.client.post(f"/systems/{sid}/capabilities/CAP-facts01/approve")
        response = self.client.get(f"/systems/{sid}/framework-applicability")
        frameworks = {f["framework"]: f for f in response.json()["frameworks"]}
        self.assertTrue(frameworks["ACAP"]["applicable"])
        self.assertIn("approved", frameworks["ACAP"]["reason"].lower())

    def test_applicability_entries_carry_explanations(self):
        sid = "facts-explain-system"
        self._seed_discovery_only_system(
            sid, [{"capability_id": "CAP-exp01", "name": "run_query", "action_type": "execute"}]
        )
        self.client.post(f"/systems/{sid}/capabilities/CAP-exp01/approve")
        frameworks = {
            f["framework"]: f
            for f in self.client.get(f"/systems/{sid}/framework-applicability").json()["frameworks"]
        }

        acap = frameworks["ACAP"]
        self.assertTrue(acap["why"], "an applicable framework must say why")
        self.assertTrue(acap["evidence"])
        self.assertTrue(acap["would_change"])

        eu = frameworks["EU AI Act"]
        self.assertFalse(eu["applicable"])
        self.assertTrue(eu["why_not"], "a non-applicable framework must say why not")
        self.assertTrue(any("jurisdiction" in r.lower() for r in eu["why_not"]))

    def test_risk_profile_derived_for_discovery_only_system(self):
        sid = "skyquery-facts-test"
        self._seed_discovery_only_system(
            sid,
            [{
                "capability_id": "CAP-risk01",
                "name": "execute_sql",
                "action_type": "execute",
                "external_side_effect": True,
            }],
        )
        profile = self.client.get(f"/systems/{sid}/risk-profile").json()["risk_profile"]
        self.assertIsNotNone(profile["use_case"])
        self.assertEqual(profile["environment"], "local")
        self.assertTrue(profile["external_side_effects"])

    def test_assessment_framework_status_not_applicable_without_boundary(self):
        """Guards the inverse: no ACAP and no approvals must still read not_applicable."""
        sid = "facts-empty-system"
        self._seed_discovery_only_system(sid, [])
        assessment = self.client.post(f"/systems/{sid}/assessments/run").json()
        statuses = {f["framework"]: f["status"] for f in assessment["framework_status"]}
        self.assertEqual(statuses["ACAP"], "not_applicable")

    def test_reviewed_acap_system_applicability_is_unchanged_by_facts(self):
        """The six fixture systems must be unaffected by facts enrichment."""
        frameworks = {
            f["framework"]: f
            for f in self.client.get(
                "/systems/restaurant-agent/framework-applicability"
            ).json()["frameworks"]
        }
        self.assertTrue(frameworks["ACAP"]["applicable"])
        self.assertIn("reviewed ACAP", frameworks["ACAP"]["reason"])
        self.assertIn("6 tools", frameworks["ACAP"]["reason"])
        profile = self.client.get("/systems/restaurant-agent/risk-profile").json()["risk_profile"]
        self.assertEqual(profile["use_case"], "Restaurant ordering assistant for local test use.")
        self.assertEqual(profile["authority_level"], "delegated")
        self.assertEqual(profile["human_approval_model"], "required_for_writes")


    # ---- Assessment inputs / EU AI Act ----

    def test_assessment_inputs_round_trip_and_validation(self):
        sid = "inputs-system"
        self._seed_discovery_only_system(sid, [])

        empty = self.client.get(f"/systems/{sid}/assessment-inputs").json()
        self.assertIsNone(empty["jurisdiction"])
        self.assertFalse(empty["high_risk_category"])

        saved = self.client.put(
            f"/systems/{sid}/assessment-inputs",
            json={
                "jurisdiction": "EU",
                "use_case": "Aviation data assistant",
                "high_risk_category": True,
                "data_sensitivity": "medium",
            },
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["jurisdiction"], "EU")
        self.assertTrue(saved.json()["high_risk_category"])

        self.assertEqual(
            self.client.put(f"/systems/{sid}/assessment-inputs",
                            json={"jurisdiction": "Mars"}).status_code, 422)
        self.assertEqual(
            self.client.put(f"/systems/{sid}/assessment-inputs",
                            json={"data_sensitivity": "spicy"}).status_code, 422)

    def test_eu_ai_act_becomes_applicable_from_declared_inputs(self):
        sid = "eu-inputs-system"
        self._seed_discovery_only_system(
            sid, [{"capability_id": "CAP-eu01", "name": "fetch_opensky_response"}]
        )

        def eu():
            frameworks = self.client.get(
                f"/systems/{sid}/framework-applicability"
            ).json()["frameworks"]
            return {f["framework"]: f for f in frameworks}["EU AI Act"]

        self.assertFalse(eu()["applicable"])

        self.client.put(
            f"/systems/{sid}/assessment-inputs",
            json={
                "jurisdiction": "EU",
                "use_case": "Aviation data assistant",
                "high_risk_category": True,
                "data_sensitivity": "medium",
            },
        )
        entry = eu()
        self.assertTrue(entry["applicable"])
        self.assertIn("EU jurisdiction", entry["reason"])
        self.assertTrue(any("high-risk" in w.lower() for w in entry["why"]))

        assessment = self.client.post(f"/systems/{sid}/assessments/run").json()
        statuses = {f["framework"]: f["status"] for f in assessment["framework_status"]}
        self.assertEqual(statuses["EU AI Act"], "needs_review")
        self.assertEqual(statuses["ACAP"], "not_applicable")  # nothing approved here

    def test_jurisdiction_alone_does_not_make_eu_applicable(self):
        """High-risk classification is required too -- jurisdiction is not enough."""
        sid = "eu-partial-system"
        self._seed_discovery_only_system(sid, [])
        self.client.put(
            f"/systems/{sid}/assessment-inputs", json={"jurisdiction": "EU"}
        )
        frameworks = {
            f["framework"]: f
            for f in self.client.get(f"/systems/{sid}/framework-applicability").json()["frameworks"]
        }
        self.assertFalse(frameworks["EU AI Act"]["applicable"])

    def test_kill_switch_alone_never_makes_eu_applicable(self):
        """Runtime controls are evidence inside a review, never a trigger for one."""
        sid = "eu-killswitch-system"
        self._seed_discovery_only_system(
            sid, [{"capability_id": "CAP-ks01", "name": "fetch_opensky_response"}]
        )
        self.client.post(
            f"/systems/{sid}/kill-switches",
            json={
                "kill_switch_id": "ks-opensky",
                "target_capabilities": ["fetch_opensky_response"],
                "enabled": True,
            },
        )
        frameworks = {
            f["framework"]: f
            for f in self.client.get(f"/systems/{sid}/framework-applicability").json()["frameworks"]
        }
        self.assertFalse(frameworks["EU AI Act"]["applicable"])
        self.assertEqual(frameworks["EU AI Act"].get("runtime_control_evidence", []), [])

    def test_declared_inputs_populate_the_risk_profile(self):
        sid = "inputs-risk-system"
        self._seed_discovery_only_system(sid, [])
        self.client.put(
            f"/systems/{sid}/assessment-inputs",
            json={
                "jurisdiction": "India",
                "use_case": "Healthcare",
                "data_sensitivity": "high",
            },
        )
        profile = self.client.get(f"/systems/{sid}/risk-profile").json()["risk_profile"]
        self.assertEqual(profile["jurisdiction"], "India")
        self.assertEqual(profile["use_case"], "Healthcare")
        self.assertEqual(profile["data_sensitivity"], "high")

    def test_declared_inputs_cannot_override_a_reviewed_acap(self):
        """A reviewed ACAP's purpose must win over a declared use case."""
        self.client.put(
            "/systems/restaurant-agent/assessment-inputs",
            json={"jurisdiction": "EU", "use_case": "Finance", "high_risk_category": True},
        )
        profile = self.client.get(
            "/systems/restaurant-agent/risk-profile"
        ).json()["risk_profile"]
        self.assertEqual(
            profile["use_case"], "Restaurant ordering assistant for local test use."
        )

    # ---- Risk, applicability, assessment tests ----

    def test_risk_profile_for_restaurant_agent(self):
        response = self.client.get("/systems/restaurant-agent/risk-profile")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["system_id"], "restaurant-agent")
        profile = body["risk_profile"]
        self.assertEqual(profile["environment"], "local")
        self.assertEqual(profile["authority_level"], "delegated")
        self.assertEqual(profile["autonomy_level"], "human_in_loop")
        self.assertEqual(profile["data_sensitivity"], "medium")
        self.assertTrue(profile["external_side_effects"])
        self.assertEqual(profile["human_approval_model"], "required_for_writes")
        self.assertIsNone(profile["jurisdiction"])

    def test_framework_applicability_rules(self):
        response = self.client.get("/systems/restaurant-agent/framework-applicability")
        self.assertEqual(response.status_code, 200, response.text)
        frameworks = {f["framework"]: f for f in response.json()["frameworks"]}
        self.assertTrue(frameworks["ACAP"]["applicable"])
        self.assertTrue(frameworks["OWASP Agentic"]["applicable"])
        self.assertTrue(frameworks["NIST AI RMF"]["applicable"])
        self.assertFalse(frameworks["EU AI Act"]["applicable"])
        self.assertEqual(frameworks["ISO/IEC 42001"]["applicable"], "informational")

    def test_assessment_combines_all_signals(self):
        self.replay_events()
        self.client.post("/rules/run")
        response = self.client.get("/systems/restaurant-agent/assessment")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["system_id"], "restaurant-agent")
        self.assertEqual(body["acap_status"], "reviewed")
        self.assertIn("risk_profile", body)
        self.assertIn("evidence_summary", body)
        self.assertIn("findings_summary", body)
        self.assertIn("framework_applicability", body)
        self.assertEqual(body["findings_summary"]["total"], 1)
        self.assertIn("AGT-AUTH-001", body["findings_summary"]["failed_controls"])
        self.assertEqual(body["evidence_summary"]["event_count"], event_count())
        self.assertEqual(body["evidence_summary"]["coverage"]["total_fields"], 17)

    def test_existing_finding_still_produced(self):
        self.replay_events()
        run = self.client.post("/rules/run")
        self.assertEqual(run.status_code, 200)
        self.assertEqual(run.json()["findings"][0]["finding_id"], "F-06236c96da2c")

    # ---- Assessment run workflow tests ----

    def test_run_assessment_produces_stable_id(self):
        self.replay_events()
        self.client.post("/rules/run")
        response = self.client.post("/systems/restaurant-agent/assessments/run")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["assessment_id"].startswith("A-"))
        self.assertIn("assessed_at", body)
        self.assertIn("overall_status", body)
        self.assertIn("evidence_confidence", body)
        self.assertIn("framework_status", body)
        self.assertIn("recommended_next_actions", body)

    def test_assessment_includes_current_finding(self):
        self.replay_events()
        self.client.post("/rules/run")
        response = self.client.post("/systems/restaurant-agent/assessments/run")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["findings_summary"]["total"], 1)
        self.assertIn("AGT-AUTH-001", body["findings_summary"]["failed_controls"])

    def test_assessment_status_requires_remediation(self):
        self.replay_events()
        self.client.post("/rules/run")
        response = self.client.post("/systems/restaurant-agent/assessments/run")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["overall_status"], "requires_remediation")

    def test_assessment_framework_status(self):
        self.replay_events()
        self.client.post("/rules/run")
        response = self.client.post("/systems/restaurant-agent/assessments/run")
        self.assertEqual(response.status_code, 200)
        fw = {f["framework"]: f["status"] for f in response.json()["framework_status"]}
        self.assertEqual(fw["ACAP"], "failed")
        self.assertEqual(fw["EU AI Act"], "not_applicable")
        self.assertEqual(fw["ISO/IEC 42001"], "informational")

    def test_list_assessments(self):
        self.replay_events()
        self.client.post("/rules/run")
        self.client.post("/systems/restaurant-agent/assessments/run")
        self.client.post("/systems/restaurant-agent/assessments/run")
        response = self.client.get("/systems/restaurant-agent/assessments")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 2)
        # Most recent first
        self.assertGreaterEqual(
            body["assessments"][0]["created_at"],
            body["assessments"][1]["created_at"],
        )

    def test_get_assessment_by_id(self):
        self.replay_events()
        self.client.post("/rules/run")
        run = self.client.post("/systems/restaurant-agent/assessments/run")
        aid = run.json()["assessment_id"]
        response = self.client.get(f"/assessments/{aid}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["assessment_id"], aid)
        self.assertEqual(response.json()["system_id"], "restaurant-agent")


    # ---- Demo reset tests ----

    def test_demo_reset(self):
        response = self.client.post("/demo/reset")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["events_replayed"], demo_event_count())
        self.assertGreaterEqual(body["findings_created"], 1)
        self.assertEqual(body["systems"], len(DEMO_SYSTEM_IDS))
        # Verify F-06236c96da2c is present for restaurant-agent
        findings = self.client.get("/findings", params={"system_id": "restaurant-agent"})
        self.assertEqual(findings.status_code, 200)
        ids = [f["finding_id"] for f in findings.json()["findings"]]
        self.assertIn("F-06236c96da2c", ids)

    def test_demo_reset_is_idempotent(self):
        r1 = self.client.post("/demo/reset")
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.post("/demo/reset")
        self.assertEqual(r2.status_code, 200)
        findings = self.client.get("/findings", params={"system_id": "restaurant-agent"})
        ids = [f["finding_id"] for f in findings.json()["findings"]]
        self.assertIn("F-06236c96da2c", ids)

    # ---- Multi-system tests ----

    def test_list_systems_returns_demo_systems(self):
        response = self.client.get("/systems")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], len(DEMO_SYSTEM_IDS))
        ids = {s["system_id"] for s in body["systems"]}
        self.assertEqual(ids, DEMO_SYSTEM_IDS)

    def test_refund_agent_has_own_acap(self):
        response = self.client.get("/systems/customer-refund-agent/acap")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["system"]["system_id"], "customer-refund-agent")
        self.assertEqual(body["acap"]["acap_id"], "customer-refund-agent-reviewed")
        self.assertIn("refund_execute", body["acap"]["approval_required_tools"])

    def test_refund_agent_finding(self):
        self.client.post("/demo/reset")
        findings = self.client.get("/findings", params={"system_id": "customer-refund-agent"})
        self.assertEqual(findings.status_code, 200)
        body = findings.json()
        self.assertGreaterEqual(body["count"], 1)
        finding = body["findings"][0]
        self.assertEqual(finding["rule_id"], "R_write_no_approval")
        self.assertIn("refund_execute", finding["description"])
        self.assertEqual(finding["failed_control"], "AGT-AUTH-001")

    def test_restaurant_finding_unchanged(self):
        self.client.post("/demo/reset")
        findings = self.client.get("/findings", params={"system_id": "restaurant-agent"})
        self.assertEqual(findings.status_code, 200)
        ids = [f["finding_id"] for f in findings.json()["findings"]]
        self.assertIn("F-06236c96da2c", ids)

    def test_demo_reset_both_systems(self):
        response = self.client.post("/demo/reset")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["systems"], len(DEMO_SYSTEM_IDS))
        system_ids = {a["system_id"] for a in body["assessments"]}
        self.assertEqual(system_ids, DEMO_SYSTEM_IDS)

    def test_demo_reset_replays_adapter_demo_traces(self):
        self.client.post("/demo/reset")
        response = self.client.get("/evidence/events", params={"limit": 5000})
        self.assertEqual(response.status_code, 200, response.text)
        events = response.json()["events"]
        by_system: dict[str, list[dict]] = {}
        for event in events:
            by_system.setdefault(event["system_id"], []).append(event)
        self.assertEqual(set(by_system), DEMO_SYSTEM_IDS)
        self.assertTrue(any(e["event_type"] == "tool_start" for e in by_system["custom-python-refund-agent"]))
        self.assertTrue(any(e["event_type"] == "llm_start" for e in by_system["openai-direct-agent"]))
        self.assertTrue(any(e["event_type"] == "llm_start" for e in by_system["anthropic-direct-agent"]))
        self.assertTrue(
            any((e.get("component") or {}).get("name", "").startswith("http:") for e in by_system["support-api"])
        )


    # ---- Assessment report tests ----

    def test_assessment_report_markdown(self):
        self.client.post("/demo/reset")
        response = self.client.get("/systems/restaurant-agent/assessment-report.md")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("text/markdown", response.headers.get("content-type", ""))
        body = response.text
        self.assertIn("# AI Governance Assessment Report", body)
        self.assertIn("restaurant-agent", body)
        self.assertIn("Executive Summary", body)
        self.assertIn("Risk Profile", body)
        self.assertIn("Reviewed ACAP Summary", body)
        self.assertIn("Evidence Coverage", body)
        self.assertIn("Findings", body)
        self.assertIn("Framework Applicability", body)
        self.assertIn("Recommended Actions", body)
        self.assertIn("Limitations", body)
        self.assertIn("AGT-AUTH-001", body)
        self.assertIn("F-06236c96da2c", body)

    def test_report_no_raw_text(self):
        self.client.post("/demo/reset")
        body = self.client.get("/systems/restaurant-agent/assessment-report.md").text
        self.assertNotIn("restaurant waiter bot", body.lower())
        self.assertNotIn("I want to order", body)
        self.assertNotIn("ignore all", body.lower())

    def test_refund_report(self):
        self.client.post("/demo/reset")
        response = self.client.get("/systems/customer-refund-agent/assessment-report.md")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("customer-refund-agent", body)
        self.assertIn("refund_execute", body)


    # ---- /findings filter regression tests ----

    def test_findings_no_filter_returns_200(self):
        self.client.post("/demo/reset")
        r = self.client.get("/findings")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["count"], 1)

    def test_findings_filter_restaurant(self):
        self.client.post("/demo/reset")
        r = self.client.get("/findings", params={"system_id": "restaurant-agent"})
        self.assertEqual(r.status_code, 200)
        ids = [f["finding_id"] for f in r.json()["findings"]]
        self.assertIn("F-06236c96da2c", ids)

    def test_findings_filter_refund(self):
        self.client.post("/demo/reset")
        r = self.client.get("/findings", params={"system_id": "customer-refund-agent"})
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["count"], 1)
        self.assertEqual(r.json()["findings"][0]["rule_id"], "R_write_no_approval")

    def test_findings_filter_unknown_returns_empty(self):
        self.client.post("/demo/reset")
        r = self.client.get("/findings", params={"system_id": "unknown-system"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 0)


    # ---- Discovery / Capability Review tests ----

    def test_upload_discovery_stores_candidates(self):
        result = self.upload_discovery()
        self.assertEqual(result["candidates_stored"], 2)
        self.assertEqual(result["system_id"], "test-system")
        self.assertIn("upload_id", result)

    def test_upload_discovery_returns_count(self):
        result = self.upload_discovery()
        self.assertEqual(result["candidates_stored"], 2)

    def test_get_discovery_returns_candidates(self):
        self.upload_discovery()
        r = self.client.get("/systems/test-system/discovery")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body["capabilities"]), 2)
        self.assertIn("scan_summary", body)
        self.assertEqual(body["scan_summary"]["candidates_found"], 2)

    def test_get_discovery_returns_model_surface(self):
        self.upload_discovery()
        r = self.client.get("/systems/test-system/discovery")
        body = r.json()
        self.assertEqual(len(body["model_surface"]), 1)
        self.assertEqual(body["model_surface"][0]["provider"], "openai")

    def test_approve_sets_status_approved_for_acap(self):
        self.upload_discovery()
        r = self.client.post("/systems/test-system/capabilities/CAP-test-001/approve")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["review_status"], "approved_for_acap")

    def test_reject_sets_status_rejected(self):
        self.upload_discovery()
        r = self.client.post("/systems/test-system/capabilities/CAP-test-002/reject")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["review_status"], "rejected")

    def test_not_a_capability_sets_status_false_positive(self):
        self.upload_discovery()
        r = self.client.post("/systems/test-system/capabilities/CAP-test-002/not-a-capability")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["review_status"], "false_positive")

    def test_edit_updates_fields_and_sets_edited(self):
        self.upload_discovery()
        r = self.client.post(
            "/systems/test-system/capabilities/CAP-test-001/edit",
            json={"action_type": "execute", "risk": "medium"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["review_status"], "edited")
        self.assertEqual(body["suggested_action_type"], "execute")
        self.assertEqual(body["risk"], "medium")

    def test_review_provenance_stored(self):
        self.upload_discovery()
        self.client.post("/systems/test-system/capabilities/CAP-test-001/approve")
        r = self.client.get("/systems/test-system/discovery")
        cap = next(c for c in r.json()["capabilities"] if c["capability_id"] == "CAP-test-001")
        self.assertEqual(cap["review_status"], "approved_for_acap")

    def test_review_provenance_has_previous_values(self):
        self.upload_discovery()
        self.client.post("/systems/test-system/capabilities/CAP-test-001/approve")
        r = self.client.post(
            "/systems/test-system/capabilities/CAP-test-001/edit",
            json={"risk": "low"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["review_status"], "edited")
        self.assertEqual(r.json()["risk"], "low")

    def test_pending_does_not_become_acap_automatically(self):
        self.upload_discovery()
        r = self.client.get("/systems/test-system/discovery")
        for cap in r.json()["capabilities"]:
            self.assertEqual(cap["review_status"], "pending",
                             f"{cap['capability_id']} should be pending")

    def test_discovery_grouped_by_risk(self):
        self.upload_discovery()
        r = self.client.get("/systems/test-system/discovery")
        risks = {c["risk"] for c in r.json()["capabilities"]}
        self.assertIn("high", risks)
        self.assertIn("medium", risks)

    def test_unknown_capability_returns_404(self):
        self.upload_discovery()
        r = self.client.post("/systems/test-system/capabilities/CAP-nonexistent/approve")
        self.assertEqual(r.status_code, 404)

    def test_upload_invalid_discovery_rejected(self):
        r = self.client.post("/discovery/upload", json={
            "system_id": "test-system",
            "discovery": {"no_schema": True},
        })
        self.assertEqual(r.status_code, 400)

    def test_demo_reset_with_discovery_tables(self):
        self.upload_discovery()
        r = self.client.post("/demo/reset")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertGreaterEqual(r.json()["events_replayed"], 1)

    # ---- ACAP version generation tests ----

    def _setup_reviewed_discovery(self):
        """Upload discovery and review all capabilities."""
        self.upload_discovery()
        self.client.post("/systems/test-system/capabilities/CAP-test-001/approve")
        self.client.post("/systems/test-system/capabilities/CAP-test-002/reject")

    def test_generate_acap_from_discovery(self):
        self._setup_reviewed_discovery()
        r = self.client.post("/systems/test-system/acap/generate-from-discovery")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("acap_version_id", body)
        self.assertEqual(body["system_id"], "test-system")
        self.assertEqual(body["status"], "generated")
        self.assertEqual(body["version_number"], 1)

    def test_approved_in_allowed_capabilities(self):
        self._setup_reviewed_discovery()
        r = self.client.post("/systems/test-system/acap/generate-from-discovery")
        body = r.json()
        allowed_ids = [c["capability_id"] for c in body["allowed_capabilities"]]
        self.assertIn("CAP-test-001", allowed_ids)
        self.assertNotIn("CAP-test-002", allowed_ids)

    def test_rejected_in_denied_capabilities(self):
        self._setup_reviewed_discovery()
        r = self.client.post("/systems/test-system/acap/generate-from-discovery")
        body = r.json()
        denied_ids = [c["capability_id"] for c in body["denied_capabilities"]]
        self.assertIn("CAP-test-002", denied_ids)
        self.assertNotIn("CAP-test-001", denied_ids)

    def test_false_positives_excluded(self):
        self.upload_discovery()
        self.client.post("/systems/test-system/capabilities/CAP-test-001/approve")
        self.client.post("/systems/test-system/capabilities/CAP-test-002/not-a-capability")
        r = self.client.post("/systems/test-system/acap/generate-from-discovery")
        body = r.json()
        all_ids = [c["capability_id"] for c in body["allowed_capabilities"] + body["denied_capabilities"]]
        self.assertNotIn("CAP-test-002", all_ids)
        self.assertEqual(body["excluded"]["false_positive_count"], 1)

    def test_pending_excluded_and_counted(self):
        self.upload_discovery()
        # leave both pending
        r = self.client.post("/systems/test-system/acap/generate-from-discovery")
        body = r.json()
        self.assertEqual(len(body["allowed_capabilities"]), 0)
        self.assertEqual(len(body["denied_capabilities"]), 0)
        self.assertEqual(body["unresolved"]["pending_count"], 2)

    def test_version_is_immutable(self):
        self._setup_reviewed_discovery()
        r1 = self.client.post("/systems/test-system/acap/generate-from-discovery")
        vid = r1.json()["acap_version_id"]
        r2 = self.client.get(f"/systems/test-system/acap/versions/{vid}")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json()["allowed_capabilities"], r2.json()["allowed_capabilities"])
        self.assertEqual(r1.json()["denied_capabilities"], r2.json()["denied_capabilities"])

    def test_second_generation_creates_new_version(self):
        self._setup_reviewed_discovery()
        r1 = self.client.post("/systems/test-system/acap/generate-from-discovery")
        r2 = self.client.post("/systems/test-system/acap/generate-from-discovery")
        self.assertEqual(r1.json()["version_number"], 1)
        self.assertEqual(r2.json()["version_number"], 2)
        self.assertNotEqual(r1.json()["acap_version_id"], r2.json()["acap_version_id"])

    def test_review_provenance_included(self):
        self._setup_reviewed_discovery()
        r = self.client.post("/systems/test-system/acap/generate-from-discovery")
        body = r.json()
        self.assertIn("review_summary", body)
        self.assertGreaterEqual(body["review_summary"]["review_count"], 2)

    def test_model_surface_not_in_allowed(self):
        self._setup_reviewed_discovery()
        r = self.client.post("/systems/test-system/acap/generate-from-discovery")
        body = r.json()
        allowed_names = [c["name"] for c in body["allowed_capabilities"]]
        self.assertNotIn("generate_reply", allowed_names)
        self.assertIn("model_surface", body)
        providers = [m["provider"] for m in body["model_surface"]]
        self.assertIn("openai", providers)

    def test_list_acap_versions(self):
        self._setup_reviewed_discovery()
        self.client.post("/systems/test-system/acap/generate-from-discovery")
        r = self.client.get("/systems/test-system/acap/versions")
        self.assertEqual(r.status_code, 200)
        versions = r.json()["versions"]
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["version_number"], 1)

    def test_generate_without_discovery_returns_404(self):
        r = self.client.post("/systems/no-system/acap/generate-from-discovery")
        self.assertEqual(r.status_code, 404)

    # ---- ACAP runtime comparison rule tests ----

    def _make_tool_event(self, system_id: str, tool_name: str, *,
                         approval: dict | None = None,
                         data_classes: list[str] | None = None) -> dict:
        """Build a minimal valid governance tool_start event."""
        eid = str(uuid.uuid4())
        tid = str(uuid.uuid4())
        sid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        event: dict = {
            "schema_version": "0.1",
            "event_id": eid,
            "timestamp": now,
            "system_id": system_id,
            "deployment_id": "test",
            "environment": "test",
            "event_type": "tool_start",
            "trace_id": tid,
            "span_id": sid,
            "source": {"type": "test"},
            "outcome": {"status": "started"},
            "tool": {"name": tool_name},
            "component": {"kind": "tool", "name": tool_name},
        }
        if approval:
            event["approval"] = approval
        if data_classes:
            event["data"] = {"classifications": data_classes}
        return event

    def _ingest_event(self, event: dict) -> None:
        r = self.client.post("/evidence/events", json={"event": event})
        self.assertIn(r.status_code, (200, 201), r.text)

    def _setup_acap_and_events(self, *, extra_events: list[dict] | None = None):
        """Upload discovery, review, generate ACAP, ingest events."""
        self._setup_reviewed_discovery()
        self.client.post("/systems/test-system/acap/generate-from-discovery")
        for ev in (extra_events or []):
            self._ingest_event(ev)

    def test_approved_capability_no_unapproved_finding(self):
        ev = self._make_tool_event("test-system", "refund_execute")
        self._setup_acap_and_events(extra_events=[ev])
        r = self.client.post("/systems/test-system/rules/run-acap")
        self.assertEqual(r.status_code, 200, r.text)
        unapproved = [f for f in r.json()["findings"]
                       if f["rule_id"] == "R_ACAP_unapproved_observed"]
        names = [f["capability_name"] for f in unapproved]
        self.assertNotIn("refund_execute", names)

    def test_unapproved_capability_creates_finding(self):
        ev = self._make_tool_event("test-system", "unknown_tool")
        self._setup_acap_and_events(extra_events=[ev])
        r = self.client.post("/systems/test-system/rules/run-acap")
        unapproved = [f for f in r.json()["findings"]
                       if f["rule_id"] == "R_ACAP_unapproved_observed"]
        names = [f["capability_name"] for f in unapproved]
        self.assertIn("unknown_tool", names)

    def test_denied_capability_creates_high_finding(self):
        ev = self._make_tool_event("test-system", "get_report")
        self._setup_acap_and_events(extra_events=[ev])
        r = self.client.post("/systems/test-system/rules/run-acap")
        denied = [f for f in r.json()["findings"]
                   if f["rule_id"] == "R_ACAP_denied_observed"]
        names = [f["capability_name"] for f in denied]
        self.assertIn("get_report", names)
        self.assertEqual(denied[0]["severity"], "high")

    def test_denied_not_also_unapproved(self):
        """Denied tool should not duplicate as unapproved."""
        ev = self._make_tool_event("test-system", "get_report")
        self._setup_acap_and_events(extra_events=[ev])
        r = self.client.post("/systems/test-system/rules/run-acap")
        unapproved = [f for f in r.json()["findings"]
                       if f["rule_id"] == "R_ACAP_unapproved_observed"
                       and f["capability_name"] == "get_report"]
        self.assertEqual(len(unapproved), 0)

    def test_approval_required_missing_creates_finding(self):
        # refund_execute has approval_required=True in SAMPLE_DISCOVERY
        ev = self._make_tool_event("test-system", "refund_execute",
                                    approval={"granted": True})  # granted alone not trusted
        self._setup_acap_and_events(extra_events=[ev])
        r = self.client.post("/systems/test-system/rules/run-acap")
        appr = [f for f in r.json()["findings"]
                 if f["rule_id"] == "R_ACAP_approval_required_missing"]
        names = [f["capability_name"] for f in appr]
        self.assertIn("refund_execute", names)
        self.assertIn("not trusted", appr[0]["description"])

    def test_trusted_approval_no_finding(self):
        ev = self._make_tool_event("test-system", "refund_execute",
                                    approval={"granted": True, "verified": True})
        self._setup_acap_and_events(extra_events=[ev])
        r = self.client.post("/systems/test-system/rules/run-acap")
        appr = [f for f in r.json()["findings"]
                 if f["rule_id"] == "R_ACAP_approval_required_missing"
                 and f["capability_name"] == "refund_execute"]
        self.assertEqual(len(appr), 0)

    def test_false_positive_does_not_authorize(self):
        """A capability marked false_positive should not authorize runtime use."""
        self.upload_discovery()
        self.client.post("/systems/test-system/capabilities/CAP-test-001/not-a-capability")
        self.client.post("/systems/test-system/capabilities/CAP-test-002/reject")
        self.client.post("/systems/test-system/acap/generate-from-discovery")
        ev = self._make_tool_event("test-system", "refund_execute")
        self._ingest_event(ev)
        r = self.client.post("/systems/test-system/rules/run-acap")
        unapproved = [f for f in r.json()["findings"]
                       if f["rule_id"] == "R_ACAP_unapproved_observed"
                       and f["capability_name"] == "refund_execute"]
        self.assertGreater(len(unapproved), 0, "false_positive should not authorize")

    def test_pending_does_not_authorize(self):
        """A pending capability should not authorize runtime use."""
        self.upload_discovery()
        # leave CAP-test-001 pending, reject CAP-test-002
        self.client.post("/systems/test-system/capabilities/CAP-test-002/reject")
        self.client.post("/systems/test-system/acap/generate-from-discovery")
        ev = self._make_tool_event("test-system", "refund_execute")
        self._ingest_event(ev)
        r = self.client.post("/systems/test-system/rules/run-acap")
        unapproved = [f for f in r.json()["findings"]
                       if f["rule_id"] == "R_ACAP_unapproved_observed"
                       and f["capability_name"] == "refund_execute"]
        self.assertGreater(len(unapproved), 0, "pending should not authorize")

    def test_findings_pin_to_acap_version(self):
        ev = self._make_tool_event("test-system", "unknown_tool")
        self._setup_acap_and_events(extra_events=[ev])
        r = self.client.post("/systems/test-system/rules/run-acap")
        body = r.json()
        self.assertIn("acap_version_id", body)
        for f in body["findings"]:
            self.assertIn("acap_version_id", f)
            self.assertIn("acap_version_number", f)

    def test_run_acap_rules_without_acap_returns_404(self):
        r = self.client.post("/systems/no-system/rules/run-acap")
        self.assertEqual(r.status_code, 404)

    def test_legacy_r1_finding_still_works(self):
        """Ensure existing restaurant-agent finding F-06236c96da2c is still produced."""
        self.client.post("/demo/reset")
        r = self.client.get("/findings", params={"system_id": "restaurant-agent"})
        self.assertEqual(r.status_code, 200)
        ids = [f["finding_id"] for f in r.json()["findings"]]
        self.assertIn("F-06236c96da2c", ids)

    # ---- Governance manifest generation tests ----

    def test_manifest_yaml_from_approved_capabilities(self):
        self._setup_reviewed_discovery()
        self.client.post("/systems/test-system/acap/generate-from-discovery")
        r = self.client.get("/systems/test-system/governance-manifest.yaml")
        self.assertEqual(r.status_code, 200)
        self.assertIn("yaml", r.headers.get("content-type", ""))
        import yaml
        manifest = yaml.safe_load(r.text)
        self.assertEqual(manifest["system_id"], "test-system")
        names = [c["name"] for c in manifest["capabilities"]]
        self.assertIn("refund_execute", names)

    def test_manifest_json_from_approved_capabilities(self):
        self._setup_reviewed_discovery()
        self.client.post("/systems/test-system/acap/generate-from-discovery")
        r = self.client.get("/systems/test-system/governance-manifest.json")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        names = [c["name"] for c in body["capabilities"]]
        self.assertIn("refund_execute", names)

    def test_manifest_excludes_denied(self):
        self._setup_reviewed_discovery()
        self.client.post("/systems/test-system/acap/generate-from-discovery")
        r = self.client.get("/systems/test-system/governance-manifest.json")
        names = [c["name"] for c in r.json()["capabilities"]]
        self.assertNotIn("get_report", names)  # rejected → denied

    def test_manifest_excludes_false_positive(self):
        self.upload_discovery()
        self.client.post("/systems/test-system/capabilities/CAP-test-001/not-a-capability")
        self.client.post("/systems/test-system/capabilities/CAP-test-002/reject")
        self.client.post("/systems/test-system/acap/generate-from-discovery")
        r = self.client.get("/systems/test-system/governance-manifest.json")
        names = [c["name"] for c in r.json()["capabilities"]]
        self.assertNotIn("refund_execute", names)

    def test_manifest_excludes_pending(self):
        self.upload_discovery()
        # leave both pending
        self.client.post("/systems/test-system/acap/generate-from-discovery")
        r = self.client.get("/systems/test-system/governance-manifest.json")
        self.assertEqual(len(r.json()["capabilities"]), 0)

    def test_manifest_includes_metadata(self):
        self._setup_reviewed_discovery()
        self.client.post("/systems/test-system/acap/generate-from-discovery")
        r = self.client.get("/systems/test-system/governance-manifest.json")
        body = r.json()
        self.assertIn("generated_from", body)
        self.assertEqual(body["generated_from"]["source"], "evidence_api")
        self.assertIn("acap_version_id", body["generated_from"])

    def test_manifest_all_capabilities_status_approved(self):
        self._setup_reviewed_discovery()
        self.client.post("/systems/test-system/acap/generate-from-discovery")
        r = self.client.get("/systems/test-system/governance-manifest.json")
        for cap in r.json()["capabilities"]:
            self.assertEqual(cap["status"], "approved")

    def test_manifest_selected_version_id(self):
        self._setup_reviewed_discovery()
        r1 = self.client.post("/systems/test-system/acap/generate-from-discovery")
        vid = r1.json()["acap_version_id"]
        r = self.client.get(f"/systems/test-system/governance-manifest.json?version_id={vid}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["generated_from"]["acap_version_id"], vid)

    def test_manifest_no_acap_returns_404(self):
        r = self.client.get("/systems/no-system/governance-manifest.json")
        self.assertEqual(r.status_code, 404)

    def test_manifest_loadable_by_sdk(self):
        """Generated manifest can be loaded by the SDK's load_manifest()."""
        import tempfile as _tf
        self._setup_reviewed_discovery()
        self.client.post("/systems/test-system/acap/generate-from-discovery")
        r = self.client.get("/systems/test-system/governance-manifest.yaml")
        with _tf.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(r.text)
            f.flush()
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk-python"))
            from ai_governance.manifest import load_manifest
            config = load_manifest(f.name)
            self.assertEqual(config["system_id"], "test-system")
            self.assertGreater(len(config["capabilities"]), 0)
            for cap in config["capabilities"]:
                self.assertIn("module_path", cap)
                self.assertIn("status", cap)

    # ---- Onboarding / continuous audit tests ----

    def test_discovery_upload_registers_new_system(self):
        """Upload for a new system should make it appear in /systems."""
        self.upload_discovery(system_id="brand-new-system")
        r = self.client.get("/systems")
        ids = [s["system_id"] for s in r.json()["systems"]]
        self.assertIn("brand-new-system", ids)

    def test_systems_includes_discovery_only_system(self):
        self.upload_discovery(system_id="my-custom-app")
        r = self.client.get("/systems")
        found = [s for s in r.json()["systems"] if s["system_id"] == "my-custom-app"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].get("source"), "discovery")

    def test_rescan_produces_changeset(self):
        """Second upload for same system should include changeset in discovery."""
        self.upload_discovery()
        # Modify discovery: add a new candidate
        modified = dict(SAMPLE_DISCOVERY)
        modified["candidates"] = list(SAMPLE_DISCOVERY["candidates"]) + [{
            "capability_id": "CAP-test-003",
            "name": "new_function",
            "module_path": "app",
            "file_path": "app.py",
            "line_start": 20, "line_end": 25,
            "suggested_action_type": "write",
            "suggested_data_classes": [],
            "suggested_approval_required": False,
            "external_side_effect": False,
            "risk": "low",
            "confidence": 0.50,
            "confidence_source": "name_heuristic",
            "evidence": [],
            "call_chain": [],
            "review_status": "pending",
            "source": "deterministic_scanner",
        }]
        self.client.post("/discovery/upload", json={
            "system_id": "test-system", "discovery": modified,
        })
        r = self.client.get("/systems/test-system/discovery")
        body = r.json()
        self.assertIn("changeset", body)
        self.assertIn("new_function", body["changeset"]["new"])

    def test_unchanged_approved_preserved(self):
        """Approved capability should stay approved after unchanged rescan."""
        self.upload_discovery()
        self.client.post("/systems/test-system/capabilities/CAP-test-001/approve")
        # Re-upload same discovery
        self.client.post("/discovery/upload", json={
            "system_id": "test-system", "discovery": SAMPLE_DISCOVERY,
        })
        r = self.client.get("/systems/test-system/discovery")
        cap = next(c for c in r.json()["capabilities"] if c["capability_id"] == "CAP-test-001")
        self.assertEqual(cap["review_status"], "approved_for_acap")

    def test_changed_high_risk_becomes_needs_reapproval(self):
        """Changed high-risk approved capability should need reapproval."""
        self.upload_discovery()
        self.client.post("/systems/test-system/capabilities/CAP-test-001/approve")
        # Re-upload with changed risk
        modified = dict(SAMPLE_DISCOVERY)
        changed_cap = dict(SAMPLE_DISCOVERY["candidates"][0])
        changed_cap["suggested_action_type"] = "execute"  # was "write"
        modified["candidates"] = [changed_cap, SAMPLE_DISCOVERY["candidates"][1]]
        self.client.post("/discovery/upload", json={
            "system_id": "test-system", "discovery": modified,
        })
        r = self.client.get("/systems/test-system/discovery")
        cap = next(c for c in r.json()["capabilities"] if c["capability_id"] == "CAP-test-001")
        self.assertEqual(cap["review_status"], "needs_reapproval")

    def test_needs_reapproval_excluded_from_acap(self):
        """needs_reapproval should not be in allowed_capabilities."""
        self.upload_discovery()
        self.client.post("/systems/test-system/capabilities/CAP-test-001/approve")
        self.client.post("/systems/test-system/capabilities/CAP-test-002/reject")
        # Change CAP-test-001 to trigger needs_reapproval
        modified = dict(SAMPLE_DISCOVERY)
        changed_cap = dict(SAMPLE_DISCOVERY["candidates"][0])
        changed_cap["risk"] = "low"  # was "high"
        modified["candidates"] = [changed_cap, SAMPLE_DISCOVERY["candidates"][1]]
        self.client.post("/discovery/upload", json={
            "system_id": "test-system", "discovery": modified,
        })
        r = self.client.post("/systems/test-system/acap/generate-from-discovery")
        body = r.json()
        allowed_ids = [c["capability_id"] for c in body["allowed_capabilities"]]
        self.assertNotIn("CAP-test-001", allowed_ids)
        self.assertGreater(body["unresolved"]["pending_count"], 0)

    def test_new_candidate_starts_pending(self):
        """New capability from rescan should start as pending."""
        self.upload_discovery()
        modified = dict(SAMPLE_DISCOVERY)
        modified["candidates"] = list(SAMPLE_DISCOVERY["candidates"]) + [{
            "capability_id": "CAP-test-new",
            "name": "brand_new",
            "module_path": "app",
            "file_path": "app.py",
            "line_start": 1, "line_end": 5,
            "suggested_action_type": "read",
            "suggested_data_classes": [],
            "suggested_approval_required": False,
            "external_side_effect": False,
            "risk": "low",
            "confidence": 0.5,
            "confidence_source": "name_heuristic",
            "evidence": [],
            "call_chain": [],
            "review_status": "pending",
            "source": "deterministic_scanner",
        }]
        self.client.post("/discovery/upload", json={
            "system_id": "test-system", "discovery": modified,
        })
        r = self.client.get("/systems/test-system/discovery")
        cap = next(c for c in r.json()["capabilities"] if c["capability_id"] == "CAP-test-new")
        self.assertEqual(cap["review_status"], "pending")

    def test_removed_candidate_in_changeset(self):
        """Removed capability should appear in changeset.removed."""
        self.upload_discovery()
        # Re-upload with one candidate removed
        modified = dict(SAMPLE_DISCOVERY)
        modified["candidates"] = [SAMPLE_DISCOVERY["candidates"][0]]  # only keep first
        self.client.post("/discovery/upload", json={
            "system_id": "test-system", "discovery": modified,
        })
        r = self.client.get("/systems/test-system/discovery")
        body = r.json()
        self.assertIn("changeset", body)
        self.assertIn("get_report", body["changeset"]["removed"])

    def test_audit_status_discovery_missing(self):
        r = self.client.get("/systems/test-system/audit-status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "discovery_missing")

    def test_audit_status_acap_missing(self):
        self.upload_discovery()
        r = self.client.get("/systems/test-system/audit-status")
        self.assertEqual(r.json()["status"], "acap_missing")

    def test_audit_status_up_to_date(self):
        self._setup_reviewed_discovery()
        self.client.post("/systems/test-system/acap/generate-from-discovery")
        ev = self._make_tool_event("test-system", "refund_execute")
        self._ingest_event(ev)
        self.client.post("/systems/test-system/rules/run-acap")
        # Run assessment to mark latest_assessment_at
        self.client.post("/systems/test-system/assessments/run")
        r = self.client.get("/systems/test-system/audit-status")
        # Should be up_to_date or runtime_missing or similar depending on timestamps
        self.assertIn(r.json()["status"], ("up_to_date", "runtime_changed_since_assessment"))

    def test_demo_reset_still_works_with_new_tables(self):
        self.upload_discovery()
        r = self.client.post("/demo/reset")
        self.assertEqual(r.status_code, 200)

    def test_existing_demo_systems_still_listed(self):
        r = self.client.get("/systems")
        ids = [s["system_id"] for s in r.json()["systems"]]
        self.assertIn("restaurant-agent", ids)


if __name__ == "__main__":
    unittest.main()
