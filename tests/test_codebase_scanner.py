"""Tests for the deterministic codebase scanner (MVP).

Run with:  python -m unittest tests.test_codebase_scanner -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "sdk-python"
sys.path.insert(0, str(SDK_ROOT))

from ai_governance.scanner.ast_scanner import scan_codebase  # noqa: E402
from ai_governance.scanner.models import SCANNER_VERSION, build_candidate, build_evidence  # noqa: E402
from ai_governance.scanner.output import format_discovery, write_governance_discovery  # noqa: E402
from ai_governance.scanner.rules import classify_candidate  # noqa: E402
from ai_governance.scanner.sinks import all_sinks, is_sql_write, match_model_usage, match_sink  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────

def _write_py(tmp: Path, name: str, code: str) -> Path:
    """Write a .py file with *code* (auto-dedented) into *tmp*."""
    p = tmp / name
    p.write_text(textwrap.dedent(code), encoding="utf-8")
    return p


def _candidates_by_name(candidates: list[dict]) -> dict[str, dict]:
    return {c["name"]: c for c in candidates}


# ── Sink catalog tests ───────────────────────────────────────────────────

class TestSinkCatalog(unittest.TestCase):

    def test_stripe_refund_matches(self) -> None:
        m = match_sink(("stripe", "refunds", "create"))
        self.assertIsNotNone(m)
        self.assertEqual(m["action_type"], "write")
        self.assertIn("financial", m["data_classes"])
        self.assertEqual(m["risk"], "high")

    def test_wildcard_paypal_matches(self) -> None:
        m = match_sink(("paypal", "orders", "capture"))
        self.assertIsNotNone(m)
        self.assertEqual(m["category"], "payment")

    def test_session_delete_is_delete_action(self) -> None:
        m = match_sink(("session", "delete"))
        self.assertIsNotNone(m)
        self.assertEqual(m["action_type"], "delete")

    def test_read_only_call_no_match(self) -> None:
        self.assertIsNone(match_sink(("json", "dumps")))
        self.assertIsNone(match_sink(("print",)))

    def test_all_sinks_have_required_keys(self) -> None:
        required = {"pattern", "action_type", "data_classes", "risk",
                     "approval_required", "external_side_effect", "category"}
        for entry in all_sinks():
            self.assertTrue(required.issubset(entry.keys()), entry)

    def test_sql_write_detection(self) -> None:
        self.assertTrue(is_sql_write("INSERT INTO users VALUES (1, 'a')"))
        self.assertTrue(is_sql_write("  DELETE FROM orders WHERE id = 1"))
        self.assertFalse(is_sql_write("SELECT * FROM users"))
        self.assertFalse(is_sql_write(None))

    def test_model_usage_openai(self) -> None:
        m = match_model_usage(("openai", "chat", "completions", "create"))
        self.assertIsNotNone(m)
        self.assertEqual(m["provider"], "openai")
        self.assertEqual(m["category"], "model_usage")

    def test_model_usage_anthropic(self) -> None:
        m = match_model_usage(("anthropic", "messages", "create"))
        self.assertIsNotNone(m)
        self.assertEqual(m["provider"], "anthropic")

    def test_model_usage_unrelated_no_match(self) -> None:
        self.assertIsNone(match_model_usage(("requests", "get")))


# ── Classification rules tests ───────────────────────────────────────────

class TestClassificationRules(unittest.TestCase):

    def test_sink_classifies_high_confidence(self) -> None:
        sink = {"action_type": "write", "data_classes": ["financial"],
                "risk": "high", "approval_required": True,
                "external_side_effect": True}
        result = classify_candidate(
            function_name="refund_execute",
            param_names=["order_id", "amount"],
            sinks_found=[sink],
            decorator_meta=None,
            route_meta=None,
        )
        self.assertEqual(result["confidence_source"], "sink_reachability")
        self.assertGreaterEqual(result["confidence"], 0.90)
        self.assertEqual(result["suggested_action_type"], "write")

    def test_delete_sink_classifies_as_delete(self) -> None:
        sink = {"action_type": "delete", "data_classes": ["database"],
                "risk": "medium", "approval_required": False,
                "external_side_effect": False}
        result = classify_candidate(
            function_name="delete_customer",
            param_names=["customer_id"],
            sinks_found=[sink],
            decorator_meta=None,
            route_meta=None,
        )
        self.assertEqual(result["suggested_action_type"], "delete")

    def test_route_post_classifies_write(self) -> None:
        result = classify_candidate(
            function_name="create_thing",
            param_names=[],
            sinks_found=[],
            decorator_meta=None,
            route_meta={"method": "post", "path": "/things"},
        )
        self.assertEqual(result["confidence_source"], "route_and_name")
        self.assertEqual(result["suggested_action_type"], "write")

    def test_route_delete_classifies_delete(self) -> None:
        result = classify_candidate(
            function_name="remove_thing",
            param_names=[],
            sinks_found=[],
            decorator_meta=None,
            route_meta={"method": "delete", "path": "/things/{id}"},
        )
        self.assertEqual(result["suggested_action_type"], "delete")

    def test_name_only_low_confidence(self) -> None:
        result = classify_candidate(
            function_name="send_notification",
            param_names=[],
            sinks_found=[],
            decorator_meta=None,
            route_meta=None,
        )
        self.assertEqual(result["confidence_source"], "name_heuristic")
        self.assertEqual(result["confidence"], 0.50)

    def test_helper_returns_empty(self) -> None:
        result = classify_candidate(
            function_name="format_date",
            param_names=["dt"],
            sinks_found=[],
            decorator_meta=None,
            route_meta=None,
        )
        self.assertEqual(result, {})

    def test_multiple_signals_boost(self) -> None:
        sink = {"action_type": "write", "data_classes": ["financial"],
                "risk": "high", "approval_required": True,
                "external_side_effect": True}
        result = classify_candidate(
            function_name="refund_execute",
            param_names=["amount"],
            sinks_found=[sink],
            decorator_meta=None,
            route_meta={"method": "post", "path": "/refund"},
        )
        # sink (0.90) + route (+0.05) + name (+0.05) = 0.95 cap
        self.assertGreater(result["confidence"], 0.90)
        self.assertLessEqual(result["confidence"], 0.95)


# ── AST scanner integration tests ────────────────────────────────────────

class TestASTScanner(unittest.TestCase):

    def test_detects_sink_in_function(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_py(Path(tmp), "pay.py", """\
                import stripe

                def refund_execute(order_id, amount):
                    stripe.refunds.create(charge=order_id, amount=amount)
            """)
            cands, _ms, _fs, _fn, _ih = scan_codebase(tmp)
            by_name = _candidates_by_name(cands)
            self.assertIn("refund_execute", by_name)
            c = by_name["refund_execute"]
            self.assertEqual(c["risk"], "high")
            self.assertEqual(c["suggested_action_type"], "write")
            self.assertIn("financial", c["suggested_data_classes"])
            self.assertEqual(c["confidence_source"], "sink_reachability")

    def test_detects_email_as_communicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_py(Path(tmp), "mail.py", """\
                import smtplib
                from email.message import EmailMessage

                def send_invoice_email(to, body):
                    msg = EmailMessage()
                    with smtplib.SMTP("localhost") as s:
                        s.send_message(msg)
            """)
            cands, *_ = scan_codebase(tmp)
            by_name = _candidates_by_name(cands)
            self.assertIn("send_invoice_email", by_name)
            self.assertEqual(by_name["send_invoice_email"]["suggested_action_type"], "communicate")

    def test_detects_db_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_py(Path(tmp), "db.py", """\
                class FakeSession:
                    def delete(self, obj): ...

                session = FakeSession()

                def delete_customer(cid):
                    session.delete(cid)
            """)
            cands, *_ = scan_codebase(tmp)
            by_name = _candidates_by_name(cands)
            self.assertIn("delete_customer", by_name)
            self.assertEqual(by_name["delete_customer"]["suggested_action_type"], "delete")

    def test_ignores_helper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_py(Path(tmp), "util.py", """\
                from datetime import datetime

                def format_date(dt):
                    return dt.strftime("%Y-%m-%d")
            """)
            cands, *_ = scan_codebase(tmp)
            names = {c["name"] for c in cands}
            self.assertNotIn("format_date", names)

    def test_detects_fastapi_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_py(Path(tmp), "web.py", """\
                from fastapi import FastAPI

                app = FastAPI()

                @app.post("/items")
                def create_item(name: str):
                    return {"name": name}
            """)
            cands, *_ = scan_codebase(tmp)
            by_name = _candidates_by_name(cands)
            self.assertIn("create_item", by_name)
            ev_types = {e["type"] for e in by_name["create_item"]["evidence"]}
            self.assertIn("route", ev_types)

    def test_detects_gov_tool_decorator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_py(Path(tmp), "tools.py", """\
                class FakeGov:
                    def tool(self, **kw):
                        def wrapper(fn):
                            return fn
                        return wrapper

                gov = FakeGov()

                @gov.tool(action_type="write", approval_required=True)
                def do_dangerous_thing(x):
                    pass
            """)
            cands, *_ = scan_codebase(tmp)
            by_name = _candidates_by_name(cands)
            self.assertIn("do_dangerous_thing", by_name)
            c = by_name["do_dangerous_thing"]
            ev_types = {e["type"] for e in c["evidence"]}
            self.assertIn("decorator", ev_types)

    def test_openai_recorded_as_model_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_py(Path(tmp), "ai.py", """\
                import openai

                def generate_reply(prompt):
                    return openai.chat.completions.create(
                        model="gpt-4",
                        messages=[{"role": "user", "content": prompt}],
                    )
            """)
            _cands, model_surface, *_ = scan_codebase(tmp)
            providers = {m["provider"] for m in model_surface}
            self.assertIn("openai", providers)

    def test_anthropic_recorded_as_model_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_py(Path(tmp), "ai2.py", """\
                import anthropic

                def analyze(text):
                    client = anthropic.Anthropic()
                    return client.messages.create(model="claude-sonnet-4-20250514", messages=[])
            """)
            _cands, model_surface, *_ = scan_codebase(tmp)
            providers = {m["provider"] for m in model_surface}
            self.assertIn("anthropic", providers)

    def test_excludes_venv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            venv_dir = Path(tmp) / "venv" / "lib"
            venv_dir.mkdir(parents=True)
            _write_py(venv_dir, "hidden.py", """\
                import subprocess

                def run_cmd(cmd):
                    subprocess.run(cmd)
            """)
            cands, *_ = scan_codebase(tmp)
            names = {c["name"] for c in cands}
            self.assertNotIn("run_cmd", names)

    def test_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cands, ms, fs, fn, ih = scan_codebase(tmp)
            self.assertEqual(cands, [])
            self.assertEqual(ms, [])
            self.assertEqual(fs, 0)

    def test_import_alias_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_py(Path(tmp), "aliased.py", """\
                from stripe import refunds

                def do_refund(oid):
                    refunds.create(charge=oid)
            """)
            cands, *_ = scan_codebase(tmp)
            by_name = _candidates_by_name(cands)
            self.assertIn("do_refund", by_name)
            self.assertEqual(by_name["do_refund"]["suggested_action_type"], "write")

    def test_self_method_call_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_py(Path(tmp), "svc.py", """\
                class Service:
                    def __init__(self):
                        self.session = None

                    def remove_user(self, uid):
                        user = self.session.query("User").first()
                        self.session.delete(user)
            """)
            cands, *_ = scan_codebase(tmp)
            by_name = _candidates_by_name(cands)
            self.assertIn("remove_user", by_name)
            self.assertEqual(by_name["remove_user"]["suggested_action_type"], "delete")

    def test_async_function_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_py(Path(tmp), "async_svc.py", """\
                import subprocess

                async def deploy(cmd):
                    subprocess.run(cmd, shell=True)
            """)
            cands, *_ = scan_codebase(tmp)
            by_name = _candidates_by_name(cands)
            self.assertIn("deploy", by_name)
            self.assertEqual(by_name["deploy"]["suggested_action_type"], "execute")
            self.assertEqual(by_name["deploy"]["risk"], "high")


# ── Output format tests ──────────────────────────────────────────────────

class TestOutputFormat(unittest.TestCase):

    def setUp(self) -> None:
        self.candidate = build_candidate(
            name="test_fn",
            module_path="mod",
            file_path="mod.py",
            line_start=1,
            line_end=5,
            suggested_action_type="write",
            suggested_data_classes=["financial"],
            suggested_approval_required=True,
            external_side_effect=True,
            risk="high",
            confidence=0.90,
            confidence_source="sink_reachability",
            evidence=[build_evidence(evidence_type="sink_call", detail="stripe.refunds.create", line=3, file_path="mod.py")],
            call_chain=["test_fn -> stripe.refunds.create"],
        )
        self.discovery = format_discovery(
            candidates=[self.candidate],
            model_surface=[],
            files_scanned=1,
            functions_seen=2,
            ignored_helpers_count=1,
            root_path="/tmp/test",
        )

    def test_schema_version(self) -> None:
        self.assertEqual(self.discovery["schema_version"], "0.1")

    def test_scanner_version(self) -> None:
        self.assertEqual(self.discovery["scanner_version"], SCANNER_VERSION)

    def test_generated_at_present(self) -> None:
        self.assertIn("generated_at", self.discovery)

    def test_project_hash_present(self) -> None:
        self.assertIn("project_hash", self.discovery)
        self.assertTrue(self.discovery["project_hash"].startswith("sha256:"))

    def test_scan_summary(self) -> None:
        s = self.discovery["scan_summary"]
        self.assertEqual(s["files_scanned"], 1)
        self.assertEqual(s["candidates_found"], 1)
        self.assertEqual(s["high_risk_count"], 1)
        self.assertEqual(s["ignored_helpers_count"], 1)

    def test_model_surface_section(self) -> None:
        self.assertIn("model_surface", self.discovery)
        self.assertIsInstance(self.discovery["model_surface"], list)

    def test_candidate_required_fields(self) -> None:
        required = {
            "capability_id", "name", "module_path", "file_path",
            "line_start", "line_end", "suggested_action_type",
            "suggested_data_classes", "suggested_approval_required",
            "external_side_effect", "risk", "confidence",
            "confidence_source", "evidence", "call_chain",
            "review_status", "source",
        }
        self.assertTrue(required.issubset(self.candidate.keys()))

    def test_all_review_status_pending(self) -> None:
        for c in self.discovery["candidates"]:
            self.assertEqual(c["review_status"], "pending")

    def test_source_is_deterministic_scanner(self) -> None:
        self.assertEqual(self.discovery["source"], "deterministic_scanner")
        for c in self.discovery["candidates"]:
            self.assertEqual(c["source"], "deterministic_scanner")

    def test_capability_id_deterministic(self) -> None:
        c2 = build_candidate(
            name="test_fn",
            module_path="mod",
            file_path="mod.py",
            line_start=1,
            line_end=5,
            suggested_action_type="write",
            suggested_data_classes=["financial"],
            suggested_approval_required=True,
            external_side_effect=True,
            risk="high",
            confidence=0.90,
            confidence_source="sink_reachability",
            evidence=[],
            call_chain=[],
        )
        self.assertEqual(self.candidate["capability_id"], c2["capability_id"])
        self.assertTrue(self.candidate["capability_id"].startswith("CAP-"))

    def test_evidence_includes_file_and_line(self) -> None:
        ev = self.candidate["evidence"][0]
        self.assertIn("file_path", ev)
        self.assertIn("line", ev)

    def test_json_output_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "discovery.json"
            write_governance_discovery(self.discovery, out)
            loaded = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(loaded["schema_version"], "0.1")
            self.assertEqual(len(loaded["candidates"]), 1)

    def test_no_approved_acap_generated(self) -> None:
        """The scanner must never produce approved ACAP — only pending candidates."""
        for c in self.discovery["candidates"]:
            self.assertNotEqual(c["review_status"], "approved")
        self.assertNotIn("acap", self.discovery)


# ── End-to-end: scan the demo app ────────────────────────────────────────

class TestEndToEndDemoApp(unittest.TestCase):

    def setUp(self) -> None:
        demo = REPO_ROOT / "examples" / "scanner-demo-app"
        if not demo.is_dir():
            self.skipTest("scanner-demo-app not found")
        self.cands, self.model_surface, self.fs, self.fn, self.ih = scan_codebase(demo)
        self.by_name = _candidates_by_name(self.cands)

    def test_refund_execute_high_risk_write(self) -> None:
        self.assertIn("refund_execute", self.by_name)
        c = self.by_name["refund_execute"]
        self.assertEqual(c["risk"], "high")
        self.assertEqual(c["suggested_action_type"], "write")
        self.assertIn("financial", c["suggested_data_classes"])

    def test_send_invoice_email_communicate(self) -> None:
        self.assertIn("send_invoice_email", self.by_name)
        c = self.by_name["send_invoice_email"]
        self.assertEqual(c["suggested_action_type"], "communicate")

    def test_delete_customer_delete(self) -> None:
        self.assertIn("delete_customer", self.by_name)
        c = self.by_name["delete_customer"]
        self.assertEqual(c["suggested_action_type"], "delete")
        self.assertEqual(c["risk"], "medium")

    def test_format_date_ignored(self) -> None:
        self.assertNotIn("format_date", self.by_name)

    def test_model_surface_openai(self) -> None:
        providers = {m["provider"] for m in self.model_surface}
        self.assertIn("openai", providers)

    def test_model_surface_anthropic(self) -> None:
        providers = {m["provider"] for m in self.model_surface}
        self.assertIn("anthropic", providers)

    def test_all_pending(self) -> None:
        for c in self.cands:
            self.assertEqual(c["review_status"], "pending")

    def test_evidence_present(self) -> None:
        for c in self.cands:
            self.assertGreater(len(c["evidence"]), 0, c["name"])

    def test_files_scanned_positive(self) -> None:
        self.assertGreater(self.fs, 0)


if __name__ == "__main__":
    unittest.main()
