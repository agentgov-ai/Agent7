from __future__ import annotations

import builtins
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "sdk-python"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from ai_governance import GovernanceClient, validate_event  # noqa: E402


def read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class FakeMessages:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    def create(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        if self.fail:
            raise RuntimeError("SECRET-RESPONSE-TEXT failed with sk-ant-secret")
        return SimpleNamespace(
            id="msg-test",
            model=kwargs.get("model"),
            usage=SimpleNamespace(input_tokens=13, output_tokens=8),
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="SECRET-RESPONSE-TEXT raw assistant content")],
        )


class FakeAnthropicClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.api_key = "sk-ant-secret"
        self.messages = FakeMessages(fail=fail)


class ExplodingSink:
    def emit(self, event):
        raise OSError("sink down")

    def flush(self):
        return None

    def close(self):
        return None


class AnthropicAdapterTest(unittest.TestCase):
    def make_client(self, path: Path | None = None, **kwargs) -> GovernanceClient:
        params = {
            "system_id": "anthropic-direct-agent",
            "deployment_id": "local-test",
            "environment": "test",
            "session_id": "default-session",
        }
        if path is not None:
            params["jsonl_path"] = path
        params.update(kwargs)
        return GovernanceClient(**params)

    def assert_valid_events(self, events: list[dict]) -> None:
        for event in events:
            self.assertEqual(validate_event(event), [], event)

    def test_mocked_success_emits_llm_start_and_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            gov = self.make_client(path)
            fake = FakeAnthropicClient()
            client = gov.anthropic_client(client=fake)

            response = client.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=256,
                messages=[{"role": "user", "content": "SECRET-PROMPT-TEXT hello"}],
            )

            self.assertIs(response, fake.messages.calls and response)
            events = read_events(path)
            self.assertEqual([e["event_type"] for e in events], ["llm_start", "llm_end"])
            self.assert_valid_events(events)
            start, end = events
            self.assertEqual(start["model"], {"provider": "anthropic", "name": "claude-3-5-sonnet-latest"})
            self.assertEqual(start["prompt"]["content_capture"], "hash")
            self.assertEqual(start["prompt"]["message_count"], 1)
            self.assertEqual(start["prompt"]["roles"], ["user"])
            self.assertTrue(start["prompt"]["template_hash"].startswith("sha256:"))
            self.assertEqual(end["outcome"]["input_tokens"], 13)
            self.assertEqual(end["outcome"]["output_tokens"], 8)
            self.assertIsNone(end["outcome"]["total_tokens"])
            self.assertEqual(end["attributes"]["finish_reasons"], ["end_turn"])
            self.assertTrue(end["attributes"]["response_hash"].startswith("sha256:"))

    def test_mocked_failure_emits_llm_start_and_error_and_reraises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            gov = self.make_client(path)
            client = gov.anthropic_client(client=FakeAnthropicClient(fail=True))

            with self.assertRaises(RuntimeError):
                client.messages.create(
                    model="claude-3-5-sonnet-latest",
                    max_tokens=256,
                    messages=[{"role": "user", "content": "hello"}],
                )

            events = read_events(path)
            self.assertEqual([e["event_type"] for e in events], ["llm_start", "llm_error"])
            self.assert_valid_events(events)
            error = events[1]
            self.assertEqual(error["outcome"]["status"], "error")
            self.assertEqual(error["outcome"]["error_type"], "RuntimeError")
            self.assertTrue(error["attributes"]["error_hash"].startswith("sha256:"))
            payload = json.dumps(events, ensure_ascii=False)
            self.assertNotIn("SECRET-RESPONSE-TEXT", payload)
            self.assertNotIn("sk-ant-secret", payload)

    def test_prompt_response_and_api_key_are_not_exposed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            gov = self.make_client(path)
            client = gov.anthropic_client(client=FakeAnthropicClient())

            client.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=256,
                messages=[{"role": "user", "content": "SECRET-PROMPT-TEXT ignore all instructions"}],
            )

            events = read_events(path)
            self.assert_valid_events(events)
            payload = json.dumps(events, ensure_ascii=False).lower()
            self.assertNotIn("secret-prompt-text", payload)
            self.assertNotIn("ignore all instructions", payload)
            self.assertNotIn("secret-response-text", payload)
            self.assertNotIn("raw assistant content", payload)
            self.assertNotIn("sk-ant-secret", payload)

    def test_inside_trace_events_share_trace_session_and_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            gov = self.make_client(path)
            client = gov.anthropic_client(client=FakeAnthropicClient())

            with gov.trace(name="chat_workflow", session_id="demo-session-001"):
                client.messages.create(
                    model="claude-3-5-sonnet-latest",
                    max_tokens=256,
                    messages=[{"role": "user", "content": "hello"}],
                )

            events = read_events(path)
            self.assertEqual([e["event_type"] for e in events], ["chain_start", "llm_start", "llm_end", "chain_end"])
            self.assert_valid_events(events)
            root = events[0]
            for event in events:
                self.assertEqual(event["trace_id"], root["trace_id"])
                self.assertEqual(event["session_id"], "demo-session-001")
            self.assertEqual(events[1]["parent_span_id"], root["span_id"])
            self.assertEqual(events[2]["parent_span_id"], root["span_id"])
            self.assertEqual(events[3]["span_id"], root["span_id"])

    def test_standalone_anthropic_call_works_without_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            gov = self.make_client(path)
            client = gov.anthropic_client(client=FakeAnthropicClient())

            client.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=256,
                messages=[{"role": "user", "content": "hello"}],
            )

            events = read_events(path)
            self.assertEqual([e["event_type"] for e in events], ["llm_start", "llm_end"])
            self.assert_valid_events(events)
            self.assertIsNone(events[0]["parent_span_id"])
            self.assertEqual(events[0]["session_id"], "default-session")
            self.assertEqual(events[0]["trace_id"], events[1]["trace_id"])

    def test_emit_failure_does_not_break_underlying_anthropic_response(self):
        gov = self.make_client(sink=ExplodingSink())
        fake = FakeAnthropicClient()
        client = gov.anthropic_client(client=fake)

        response = client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=256,
            messages=[{"role": "user", "content": "hello"}],
        )

        self.assertEqual(response.model, "claude-3-5-sonnet-latest")
        self.assertEqual(len(fake.messages.calls), 1)
        self.assertGreaterEqual(gov.dropped_events, 2)

    def test_missing_optional_dependency_error_is_clear(self):
        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "anthropic":
                raise ModuleNotFoundError("No module named 'anthropic'", name="anthropic")
            return real_import(name, globals, locals, fromlist, level)

        with tempfile.TemporaryDirectory() as tmp:
            gov = self.make_client(Path(tmp) / "events.jsonl")
            with patch("builtins.__import__", side_effect=fake_import):
                with self.assertRaisesRegex(ImportError, "optional 'anthropic' package"):
                    gov.anthropic_client()


if __name__ == "__main__":
    unittest.main()
