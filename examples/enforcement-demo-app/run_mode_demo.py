"""Prove that a dashboard enforcement-mode change reaches a running app.

Stands in for SkyQuery: one process starts in ``observe``, keeps running, and
starts blocking once an operator sets ``enforce`` in the dashboard. The app is
never restarted and its code never changes -- only the backend's stored mode.

Start the Evidence API first, then run this:

    python -m uvicorn services.evidence_api.app:app --host 127.0.0.1 --port 8077
    cd examples/enforcement-demo-app
    python run_mode_demo.py --api http://127.0.0.1:8077

``governance.yaml`` is not edited. Its ``enforcement_mode`` stays the local
fallback; this script passes ``enforcement_mode="observe"`` explicitly, which is
what a SkyQuery deployment configured for observe would send.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for path in (str(REPO_ROOT / "sdk-python"), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

from ai_governance import GovernanceClient  # noqa: E402

BANNER = "=" * 74
DANGEROUS_SQL = "DROP TABLE flights"


def heading(text: str) -> None:
    print(f"\n{BANNER}\n{text}\n{BANNER}")


def set_dashboard_mode(api: str, system_id: str, mode: str | None) -> dict:
    """What the dashboard's segmented control does, over the same endpoint."""
    body = json.dumps({"mode": mode}).encode("utf-8")
    request = urllib.request.Request(
        f"{api.rstrip('/')}/systems/{system_id}/enforcement-mode",
        data=body,
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def attempt(app, label: str) -> bool:
    """Run the dangerous prompt and report whether the body executed."""
    app.reset()
    result = app.run_trino_query(DANGEROUS_SQL)
    blocked = isinstance(result, dict) and result.get("agent7_blocked")
    print(f"\n  {label}")
    print(f"      run_trino_query({DANGEROUS_SQL!r})")
    if blocked:
        print(f"      -> BLOCKED  verdict={result['verdict']} reason_code={result['reason_code']}")
    else:
        print(f"      -> EXECUTED returned={result}")
    print(f"      side effects: {app.SIDE_EFFECTS or 'none -- the function body never ran'}")
    return bool(blocked)


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent7 dashboard-controlled mode demo")
    parser.add_argument(
        "--api",
        default="http://127.0.0.1:8077",
        help="Evidence API base URL (default: http://127.0.0.1:8077)",
    )
    args = parser.parse_args()

    # The app starts once, configured for observe, and is never restarted.
    gov = GovernanceClient.from_config(
        HERE / "governance.yaml",
        api_endpoint=args.api,
        jsonl_path=str(HERE / "events.jsonl"),
        actions_jsonl_path=str(HERE / "actions.jsonl"),
        enforcement_mode="observe",
    )
    gov.instrument_from_config()
    import app

    system_id = gov.system_id
    heading(f"App started once: system={system_id} sdk_mode={gov.enforcement_mode} api={args.api}")

    failures: list[str] = []
    with gov.trace(name="mode_demo_session", session_id="mode-demo-001"):
        heading("1. Dashboard mode: SDK default -- records, does not block")
        set_dashboard_mode(args.api, system_id, None)
        if attempt(app, "[expect EXECUTED]"):
            failures.append("blocked while the dashboard had no override")

        heading("2. Operator sets Enforce in the dashboard")
        state = set_dashboard_mode(args.api, system_id, "enforce")
        print(f"\n  effective mode : {state['mode']}  (source: {state['source']})")
        print(f"  sdk sends      : {state['sdk_mode']}")
        print("  the app was NOT restarted")

        heading("3. Same prompt, same process -- expected to be blocked")
        if not attempt(app, "[expect BLOCKED]"):
            failures.append("executed while the dashboard override was enforce")

        heading("4. Operator returns the control to SDK default")
        set_dashboard_mode(args.api, system_id, None)
        if attempt(app, "[expect EXECUTED]"):
            failures.append("still blocked after the override was cleared")

    heading("Result")
    if failures:
        for problem in failures:
            print(f"  FAIL: {problem}")
        return 1
    print("  PASS: the dashboard changed a running app's enforcement with no restart.")
    print(f"  blocked actions this run : {gov.blocked_actions}")
    print(f"  dashboard                : {args.api}/ui/  -> Governed Actions tab")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
