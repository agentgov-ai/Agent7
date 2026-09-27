"""Tests for Agent7 pre-execution enforcement.

Run with:  python -m unittest tests.test_enforcement -v
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "sdk-python"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from ai_governance import Agent7Blocked, GovernanceClient, validate_event  # noqa: E402
from ai_governance.core.actions import (  # noqa: E402
    EXECUTION_ALLOWED_EXECUTED,
    EXECUTION_APPROVAL_REQUIRED_BLOCKED,
    EXECUTION_DENIED_BLOCKED,
    EXECUTION_OBSERVE_ONLY,
    EXECUTION_SHADOW_ALLOWED,
)
from ai_governance.core.decisions import (  # noqa: E402
    REASON_APPROVAL_REQUIRED_UNTRUSTED,
    REASON_ARGUMENT_PATTERN_DENIED,
    REASON_CAPABILITY_DENIED,
    REASON_KILL_SWITCH,
    VERDICT_ALLOW,
    VERDICT_DENY,
    VERDICT_REQUIRE_APPROVAL,
)
from ai_governance.enforcement import (  # noqa: E402
    build_policy_from_manifest,
    resolve_endpoints,
)
from ai_governance.manifest import (  # noqa: E402
    STATUS_SKIPPED_NOT_APPROVED,
    STATUS_WRAPPED,
    STATUS_WRAPPED_FOR_ENFORCEMENT,
    load_manifest,
)

# Side effects recorded by governed functions. A blocked action must leave
# this list untouched -- that is the acceptance test for this milestone.
SIDE_EFFECTS: list[str] = []


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_manifest(tmp: Path, payload: dict) -> Path:
    import yaml

    path = tmp / "governance.yaml"
    path.write_text(yaml.dump(payload, default_flow_style=False), encoding="utf-8")
    return path


class EnforcementTestBase(unittest.TestCase):
    def setUp(self) -> None:
        SIDE_EFFECTS.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.events_path = self.tmp_path / "events.jsonl"
        self.actions_path = self.tmp_path / "actions.jsonl"

    def tearDown(self) -> None:
        SIDE_EFFECTS.clear()
        self.tmp.cleanup()

    def make_client(self, *, capabilities: list[dict], mode: str, **kwargs) -> GovernanceClient:
        manifest: dict = {"system_id": "enforcement-test", "capabilities": capabilities}
        manifest.update(kwargs.pop("manifest_extra", {}))
        path = write_manifest(self.tmp_path, manifest)
        return GovernanceClient.from_config(
            path,
            jsonl_path=str(self.events_path),
            actions_jsonl_path=str(self.actions_path),
            enforcement_mode=mode,
            remote_decisions=False,
            **kwargs,
        )

    def events(self) -> list[dict]:
        return read_jsonl(self.events_path)

    def records(self) -> list[dict]:
        return read_jsonl(self.actions_path)

    def event_types(self) -> list[str]:
        return [event["event_type"] for event in self.events()]


class AllowExecutesTest(EnforcementTestBase):
    def test_allow_executes_and_emits_normal_evidence(self):
        gov = self.make_client(
            capabilities=[{"name": "fetch", "module_path": "m.fetch", "status": "approved"}],
            mode="enforce",
        )

        @gov.tool(name="fetch", action_type="read")
        def fetch(query: str) -> str:
            SIDE_EFFECTS.append("fetch")
            return "rows"

        self.assertEqual(fetch("all"), "rows")
        self.assertEqual(SIDE_EFFECTS, ["fetch"])
        self.assertEqual(self.event_types(), ["tool_start", "tool_end"])
        for event in self.events():
            self.assertEqual(validate_event(event), [], event)

        start = self.events()[0]
        self.assertEqual(start["decision"]["verdict"], VERDICT_ALLOW)
        self.assertEqual(start["decision"]["execution_status"], EXECUTION_ALLOWED_EXECUTED)

        records = self.records()
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]["executed"])
        self.assertEqual(records[0]["execution_status"], EXECUTION_ALLOWED_EXECUTED)


class DenyBlocksTest(EnforcementTestBase):
    """The acceptance test: a denied body must not run."""

    def test_denied_sync_function_body_never_executes(self):
        gov = self.make_client(
            capabilities=[{"name": "purge", "module_path": "m.purge", "status": "denied"}],
            mode="enforce",
        )

        @gov.tool(name="purge", action_type="write")
        def purge(record_id: str) -> str:
            SIDE_EFFECTS.append("purge")
            return "deleted"

        result = purge("REC-1")

        self.assertEqual(SIDE_EFFECTS, [], "denied function body executed")
        self.assertTrue(result["agent7_blocked"])
        self.assertEqual(result["verdict"], VERDICT_DENY)
        self.assertEqual(result["reason_code"], REASON_CAPABILITY_DENIED)
        self.assertTrue(result["action_id"].startswith("ACT-"))
        self.assertTrue(result["decision_id"].startswith("DEC-"))

        # No tool_start: the tool never started.
        self.assertEqual(self.event_types(), ["action_decision"])
        for event in self.events():
            self.assertEqual(validate_event(event), [], event)

        records = self.records()
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0]["executed"])
        self.assertEqual(records[0]["execution_status"], EXECUTION_DENIED_BLOCKED)
        self.assertTrue(records[0]["evidence_hash"].startswith("sha256:"))

    def test_denied_async_coroutine_body_never_executes(self):
        gov = self.make_client(
            capabilities=[{"name": "purge_async", "module_path": "m.purge_async", "status": "denied"}],
            mode="enforce",
        )

        @gov.tool(name="purge_async", action_type="write")
        async def purge_async(record_id: str) -> str:
            SIDE_EFFECTS.append("purge_async")
            return "deleted"

        result = asyncio.run(purge_async("REC-1"))

        self.assertEqual(SIDE_EFFECTS, [], "denied coroutine body executed")
        self.assertTrue(result["agent7_blocked"])
        self.assertEqual(result["verdict"], VERDICT_DENY)
        self.assertEqual(self.event_types(), ["action_decision"])

    def test_allowed_async_coroutine_executes_and_awaits(self):
        gov = self.make_client(
            capabilities=[{"name": "fetch_async", "module_path": "m.fetch_async", "status": "approved"}],
            mode="enforce",
        )

        @gov.tool(name="fetch_async", action_type="read")
        async def fetch_async(query: str) -> str:
            await asyncio.sleep(0)
            SIDE_EFFECTS.append("fetch_async")
            return "rows"

        self.assertEqual(asyncio.run(fetch_async("all")), "rows")
        self.assertEqual(SIDE_EFFECTS, ["fetch_async"])
        self.assertEqual(self.event_types(), ["tool_start", "tool_end"])
        # Proof the coroutine was awaited, not merely created.
        self.assertEqual(self.events()[1]["attributes"]["result_summary"], "rows")

    def test_on_deny_raise_raises_agent7_blocked(self):
        gov = self.make_client(
            capabilities=[{"name": "purge", "module_path": "m.purge", "status": "denied"}],
            mode="enforce",
            on_deny="raise",
        )

        @gov.tool(name="purge", action_type="write")
        def purge() -> str:
            SIDE_EFFECTS.append("purge")
            return "deleted"

        with self.assertRaises(Agent7Blocked) as caught:
            purge()

        self.assertEqual(SIDE_EFFECTS, [])
        self.assertEqual(caught.exception.verdict, VERDICT_DENY)
        self.assertTrue(caught.exception.action_id.startswith("ACT-"))

    def test_unapproved_capability_is_denied_in_enforce_mode(self):
        gov = self.make_client(
            capabilities=[
                {"name": "known", "module_path": "m.known", "status": "approved"},
            ],
            mode="enforce",
        )

        @gov.tool(name="unknown_capability", action_type="write")
        def unknown_capability() -> str:
            SIDE_EFFECTS.append("unknown")
            return "done"

        result = unknown_capability()
        self.assertEqual(SIDE_EFFECTS, [])
        self.assertTrue(result["agent7_blocked"])


class ApprovalTest(EnforcementTestBase):
    def _client(self) -> GovernanceClient:
        return self.make_client(
            capabilities=[
                {
                    "name": "export",
                    "module_path": "m.export",
                    "status": "approved",
                    "approval_required": True,
                }
            ],
            mode="enforce",
        )

    def test_approval_required_without_token_blocks(self):
        gov = self._client()

        @gov.tool(name="export", action_type="write", approval_required=True)
        def export(dataset: str) -> str:
            SIDE_EFFECTS.append("export")
            return "exported"

        result = export("flights")
        self.assertEqual(SIDE_EFFECTS, [])
        self.assertEqual(result["verdict"], VERDICT_REQUIRE_APPROVAL)
        self.assertEqual(result["reason_code"], REASON_APPROVAL_REQUIRED_UNTRUSTED)
        self.assertEqual(self.records()[0]["execution_status"], EXECUTION_APPROVAL_REQUIRED_BLOCKED)

    def test_granted_alone_is_not_trusted(self):
        gov = self._client()

        @gov.tool(name="export", action_type="write", approval_required=True)
        def export(dataset: str) -> str:
            SIDE_EFFECTS.append("export")
            return "exported"

        result = export("flights", agent7_approval={"granted": True})
        self.assertEqual(SIDE_EFFECTS, [], "a self-asserted approval was trusted")
        self.assertEqual(result["verdict"], VERDICT_REQUIRE_APPROVAL)

    def test_verified_approval_allows_execution(self):
        gov = self._client()

        @gov.tool(name="export", action_type="write", approval_required=True)
        def export(dataset: str) -> str:
            SIDE_EFFECTS.append("export")
            return "exported"

        self.assertEqual(export("flights", agent7_approval={"verified": True}), "exported")
        self.assertEqual(SIDE_EFFECTS, ["export"])

    def test_approval_context_manager_allows_execution(self):
        gov = self._client()

        @gov.tool(name="export", action_type="write", approval_required=True)
        def export(dataset: str) -> str:
            SIDE_EFFECTS.append("export")
            return "exported"

        with gov.approval({"token_verified": True}):
            self.assertEqual(export("flights"), "exported")
        self.assertEqual(SIDE_EFFECTS, ["export"])


class ModeTest(EnforcementTestBase):
    CAPS = [{"name": "purge", "module_path": "m.purge", "status": "denied"}]

    def test_observe_never_blocks_and_emits_nothing_extra(self):
        gov = self.make_client(capabilities=self.CAPS, mode="observe")

        @gov.tool(name="purge", action_type="write")
        def purge() -> str:
            SIDE_EFFECTS.append("purge")
            return "deleted"

        self.assertEqual(purge(), "deleted")
        self.assertEqual(SIDE_EFFECTS, ["purge"])
        # Byte-compatible with pre-enforcement releases: no extra event rows.
        self.assertEqual(self.event_types(), ["tool_start", "tool_end"])
        self.assertEqual(self.events()[0]["decision"]["execution_status"], EXECUTION_OBSERVE_ONLY)
        # And no action-record file is created at all.
        self.assertFalse(self.actions_path.exists())

    def test_shadow_never_blocks_but_records_would_have_blocked(self):
        gov = self.make_client(capabilities=self.CAPS, mode="shadow")

        @gov.tool(name="purge", action_type="write")
        def purge() -> str:
            SIDE_EFFECTS.append("purge")
            return "deleted"

        self.assertEqual(purge(), "deleted")
        self.assertEqual(SIDE_EFFECTS, ["purge"])
        self.assertEqual(self.event_types(), ["action_decision", "tool_start", "tool_end"])

        record = self.records()[0]
        self.assertTrue(record["executed"])
        self.assertTrue(record["would_have_blocked"])
        self.assertEqual(record["execution_status"], EXECUTION_SHADOW_ALLOWED)
        self.assertEqual(record["decision"]["verdict"], VERDICT_DENY)

    def test_observe_with_record_decisions_opts_into_records(self):
        gov = self.make_client(capabilities=self.CAPS, mode="observe", record_decisions=True)

        @gov.tool(name="purge", action_type="write")
        def purge() -> str:
            SIDE_EFFECTS.append("purge")
            return "deleted"

        purge()
        self.assertEqual(SIDE_EFFECTS, ["purge"])
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.records()[0]["execution_status"], EXECUTION_OBSERVE_ONLY)


class KillSwitchTest(EnforcementTestBase):
    def test_kill_switch_forces_deny_on_an_approved_capability(self):
        gov = self.make_client(
            capabilities=[{"name": "fetch_live_flights", "module_path": "m.f", "status": "approved"}],
            mode="enforce",
            manifest_extra={
                "kill_switches": [
                    {
                        "id": "disable_live_airspace",
                        "enabled": True,
                        "target_capabilities": ["fetch_live_flights"],
                        "verdict": "DENY",
                        "reason": "Live airspace disabled for demo",
                    }
                ]
            },
        )

        @gov.tool(name="fetch_live_flights", action_type="read")
        def fetch_live_flights() -> list:
            SIDE_EFFECTS.append("fetch")
            return [1, 2]

        result = fetch_live_flights()
        self.assertEqual(SIDE_EFFECTS, [])
        self.assertEqual(result["verdict"], VERDICT_DENY)
        self.assertEqual(result["reason_code"], REASON_KILL_SWITCH)
        self.assertEqual(self.records()[0]["decision"]["kill_switch_id"], "disable_live_airspace")

    def test_disabled_kill_switch_allows_execution(self):
        gov = self.make_client(
            capabilities=[{"name": "fetch_live_flights", "module_path": "m.f", "status": "approved"}],
            mode="enforce",
            manifest_extra={
                "kill_switches": [
                    {
                        "id": "disable_live_airspace",
                        "enabled": False,
                        "target_capabilities": ["fetch_live_flights"],
                    }
                ]
            },
        )

        @gov.tool(name="fetch_live_flights", action_type="read")
        def fetch_live_flights() -> str:
            SIDE_EFFECTS.append("fetch")
            return "ok"

        self.assertEqual(fetch_live_flights(), "ok")
        self.assertEqual(SIDE_EFFECTS, ["fetch"])


class ArgumentPolicyTest(EnforcementTestBase):
    CAPS = [
        {
            "name": "run_query",
            "module_path": "m.run_query",
            "status": "approved",
            "denied_argument_patterns": [
                {"id": "destructive_sql", "pattern": "(?i)\\b(drop|delete|truncate|alter)\\b"}
            ],
        }
    ]

    def test_safe_query_is_allowed(self):
        gov = self.make_client(capabilities=self.CAPS, mode="enforce")

        @gov.tool(name="run_query", action_type="execute")
        def run_query(sql: str) -> str:
            SIDE_EFFECTS.append(sql)
            return "rows"

        self.assertEqual(run_query("SELECT * FROM flights"), "rows")
        self.assertEqual(len(SIDE_EFFECTS), 1)

    def test_destructive_query_is_denied_and_never_executes(self):
        gov = self.make_client(capabilities=self.CAPS, mode="enforce")

        @gov.tool(name="run_query", action_type="execute")
        def run_query(sql: str) -> str:
            SIDE_EFFECTS.append(sql)
            return "rows"

        result = run_query("DROP TABLE flights")
        self.assertEqual(SIDE_EFFECTS, [])
        self.assertEqual(result["reason_code"], REASON_ARGUMENT_PATTERN_DENIED)
        self.assertEqual(self.records()[0]["decision"]["matched_pattern_id"], "destructive_sql")

    def test_raw_sql_is_never_persisted_in_the_action_record(self):
        gov = self.make_client(capabilities=self.CAPS, mode="enforce")

        @gov.tool(name="run_query", action_type="execute")
        def run_query(sql: str) -> str:
            SIDE_EFFECTS.append(sql)
            return "rows"

        run_query("DROP TABLE flights")
        payload = json.dumps(self.records(), ensure_ascii=False)
        self.assertNotIn("DROP TABLE flights", payload)
        self.assertNotIn("flights", payload)
        record = self.records()[0]
        self.assertEqual(record["request"]["argument_names"], ["sql"])
        self.assertEqual(record["request"]["argument_types"], {"sql": "str"})
        self.assertTrue(record["request"]["arguments_hash"].startswith("sha256:"))


class PrivacyTest(EnforcementTestBase):
    def test_action_records_carry_no_argument_values(self):
        gov = self.make_client(
            capabilities=[{"name": "lookup", "module_path": "m.lookup", "status": "approved"}],
            mode="enforce",
        )

        @gov.tool(name="lookup", action_type="read")
        def lookup(email: str, api_key: str, card_number: str) -> str:
            return "ok"

        lookup("a@b.com", "sk-secret-value", "4111111111111111")

        payload = json.dumps(self.records(), ensure_ascii=False)
        self.assertNotIn("a@b.com", payload)
        self.assertNotIn("sk-secret-value", payload)
        self.assertNotIn("4111111111111111", payload)

        request = self.records()[0]["request"]
        self.assertEqual(request["argument_names"], ["api_key", "card_number", "email"])
        self.assertNotIn("sanitized_arguments", request)
        self.assertNotIn("arguments", request)


class ManifestInstrumentationTest(EnforcementTestBase):
    def setUp(self) -> None:
        super().setUp()
        module = self.tmp_path / "enf_mod.py"
        module.write_text(
            textwrap.dedent(
                """\
                CALLS = []

                def approved_fn(x):
                    CALLS.append("approved")
                    return x * 2

                def denied_fn(x):
                    CALLS.append("denied")
                    return x * 3

                def bogus_fn(x):
                    CALLS.append("bogus")
                    return x
                """
            ),
            encoding="utf-8",
        )
        sys.path.insert(0, str(self.tmp_path))
        sys.modules.pop("enf_mod", None)

    def tearDown(self) -> None:
        sys.path.remove(str(self.tmp_path))
        sys.modules.pop("enf_mod", None)
        super().tearDown()

    CAPS = [
        {"name": "approved_fn", "module_path": "enf_mod.approved_fn", "status": "approved"},
        {"name": "denied_fn", "module_path": "enf_mod.denied_fn", "status": "denied"},
        {"name": "bogus_fn", "module_path": "enf_mod.bogus_fn", "status": "false_positive"},
    ]

    def test_observe_mode_keeps_historical_wrapping_behaviour(self):
        gov = self.make_client(capabilities=self.CAPS, mode="observe")
        results = {item["name"]: item["status"] for item in gov.instrument_from_config()}
        self.assertEqual(results["approved_fn"], STATUS_WRAPPED)
        self.assertEqual(results["denied_fn"], STATUS_SKIPPED_NOT_APPROVED)
        self.assertEqual(results["bogus_fn"], STATUS_SKIPPED_NOT_APPROVED)

    def test_enforce_mode_wraps_denied_capability_and_blocks_it(self):
        gov = self.make_client(capabilities=self.CAPS, mode="enforce")
        results = {item["name"]: item["status"] for item in gov.instrument_from_config()}
        self.assertEqual(results["approved_fn"], STATUS_WRAPPED)
        self.assertEqual(results["denied_fn"], STATUS_WRAPPED_FOR_ENFORCEMENT)
        self.assertEqual(results["bogus_fn"], STATUS_SKIPPED_NOT_APPROVED)

        import enf_mod

        self.assertEqual(enf_mod.approved_fn(4), 8)
        blocked = enf_mod.denied_fn(4)
        self.assertTrue(blocked["agent7_blocked"])
        self.assertEqual(enf_mod.CALLS, ["approved"], "denied module function executed")


class ManifestValidationTest(unittest.TestCase):
    def test_invalid_enforcement_mode_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_manifest(
                Path(tmp),
                {"system_id": "s", "capabilities": [], "enforcement_mode": "blocking"},
            )
            with self.assertRaises(ValueError):
                load_manifest(path)

    def test_kill_switch_without_id_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_manifest(
                Path(tmp),
                {"system_id": "s", "capabilities": [], "kill_switches": [{"enabled": True}]},
            )
            with self.assertRaises(ValueError):
                load_manifest(path)

    def test_valid_enforcement_manifest_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_manifest(
                Path(tmp),
                {
                    "system_id": "s",
                    "enforcement_mode": "enforce",
                    "capabilities": [{"name": "f", "module_path": "m.f", "status": "approved"}],
                    "kill_switches": [{"id": "ks1", "target_capabilities": ["f"]}],
                },
            )
            config = load_manifest(path)
            self.assertEqual(config["enforcement_mode"], "enforce")


class DenyPatternGuardTest(unittest.TestCase):
    """A deny rule that can never match must fail loudly, not silently."""

    def test_control_character_pattern_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_manifest(
                Path(tmp),
                {
                    "system_id": "s",
                    "capabilities": [
                        {
                            "name": "q",
                            "module_path": "m.q",
                            "status": "approved",
                            "denied_argument_patterns": ["(?i)\x08drop"],
                        }
                    ],
                },
            )
            config = load_manifest(path)
            with self.assertRaises(ValueError) as caught:
                build_policy_from_manifest(config)
            self.assertIn("control character", str(caught.exception))

    def test_single_quoted_pattern_compiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_manifest(
                Path(tmp),
                {
                    "system_id": "s",
                    "capabilities": [
                        {
                            "name": "q",
                            "module_path": "m.q",
                            "status": "approved",
                            "denied_argument_patterns": ["(?i)\\bdrop\\b"],
                        }
                    ],
                },
            )
            policy = build_policy_from_manifest(load_manifest(path))
            pattern = policy.capabilities["q"].denied_argument_patterns[0][1]
            self.assertTrue(re.compile(pattern).search("DROP TABLE t"))


class EndpointResolutionTest(unittest.TestCase):
    def test_full_events_url_is_preserved(self):
        events, base = resolve_endpoints("http://127.0.0.1:8000/evidence/events")
        self.assertEqual(events, "http://127.0.0.1:8000/evidence/events")
        self.assertEqual(base, "http://127.0.0.1:8000")

    def test_base_url_gains_the_events_path(self):
        events, base = resolve_endpoints("http://127.0.0.1:8000")
        self.assertEqual(events, "http://127.0.0.1:8000/evidence/events")
        self.assertEqual(base, "http://127.0.0.1:8000")

    def test_none_stays_none(self):
        self.assertEqual(resolve_endpoints(None), (None, None))


class RemoteDecisionTest(EnforcementTestBase):
    """The backend may decide, but must never downgrade a local DENY."""

    class _Response:
        def __init__(self, payload: bytes, status: int = 200) -> None:
            self._payload = payload
            self.status = status

        def read(self) -> bytes:
            return self._payload

        def close(self) -> None:
            return None

    def test_backend_deny_is_honoured_for_a_locally_approved_capability(self):
        payload = json.dumps(
            {
                "decision": {
                    "decision_id": "DEC-remote",
                    "verdict": "DENY",
                    "reason": "kill switch active",
                    "reason_code": "kill_switch",
                    "kill_switch_id": "ks-remote",
                }
            }
        ).encode("utf-8")

        def opener(request, timeout=None):
            return self._Response(payload)

        path = write_manifest(
            self.tmp_path,
            {
                "system_id": "enforcement-test",
                "capabilities": [{"name": "fetch", "module_path": "m.f", "status": "approved"}],
            },
        )
        gov = GovernanceClient.from_config(
            path,
            jsonl_path=str(self.events_path),
            actions_jsonl_path=str(self.actions_path),
            enforcement_mode="enforce",
            api_endpoint="http://127.0.0.1:8000",
            remote_decisions=True,
            decision_opener=opener,
        )

        @gov.tool(name="fetch", action_type="read")
        def fetch() -> str:
            SIDE_EFFECTS.append("fetch")
            return "rows"

        result = fetch()
        self.assertEqual(SIDE_EFFECTS, [])
        self.assertEqual(result["verdict"], VERDICT_DENY)
        self.assertEqual(self.records()[0]["decision"]["decided_by"], "backend")

    def test_local_argument_policy_survives_a_backend_allow(self):
        """Deny patterns are local-only, so a backend ALLOW must not bypass them."""
        payload = json.dumps(
            {
                "decision": {
                    "decision_id": "DEC-remote-allow",
                    "verdict": "ALLOW",
                    "reason": "approved in ACAP",
                    "reason_code": "allowed_by_policy",
                }
            }
        ).encode("utf-8")

        def opener(request, timeout=None):
            return self._Response(payload)

        path = write_manifest(
            self.tmp_path,
            {
                "system_id": "enforcement-test",
                "capabilities": [
                    {
                        "name": "run_query",
                        "module_path": "m.q",
                        "status": "approved",
                        "denied_argument_patterns": [
                            {"id": "destructive_sql", "pattern": "(?i)\\bdrop\\b"}
                        ],
                    }
                ],
            },
        )
        gov = GovernanceClient.from_config(
            path,
            jsonl_path=str(self.events_path),
            actions_jsonl_path=str(self.actions_path),
            enforcement_mode="enforce",
            api_endpoint="http://127.0.0.1:8000",
            remote_decisions=True,
            decision_opener=opener,
        )

        @gov.tool(name="run_query", action_type="execute")
        def run_query(sql: str) -> str:
            SIDE_EFFECTS.append(sql)
            return "rows"

        # A safe statement still rides the backend ALLOW.
        self.assertEqual(run_query("SELECT 1"), "rows")
        SIDE_EFFECTS.clear()

        # A destructive one is stopped by local policy despite the backend.
        result = run_query("DROP TABLE flights")
        self.assertEqual(SIDE_EFFECTS, [], "backend ALLOW bypassed local argument policy")
        self.assertEqual(result["verdict"], VERDICT_DENY)
        self.assertEqual(result["reason_code"], REASON_ARGUMENT_PATTERN_DENIED)

    def test_unreachable_backend_falls_back_to_local_deny(self):
        def opener(request, timeout=None):
            raise OSError("backend down")

        path = write_manifest(
            self.tmp_path,
            {
                "system_id": "enforcement-test",
                "capabilities": [{"name": "purge", "module_path": "m.p", "status": "denied"}],
            },
        )
        gov = GovernanceClient.from_config(
            path,
            jsonl_path=str(self.events_path),
            actions_jsonl_path=str(self.actions_path),
            enforcement_mode="enforce",
            api_endpoint="http://127.0.0.1:8000",
            remote_decisions=True,
            decision_opener=opener,
        )

        @gov.tool(name="purge", action_type="write")
        def purge() -> str:
            SIDE_EFFECTS.append("purge")
            return "deleted"

        result = purge()
        self.assertEqual(SIDE_EFFECTS, [], "a down backend allowed a denied capability")
        self.assertEqual(result["verdict"], VERDICT_DENY)
        self.assertEqual(self.records()[0]["decision"]["decided_by"], "sdk_local")


class BareToolCompatibilityTest(EnforcementTestBase):
    def test_tool_without_a_manifest_is_never_blocked(self):
        gov = GovernanceClient(system_id="bare", jsonl_path=str(self.events_path))

        @gov.tool(name="anything", action_type="write")
        def anything() -> str:
            SIDE_EFFECTS.append("anything")
            return "done"

        self.assertEqual(anything(), "done")
        self.assertEqual(SIDE_EFFECTS, ["anything"])
        self.assertEqual(self.event_types(), ["tool_start", "tool_end"])


if __name__ == "__main__":
    unittest.main()
