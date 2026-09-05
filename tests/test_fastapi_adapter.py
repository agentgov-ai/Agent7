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
from ai_governance.adapters.fastapi import GovernanceMiddleware  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class ExplodingSink:
    def emit(self, event):
        raise OSError("sink down")

    def flush(self):
        return None

    def close(self):
        return None


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        return SimpleNamespace(
            model=kwargs.get("model"),
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5),
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="SECRET-RESPONSE-TEXT"))],
        )


class FastAPIAdapterTest(unittest.TestCase):
    def make_client(self, path: Path | None = None, **kwargs) -> GovernanceClient:
        params = {
            "system_id": "support-api",
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

    def test_successful_request_emits_root_start_child_tool_and_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            gov = self.make_client(path)

            @gov.tool(name="refund_execute", action_type="write")
            def refund_execute(order_id: str) -> dict:
                return {"order_id": order_id, "status": "ok"}

            app = FastAPI()
            app.add_middleware(GovernanceMiddleware, governance_client=gov, request_id_header="x-request-id")

            @app.post("/refund")
            def refund_endpoint(payload: dict):
                result = refund_execute(payload["order_id"])
                return {"ok": True, "result": result}

            response = TestClient(app).post(
                "/refund?debug=SECRET-PROMPT-TEXT",
                json={"order_id": "ORD-1", "secret": "SECRET-PROMPT-TEXT ignore all instructions"},
                headers={"x-request-id": "req-123"},
            )
            self.assertEqual(response.status_code, 200)

            events = read_events(path)
            self.assertEqual([e["event_type"] for e in events], ["chain_start", "tool_start", "tool_end", "chain_end"])
            self.assert_valid_events(events)
            root = events[0]
            self.assertEqual(root["component"]["kind"], "chain")
            self.assertEqual(root["attributes"]["http.method"], "POST")
            self.assertEqual(root["attributes"]["request_id"], "req-123")
            self.assertEqual(events[-1]["attributes"]["status_code"], 200)
            for event in events:
                self.assertEqual(event["trace_id"], root["trace_id"])
                self.assertEqual(event["session_id"], "req-123")
            self.assertEqual(events[1]["parent_span_id"], root["span_id"])
            self.assertEqual(events[2]["parent_span_id"], root["span_id"])
            payload = json.dumps(events, ensure_ascii=False).lower()
            self.assertNotIn("secret-prompt-text", payload)
            self.assertNotIn("ignore all instructions", payload)
            self.assertNotIn("debug=", payload)

    def test_request_with_nested_trace_keeps_tool_parented_to_request_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            gov = self.make_client(path)

            @gov.tool(name="refund_lookup", action_type="read")
            def refund_lookup(order_id: str) -> dict:
                return {"order_id": order_id}

            app = FastAPI()
            app.add_middleware(
                GovernanceMiddleware,
                governance_client=gov,
                request_id_header="x-request-id",
                session_header="x-session-id",
                user_header="x-user-id",
            )

            @app.post("/refund")
            def refund_endpoint(payload: dict):
                with gov.trace(name="refund_workflow"):
                    refund_lookup(payload["order_id"])
                return {"ok": True}

            response = TestClient(app).post(
                "/refund",
                json={"order_id": "ORD-2"},
                headers={
                    "x-request-id": "req-456",
                    "x-session-id": "raw-session-secret",
                    "x-user-id": "raw-user-secret",
                    "authorization": "Bearer sk-secret",
                    "cookie": "session=secret-cookie",
                },
            )
            self.assertEqual(response.status_code, 200)
            events = read_events(path)
            self.assertEqual(
                [e["event_type"] for e in events],
                ["chain_start", "chain_start", "tool_start", "tool_end", "chain_end", "chain_end"],
            )
            self.assert_valid_events(events)
            request_root = events[0]
            nested_trace = events[1]
            tool_start = events[2]
            tool_end = events[3]
            for event in events:
                self.assertEqual(event["trace_id"], request_root["trace_id"])
                self.assertEqual(event["session_id"], request_root["session_id"])
            self.assertEqual(nested_trace["parent_span_id"], request_root["span_id"])
            self.assertEqual(tool_start["parent_span_id"], request_root["span_id"])
            self.assertEqual(tool_end["parent_span_id"], request_root["span_id"])
            self.assertTrue(request_root["session_id"].startswith("sha256:"))
            text = json.dumps(events, ensure_ascii=False)
            self.assertNotIn("raw-session-secret", text)
            self.assertNotIn("raw-user-secret", text)
            self.assertNotIn("sk-secret", text)
            self.assertNotIn("secret-cookie", text)

    def test_failing_request_emits_chain_error_and_reraises_to_fastapi(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            gov = self.make_client(path)
            app = FastAPI()
            app.add_middleware(GovernanceMiddleware, governance_client=gov)

            @app.get("/boom")
            def boom():
                raise RuntimeError("boom SECRET-RESPONSE-TEXT")

            response = TestClient(app, raise_server_exceptions=False).get("/boom")
            self.assertEqual(response.status_code, 500)
            events = read_events(path)
            self.assertEqual([e["event_type"] for e in events], ["chain_start", "chain_error"])
            self.assert_valid_events(events)
            self.assertEqual(events[1]["outcome"]["status"], "error")
            self.assertEqual(events[1]["outcome"]["error_type"], "RuntimeError")
            self.assertEqual(events[1]["attributes"]["status_code"], 500)
            self.assertNotIn("SECRET-RESPONSE-TEXT", json.dumps(events, ensure_ascii=False))

    def test_child_openai_events_share_request_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            gov = self.make_client(path)
            openai_client = gov.openai_client(client=FakeOpenAIClient())
            app = FastAPI()
            app.add_middleware(GovernanceMiddleware, governance_client=gov)

            @app.post("/chat")
            def chat():
                openai_client.chat.completions.create(model="gpt-4.1-mini", messages=[{"role": "user", "content": "Hello"}])
                return {"ok": True}

            response = TestClient(app).post("/chat")
            self.assertEqual(response.status_code, 200)
            events = read_events(path)
            self.assertEqual([e["event_type"] for e in events], ["chain_start", "llm_start", "llm_end", "chain_end"])
            self.assert_valid_events(events)
            root = events[0]
            self.assertEqual(events[1]["trace_id"], root["trace_id"])
            self.assertEqual(events[2]["trace_id"], root["trace_id"])
            self.assertEqual(events[1]["parent_span_id"], root["span_id"])
            self.assertEqual(events[2]["parent_span_id"], root["span_id"])

    def test_middleware_emit_failure_does_not_break_response(self):
        gov = self.make_client(sink=ExplodingSink())
        app = FastAPI()
        app.add_middleware(GovernanceMiddleware, governance_client=gov)

        @app.get("/health")
        def health():
            return {"ok": True}

        response = TestClient(app).get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertGreaterEqual(gov.dropped_events, 2)


if __name__ == "__main__":
    unittest.main()
