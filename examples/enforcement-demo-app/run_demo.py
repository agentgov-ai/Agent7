"""Run the Agent7 pre-execution enforcement demo.

    cd examples/enforcement-demo-app
    python run_demo.py

Optional: start the Evidence API first so the actions show up in the dashboard
and so a kill switch toggled there takes effect on the next call.

    python -m uvicorn services.evidence_api.app:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for path in (str(REPO_ROOT / "sdk-python"), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

from ai_governance import GovernanceClient  # noqa: E402

BANNER = "=" * 74


def heading(text: str) -> None:
    print(f"\n{BANNER}\n{text}\n{BANNER}")


def show(label: str, result: object, side_effects: list[str]) -> None:
    blocked = isinstance(result, dict) and result.get("agent7_blocked")
    marker = "BLOCKED" if blocked else "EXECUTED"
    print(f"\n  [{marker}] {label}")
    if blocked:
        print(f"      verdict     : {result['verdict']}")
        print(f"      reason_code : {result['reason_code']}")
        print(f"      reason      : {result['reason']}")
        print(f"      action_id   : {result['action_id']}")
    else:
        print(f"      returned    : {result}")
    print(f"      side effects: {side_effects or 'none -- the function body never ran'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent7 enforcement demo")
    parser.add_argument(
        "--api",
        default=None,
        help="Evidence API base URL, e.g. http://127.0.0.1:8000. Omitted = local policy only.",
    )
    parser.add_argument(
        "--mode",
        default="enforce",
        choices=["observe", "shadow", "enforce"],
        help="Override the manifest enforcement_mode.",
    )
    args = parser.parse_args()

    gov = GovernanceClient.from_config(
        HERE / "governance.yaml",
        api_endpoint=args.api,
        jsonl_path=str(HERE / "events.jsonl"),
        actions_jsonl_path=str(HERE / "actions.jsonl"),
        enforcement_mode=args.mode,
    )

    heading(f"Agent7 enforcement demo  (mode={gov.enforcement_mode}, api={args.api or 'local only'})")

    results = gov.instrument_from_config()
    print("\nInstrumentation:")
    for item in results:
        print(f"  {item['status']:<24} {item['name']}")

    import app

    with gov.trace(name="airspace_copilot_session", session_id="demo-session-001"):
        heading("1. Approved capability -- expected to run")
        app.reset()
        show("fetch_live_flights()", app.fetch_live_flights("tokyo"), app.SIDE_EFFECTS)

        heading("2. Approved capability, safe argument -- expected to run")
        app.reset()
        show(
            "run_trino_query('SELECT callsign FROM flights')",
            app.run_trino_query("SELECT callsign FROM flights"),
            app.SIDE_EFFECTS,
        )

        heading("3. Approved capability, destructive argument -- expected to be denied")
        app.reset()
        show(
            "run_trino_query('DROP TABLE flights')",
            app.run_trino_query("DROP TABLE flights"),
            app.SIDE_EFFECTS,
        )

        heading("4. Approval-required capability, no approval -- expected to be held")
        app.reset()
        show(
            "export_query_result('flights', 's3://exports')",
            app.export_query_result("flights", "s3://exports"),
            app.SIDE_EFFECTS,
        )

        heading("5. Same capability with a verified approval -- expected to run")
        app.reset()
        with gov.approval({"verified": True, "approver": "ops-lead"}):
            show(
                "export_query_result(...) under a verified approval",
                app.export_query_result("flights", "s3://exports"),
                app.SIDE_EFFECTS,
            )

        heading("6. Denied capability -- body must never execute")
        app.reset()
        before = app.remaining_airspace_records()
        show(
            "delete_airspace_record('AREA-TOKYO-01')",
            app.delete_airspace_record("AREA-TOKYO-01"),
            app.SIDE_EFFECTS,
        )
        after = app.remaining_airspace_records()
        print(f"      records before: {before}")
        print(f"      records after : {after}")
        print(f"      record survived the denied delete: {before == after}")

    heading("Summary")
    print(f"  blocked actions this run : {gov.blocked_actions}")
    print(f"  evidence events          : {HERE / 'events.jsonl'}")
    print(f"  action records           : {HERE / 'actions.jsonl'}")
    if args.api:
        print(f"  dashboard                : {args.api}/ui/  -> Governed Actions tab")
    else:
        print("  dashboard                : re-run with --api http://127.0.0.1:8000 to publish")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
