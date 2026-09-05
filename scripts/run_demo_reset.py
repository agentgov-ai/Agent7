from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _post_json(base_url: str, path: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(base_url: str, path: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _server_reset(base_url: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    reset = _post_json(base_url, "/demo/reset")
    systems = _get_json(base_url, "/systems")
    findings = _get_json(base_url, "/findings?system_id=restaurant-agent")
    return reset, systems, findings


def _in_process_reset() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    from fastapi.testclient import TestClient

    from services.evidence_api.app import app

    with TestClient(app) as client:
        reset_response = client.post("/demo/reset")
        reset_response.raise_for_status()
        systems_response = client.get("/systems")
        systems_response.raise_for_status()
        findings_response = client.get("/findings", params={"system_id": "restaurant-agent"})
        findings_response.raise_for_status()
        return reset_response.json(), systems_response.json(), findings_response.json()


def _summarize(reset: dict[str, Any], systems: dict[str, Any], findings: dict[str, Any]) -> dict[str, Any]:
    system_ids = [item.get("system_id") for item in systems.get("systems", [])]
    finding_ids = [item.get("finding_id") for item in findings.get("findings", [])]
    return {
        "events_replayed": reset.get("events_replayed"),
        "findings_created": reset.get("findings_created"),
        "systems": system_ids,
        "restaurant_finding_present": "F-06236c96da2c" in finding_ids,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the local Evidence API demo database.")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Evidence API base URL. Defaults to http://127.0.0.1:8000.",
    )
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="Run the reset against the FastAPI app in this Python process.",
    )
    args = parser.parse_args()

    try:
        if args.in_process:
            reset, systems, findings = _in_process_reset()
        else:
            reset, systems, findings = _server_reset(args.base_url)
    except urllib.error.URLError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "hint": "Start the Evidence API or rerun with --in-process.",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    summary = _summarize(reset, systems, findings)
    print(json.dumps({"ok": True, **summary}, indent=2, sort_keys=True))
    return 0 if summary["restaurant_finding_present"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
