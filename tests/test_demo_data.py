from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "sdk-python"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from ai_governance import validate_event  # noqa: E402

DEMO_DATA = REPO_ROOT / "examples" / "demo-data"
EXPECTED_SYSTEMS = {
    "restaurant-agent": "restaurant-agent",
    "customer-refund-agent": "customer-refund-agent",
    "custom-python-tool": "custom-python-refund-agent",
    "openai-direct": "openai-direct-agent",
    "anthropic-direct": "anthropic-direct-agent",
    "fastapi-app": "support-api",
}
FORBIDDEN_MARKERS = [
    "customer@example.com",
    "sk-demo-secret",
    "SECRET-PROMPT-TEXT",
    "SECRET-RESPONSE-TEXT",
    "restaurant waiter bot",
    "I want to order",
    "ignore all instructions",
    "Hello from fake OpenAI",
    "Hello from fake Anthropic",
    "Bearer sk-secret",
    "secret-cookie",
]


class DemoDataTest(unittest.TestCase):
    def test_demo_data_files_exist_for_all_systems(self):
        for directory in EXPECTED_SYSTEMS:
            root = DEMO_DATA / directory
            self.assertTrue((root / "events.jsonl").exists(), directory)
            self.assertTrue((root / "acap-reviewed.yaml").exists(), directory)

    def test_demo_events_validate_and_match_expected_system(self):
        for directory, system_id in EXPECTED_SYSTEMS.items():
            path = DEMO_DATA / directory / "events.jsonl"
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertGreater(len(events), 0, directory)
            self.assertEqual({event["system_id"] for event in events}, {system_id})
            for event in events:
                self.assertEqual(validate_event(event), [], event)

    def test_demo_data_does_not_contain_raw_sensitive_markers(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in DEMO_DATA.glob("*/*")
            if path.is_file()
        )
        for marker in FORBIDDEN_MARKERS:
            self.assertNotIn(marker, text)

    def test_fastapi_demo_fixture_does_not_expose_request_body(self):
        text = (DEMO_DATA / "fastapi-app" / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("ORD-1001", text)
        self.assertNotIn('"amount_cents":2599', text)
        self.assertIn('"request_body_exposed":false', text)


if __name__ == "__main__":
    unittest.main()
