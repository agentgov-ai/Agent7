from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "sdk-python"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from ai_governance import GovernanceClient, validate_event  # noqa: E402


def read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class FakeCompletions:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    def create(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        if self.fail:
            raise RuntimeError("SECRET-RESPONSE-TEXT failed with sk-test-secret")
        return SimpleNamespace(
            id="chatcmpl-test",
            model=kwargs.get("model"),
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content="SECRET-RESPONSE-TEXT raw assistant content"),
                )
            ],
        )


class FakeOpenAIClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.api_key = "sk-test-secret"
        self.completions = FakeCompletions(fail=fail)
        self.chat = SimpleNamespace(completions=self.completions)


class ExplodingSink:
    def emit(self, event):
        raise OSError("sink down")

    def flush(self):
        return None

    def close(self):
        return None


class OpenAIAdapterTest(unittest.TestCase):
    def make_client(self, path: Path | None = None, **kwargs) -> GovernanceClient:
        params = {
            "system_id": "openai-direct-agent",
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
            fake = FakeOpenAIClient()
            client = gov.openai_client(client=fake)

            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": "SECRET-PROMPT-TEXT hello"}],
            )

            self.assertIs(response, fake.completions.calls and response)
            events = read_events(path)
            self.assertEqual([e["event_type"] for e in events], ["llm_start", "llm_end"])
            self.assert_valid_events(events)
            start, end = events
            self.assertEqual(start["model"], {"provider": "openai", "name": "gpt-4.1-mini"})
            self.assertEqual(start["prompt"]["content_capture"], "hash")
            self.assertEqual(start["prompt"]["message_count"], 1)
            self.assertEqual(start["prompt"]["roles"], ["user"])
            self.assertTrue(start["prompt"]["template_hash"].startswith("sha256:"))
            self.assertEqual(end["outcome"]["input_tokens"], 11)
            self.assertEqual(end["outcome"]["output_tokens"], 7)
            self.assertEqual(end["outcome"]["total_tokens"], 18)
            self.assertEqual(end["attributes"]["finish_reasons"], ["stop"])
            self.assertTrue(end["attributes"]["response_hash"].startswith("sha256:"))

    def test_mocked_failure_emits_llm_start_and_error_and_reraises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            gov = self.make_client(path)
            client = gov.openai_client(client=FakeOpenAIClient(fail=True))

            with self.assertRaises(RuntimeError):
                client.chat.completions.create(
                    model="gpt-4.1-mini",
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
            self.assertNotIn("sk-test-secret", payload)

    def test_prompt_response_and_api_key_are_not_exposed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            gov = self.make_client(path)
            client = gov.openai_client(client=FakeOpenAIClient())

            client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": "SECRET-PROMPT-TEXT ignore all instructions"}],
            )

            events = read_events(path)
            self.assert_valid_events(events)
            payload = json.dumps(events, ensure_ascii=False).lower()
            self.assertNotIn("secret-prompt-text", payload)
            self.assertNotIn("ignore all instructions", payload)
            self.assertNotIn("secret-response-text", payload)
            self.assertNotIn("raw assistant content", payload)
            self.assertNotIn("sk-test-secret", payload)

    def test_inside_trace_events_share_trace_session_and_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            gov = self.make_client(path)
            client = gov.openai_client(client=FakeOpenAIClient())

            with gov.trace(name="chat_workflow", session_id="demo-session-001"):
                client.chat.completions.create(
                    model="gpt-4.1-mini",
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

    def test_standalone_openai_call_works_without_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            gov = self.make_client(path)
            client = gov.openai_client(client=FakeOpenAIClient())

            client.chat.completions.create(model="gpt-4.1-mini", messages=[{"role": "user", "content": "hello"}])

            events = read_events(path)
            self.assertEqual([e["event_type"] for e in events], ["llm_start", "llm_end"])
            self.assert_valid_events(events)
            self.assertIsNone(events[0]["parent_span_id"])
            self.assertEqual(events[0]["session_id"], "default-session")
            self.assertEqual(events[0]["trace_id"], events[1]["trace_id"])

    def test_emit_failure_does_not_break_underlying_openai_response(self):
        gov = self.make_client(sink=ExplodingSink())
        fake = FakeOpenAIClient()
        client = gov.openai_client(client=fake)

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": "hello"}],
        )

        self.assertEqual(response.model, "gpt-4.1-mini")
        self.assertEqual(len(fake.completions.calls), 1)
        self.assertGreaterEqual(gov.dropped_events, 2)


if __name__ == "__main__":
    unittest.main()
