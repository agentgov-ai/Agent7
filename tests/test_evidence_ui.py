from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from services.evidence_api.app import app

REPO_ROOT = Path(__file__).resolve().parents[1]
EVENTS = REPO_ROOT / "artifacts" / "governance" / "events.jsonl"
REQUIRED_FINDING_ID = "F-06236c96da2c"
REQUIRED_EVENT_ID = "bef3e128-513d-4484-86d2-603c8916e220"


def event_count() -> int:
    return sum(1 for line in EVENTS.read_text(encoding="utf-8").splitlines() if line.strip())


class EvidenceUiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["EVIDENCE_DB_PATH"] = str(Path(self.tmp.name) / "evidence.db")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.tmp.cleanup()
        os.environ.pop("EVIDENCE_DB_PATH", None)

    def seed_findings(self) -> None:
        replay = self.client.post("/evidence/replay-jsonl", json={"path": str(EVENTS), "reset": True})
        self.assertEqual(replay.status_code, 200, replay.text)
        run = self.client.post("/rules/run", json={"rule_ids": ["R1_confirm_without_proposal"]})
        self.assertEqual(run.status_code, 200, run.text)

    def test_ui_assets_are_served_and_call_expected_endpoints(self):
        page = self.client.get("/ui/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Agent7 Control Center", page.text)

        script = self.client.get("/ui/app.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn('readJson("/health")', script.text)
        self.assertIn('readJson("/findings")', script.text)
        self.assertIn('readJson("/evidence/events?limit=5000")', script.text)
        self.assertIn('readJson("/systems")', script.text)
        self.assertIn("/acap", script.text)
        self.assertIn("/acap/draft", script.text)
        self.assertIn("/coverage", script.text)
        self.assertIn("/risk-profile", script.text)
        self.assertIn("/framework-applicability", script.text)
        self.assertIn("/demo/reset", script.text)

        self.assertIn("System", page.text)
        self.assertIn("Reviewed ACAP", page.text)
        self.assertIn("Tool Authorization", page.text)
        self.assertIn("Evidence Coverage", page.text)
        self.assertIn("Risk Profile", page.text)
        self.assertIn("Framework Applicability", page.text)
        self.assertIn("Latest Assessment", page.text)
        self.assertIn("What Happened", page.text)
        self.assertIn("Why It Matters", page.text)
        self.assertIn("Recommendation", page.text)
        self.assertIn("/assessments", script.text)
        self.assertIn("systemSelector", page.text)
        self.assertIn("systemSelector", script.text)
        self.assertIn("enforcementModeControl", page.text)
        self.assertIn("enforcementModeControl", script.text)
        self.assertIn("/enforcement-mode", script.text)
        self.assertIn("Export Report", page.text)
        self.assertIn("assessment-report.md", script.text)

    def test_ui_required_data_is_available_without_raw_event_payload_fields(self):
        self.seed_findings()

        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["events"], event_count())

        findings = self.client.get("/findings", params={"system_id": "restaurant-agent"})
        self.assertEqual(findings.status_code, 200)
        finding = next(f for f in findings.json()["findings"] if f["finding_id"] == REQUIRED_FINDING_ID)
        self.assertEqual(finding["event_ids"], [REQUIRED_EVENT_ID])

        acap = self.client.get("/systems/restaurant-agent/acap")
        self.assertEqual(acap.status_code, 200)
        self.assertEqual(acap.json()["system"]["system_id"], "restaurant-agent")
        self.assertEqual(acap.json()["acap"]["acap_id"], "restaurant-agent-local-reviewed")
        self.assertIn("confirm_order", acap.json()["acap"]["approval_required_tools"])

        events = self.client.get("/evidence/events", params={"limit": 5000})
        self.assertEqual(events.status_code, 200)
        event = next(item for item in events.json()["events"] if item["event_id"] == REQUIRED_EVENT_ID)
        self.assertNotIn("sanitized_arguments", event["tool"])
        self.assertFalse(event["tool"]["arguments_exposed"])


if __name__ == "__main__":
    unittest.main()
