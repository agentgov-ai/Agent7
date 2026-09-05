"""Tests for manifest-based instrumentation.

Run with:  python -m unittest tests.test_manifest_instrumentation -v
"""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "sdk-python"
sys.path.insert(0, str(SDK_ROOT))

from ai_governance import GovernanceClient  # noqa: E402
from ai_governance.manifest import (  # noqa: E402
    STATUS_ALREADY_WRAPPED,
    STATUS_FAILED_IMPORT,
    STATUS_SKIPPED_NOT_APPROVED,
    STATUS_UNSUPPORTED_TARGET,
    STATUS_WRAPPED,
    WRAPPED_MARKER,
    load_manifest,
)


def _write(path: Path, name: str, content: str) -> Path:
    p = path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _make_manifest(tmp: Path, *, capabilities: list[dict], system_id: str = "test-system") -> Path:
    import yaml

    manifest = {"system_id": system_id, "capabilities": capabilities}
    p = tmp / "governance.yaml"
    p.write_text(yaml.dump(manifest, default_flow_style=False), encoding="utf-8")
    return p


def _read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class TestLoadManifest(unittest.TestCase):

    def test_parses_valid_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = _make_manifest(Path(tmp), capabilities=[
                {"name": "fn", "module_path": "mod.fn", "status": "approved"},
            ])
            config = load_manifest(p)
            self.assertEqual(config["system_id"], "test-system")
            self.assertEqual(len(config["capabilities"]), 1)

    def test_missing_system_id_raises(self) -> None:
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.yaml"
            p.write_text(yaml.dump({"capabilities": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_manifest(p)

    def test_missing_capability_name_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = _make_manifest(Path(tmp), capabilities=[
                {"module_path": "mod.fn", "status": "approved"},
            ])
            with self.assertRaises(ValueError):
                load_manifest(p)

    def test_missing_module_path_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = _make_manifest(Path(tmp), capabilities=[
                {"name": "fn", "status": "approved"},
            ])
            with self.assertRaises(ValueError):
                load_manifest(p)

    def test_missing_status_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = _make_manifest(Path(tmp), capabilities=[
                {"name": "fn", "module_path": "mod.fn"},
            ])
            with self.assertRaises(ValueError):
                load_manifest(p)


class TestFromConfig(unittest.TestCase):

    def test_creates_client_with_correct_system_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = _make_manifest(Path(tmp), capabilities=[], system_id="my-system")
            gov = GovernanceClient.from_config(p)
            self.assertEqual(gov.system_id, "my-system")

    def test_overrides_jsonl_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = _make_manifest(Path(tmp), capabilities=[])
            out = str(Path(tmp) / "custom.jsonl")
            gov = GovernanceClient.from_config(p, jsonl_path=out)
            self.assertEqual(str(gov.sink.path), out)


class TestInstrumentFromConfig(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        # Create a temporary Python module
        _write(self.tmp_path, "demo_mod.py", """\
            def good_fn(x):
                return x * 2

            def bad_fn():
                raise ValueError("boom")

            CONST = 42
        """)
        sys.path.insert(0, str(self.tmp_path))
        # Force re-import to pick up the fresh module
        if "demo_mod" in sys.modules:
            del sys.modules["demo_mod"]

    def tearDown(self) -> None:
        self.tmp.cleanup()
        sys.path.remove(str(self.tmp_path))
        sys.modules.pop("demo_mod", None)

    def _make_gov(self, capabilities: list[dict]) -> tuple[GovernanceClient, Path]:
        out = self.tmp_path / "events.jsonl"
        p = _make_manifest(self.tmp_path, capabilities=capabilities)
        gov = GovernanceClient.from_config(p, jsonl_path=str(out))
        return gov, out

    def test_wraps_approved_function(self) -> None:
        gov, out = self._make_gov([
            {"name": "good_fn", "module_path": "demo_mod.good_fn",
             "action_type": "read", "status": "approved"},
        ])
        results = gov.instrument_from_config()
        self.assertEqual(results[0]["status"], STATUS_WRAPPED)
        import demo_mod
        self.assertEqual(demo_mod.good_fn(5), 10)

    def test_skips_pending(self) -> None:
        gov, _ = self._make_gov([
            {"name": "good_fn", "module_path": "demo_mod.good_fn", "status": "pending"},
        ])
        results = gov.instrument_from_config()
        self.assertEqual(results[0]["status"], STATUS_SKIPPED_NOT_APPROVED)

    def test_skips_rejected(self) -> None:
        gov, _ = self._make_gov([
            {"name": "good_fn", "module_path": "demo_mod.good_fn", "status": "rejected"},
        ])
        results = gov.instrument_from_config()
        self.assertEqual(results[0]["status"], STATUS_SKIPPED_NOT_APPROVED)

    def test_skips_false_positive(self) -> None:
        gov, _ = self._make_gov([
            {"name": "good_fn", "module_path": "demo_mod.good_fn", "status": "false_positive"},
        ])
        results = gov.instrument_from_config()
        self.assertEqual(results[0]["status"], STATUS_SKIPPED_NOT_APPROVED)

    def test_wrapped_function_emits_events(self) -> None:
        gov, out = self._make_gov([
            {"name": "good_fn", "module_path": "demo_mod.good_fn",
             "action_type": "read", "status": "approved"},
        ])
        gov.instrument_from_config()
        import demo_mod
        demo_mod.good_fn(7)
        events = _read_events(out)
        types = [e["event_type"] for e in events]
        self.assertIn("tool_start", types)
        self.assertIn("tool_end", types)
        # Check tool name in tool_start
        start = next(e for e in events if e["event_type"] == "tool_start")
        self.assertEqual(start["tool"]["name"], "good_fn")
        self.assertEqual(start["tool"]["action_type"], "read")

    def test_wrapped_function_error_emits_tool_error(self) -> None:
        gov, out = self._make_gov([
            {"name": "bad_fn", "module_path": "demo_mod.bad_fn",
             "action_type": "execute", "status": "approved"},
        ])
        gov.instrument_from_config()
        import demo_mod
        with self.assertRaises(ValueError):
            demo_mod.bad_fn()
        events = _read_events(out)
        types = [e["event_type"] for e in events]
        self.assertIn("tool_start", types)
        self.assertIn("tool_error", types)

    def test_failed_import_does_not_crash(self) -> None:
        gov, _ = self._make_gov([
            {"name": "fn", "module_path": "nonexistent_module.fn", "status": "approved"},
        ])
        results = gov.instrument_from_config()
        self.assertEqual(results[0]["status"], STATUS_FAILED_IMPORT)

    def test_unsupported_target(self) -> None:
        gov, _ = self._make_gov([
            {"name": "CONST", "module_path": "demo_mod.CONST",
             "action_type": "read", "status": "approved"},
        ])
        results = gov.instrument_from_config()
        self.assertEqual(results[0]["status"], STATUS_UNSUPPORTED_TARGET)

    def test_double_instrumentation_does_not_double_wrap(self) -> None:
        gov, out = self._make_gov([
            {"name": "good_fn", "module_path": "demo_mod.good_fn",
             "action_type": "read", "status": "approved"},
        ])
        r1 = gov.instrument_from_config()
        r2 = gov.instrument_from_config()
        self.assertEqual(r1[0]["status"], STATUS_WRAPPED)
        self.assertEqual(r2[0]["status"], STATUS_ALREADY_WRAPPED)
        # Call function — should emit exactly 2 events (one start, one end), not 4
        import demo_mod
        demo_mod.good_fn(1)
        events = _read_events(out)
        self.assertEqual(len(events), 2)

    def test_manual_decorator_still_works(self) -> None:
        out = self.tmp_path / "manual.jsonl"
        gov = GovernanceClient(system_id="manual-test", jsonl_path=str(out))

        @gov.tool(name="manual_fn", action_type="write")
        def manual_fn(x: int) -> int:
            return x + 1

        result = manual_fn(10)
        self.assertEqual(result, 11)
        events = _read_events(out)
        types = [e["event_type"] for e in events]
        self.assertIn("tool_start", types)
        self.assertIn("tool_end", types)

    def test_approved_for_acap_status_wraps(self) -> None:
        gov, _ = self._make_gov([
            {"name": "good_fn", "module_path": "demo_mod.good_fn",
             "action_type": "read", "status": "approved_for_acap"},
        ])
        results = gov.instrument_from_config()
        self.assertEqual(results[0]["status"], STATUS_WRAPPED)


if __name__ == "__main__":
    unittest.main()
