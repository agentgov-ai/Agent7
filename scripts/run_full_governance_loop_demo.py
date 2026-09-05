#!/usr/bin/env python
"""End-to-end governance loop demo.

Proves the full loop in-process using FastAPI TestClient and isolated temp DB:

  Scanner suggests → Human approves → ACAP generated →
  Runtime observed → Findings detected

Run from the repo root:
    python scripts/run_full_governance_loop_demo.py

No running server required.  No AI calls.  No source uploads.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "sdk-python"
sys.path.insert(0, str(SDK_ROOT))
sys.path.insert(0, str(REPO_ROOT))

DEMO_SYSTEM_ID = "scanner-demo"
DEMO_APP_DIR = REPO_ROOT / "examples" / "scanner-demo-app"


def main() -> int:
    # ── 0. Isolated temp DB ──────────────────────────────────────────
    tmp = tempfile.TemporaryDirectory()
    os.environ["EVIDENCE_DB_PATH"] = str(Path(tmp.name) / "evidence.db")

    from fastapi.testclient import TestClient
    from services.evidence_api.app import app

    client = TestClient(app)
    print("=" * 64)
    print("  AI Governance — Full Loop Demo")
    print("=" * 64)

    # ── 1. Scan ──────────────────────────────────────────────────────
    print("\n> Step 1: Scan examples/scanner-demo-app")
    from ai_governance.scanner import format_discovery, scan_codebase

    candidates, model_surface, files_scanned, functions_seen, ignored = scan_codebase(DEMO_APP_DIR)
    discovery = format_discovery(
        candidates=candidates,
        model_surface=model_surface,
        files_scanned=files_scanned,
        functions_seen=functions_seen,
        ignored_helpers_count=ignored,
        root_path=DEMO_APP_DIR,
    )
    cap_names = [c["name"] for c in candidates]
    print(f"  Files scanned:   {files_scanned}")
    print(f"  Candidates:      {len(candidates)} ({', '.join(cap_names)})")
    print(f"  Model surface:   {len(model_surface)}")

    # ── 2. Upload discovery ──────────────────────────────────────────
    print("\n> Step 2: Upload discovery to Evidence API")
    r = client.post("/discovery/upload", json={
        "system_id": DEMO_SYSTEM_ID,
        "discovery": discovery,
    })
    assert r.status_code == 200, r.text
    upload = r.json()
    print(f"  Upload ID:       {upload['upload_id'][:12]}…")
    print(f"  Candidates:      {upload['candidates_stored']}")

    # ── 3. Review capabilities ───────────────────────────────────────
    print("\n> Step 3: Review capabilities")
    # Approve refund_execute (high-risk write, has approval_required)
    cap_map = {c["name"]: c["capability_id"] for c in candidates}

    approved_names = []
    rejected_names = []

    if "refund_execute" in cap_map:
        r = client.post(f"/systems/{DEMO_SYSTEM_ID}/capabilities/{cap_map['refund_execute']}/approve")
        assert r.status_code == 200, r.text
        approved_names.append("refund_execute")

    if "send_invoice_email" in cap_map:
        r = client.post(f"/systems/{DEMO_SYSTEM_ID}/capabilities/{cap_map['send_invoice_email']}/approve")
        assert r.status_code == 200, r.text
        approved_names.append("send_invoice_email")

    if "delete_customer" in cap_map:
        r = client.post(f"/systems/{DEMO_SYSTEM_ID}/capabilities/{cap_map['delete_customer']}/reject")
        assert r.status_code == 200, r.text
        rejected_names.append("delete_customer")

    print(f"  Approved:        {', '.join(approved_names)}")
    print(f"  Rejected:        {', '.join(rejected_names)}")

    # ── 4. Generate ACAP version ─────────────────────────────────────
    print("\n> Step 4: Generate ACAP version")
    r = client.post(f"/systems/{DEMO_SYSTEM_ID}/acap/generate-from-discovery")
    assert r.status_code == 200, r.text
    acap = r.json()
    print(f"  ACAP version:    {acap['acap_version_id']}")
    print(f"  Allowed:         {acap['review_summary']['approved_count']}")
    print(f"  Denied:          {acap['review_summary']['denied_count']}")
    print(f"  Pending:         {acap['review_summary']['pending_count']}")

    # ── 5. Download governance manifest ──────────────────────────────
    print("\n> Step 5: Download governance manifest")
    r = client.get(f"/systems/{DEMO_SYSTEM_ID}/governance-manifest.json")
    assert r.status_code == 200, r.text
    manifest = r.json()
    manifest_caps = [c["name"] for c in manifest["capabilities"]]
    print(f"  Manifest caps:   {len(manifest_caps)} ({', '.join(manifest_caps)})")
    print(f"  Source:          {manifest['generated_from']['source']}")

    # ── 6. Ingest runtime events ─────────────────────────────────────
    print("\n> Step 6: Ingest runtime events")

    def make_event(tool_name: str, *, approval: dict | None = None) -> dict:
        return {
            "schema_version": "0.1",
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system_id": DEMO_SYSTEM_ID,
            "deployment_id": "demo",
            "environment": "local",
            "event_type": "tool_start",
            "trace_id": str(uuid.uuid4()),
            "span_id": str(uuid.uuid4()),
            "source": {"type": "demo"},
            "outcome": {"status": "started"},
            "tool": {"name": tool_name},
            "component": {"kind": "tool", "name": tool_name},
            **({"approval": approval} if approval else {}),
        }

    events_to_ingest = [
        # Approved capability — but only approval.granted (not trusted)
        make_event("refund_execute", approval={"required": True, "granted": True}),
        # Denied capability — should trigger R_ACAP_denied_observed
        make_event("delete_customer"),
    ]

    for ev in events_to_ingest:
        r = client.post("/evidence/events", json={"event": ev})
        assert r.status_code in (200, 201), r.text

    print(f"  Events ingested: {len(events_to_ingest)}")
    print(f"    refund_execute   (approved, approval.granted only — not trusted)")
    print(f"    delete_customer  (denied capability)")

    # ── 7. Run ACAP rules ────────────────────────────────────────────
    print("\n> Step 7: Run ACAP rules")
    r = client.post(f"/systems/{DEMO_SYSTEM_ID}/rules/run-acap")
    assert r.status_code == 200, r.text
    rules_result = r.json()
    print(f"  Events evaluated: {rules_result['events_evaluated']}")
    print(f"  Findings:         {rules_result['findings_created']}")

    # ── 8. Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  Summary")
    print("=" * 64)
    findings = rules_result["findings"]
    rule_ids = sorted({f["rule_id"] for f in findings})

    print(f"  Scanner candidates:        {len(candidates)}")
    print(f"  Approved capabilities:     {len(approved_names)}")
    print(f"  Rejected capabilities:     {len(rejected_names)}")
    print(f"  ACAP version:              {acap['acap_version_id']}")
    print(f"  Manifest capabilities:     {len(manifest_caps)}")
    print(f"  Runtime events ingested:   {len(events_to_ingest)}")
    print(f"  ACAP findings created:     {len(findings)}")
    print(f"  Finding rule IDs:          {', '.join(rule_ids)}")
    print()

    for f in findings:
        sev = f.get("severity", "?")
        rule = f["rule_id"]
        cap_name = f.get("capability_name", "?")
        print(f"  [{sev.upper():6s}] {rule}")
        print(f"           capability: {cap_name}")
        print(f"           {f['description']}")
        print()

    ok = len(findings) > 0
    denied_found = any(f["rule_id"] == "R_ACAP_denied_observed" for f in findings)
    approval_found = any(f["rule_id"] == "R_ACAP_approval_required_missing" for f in findings)

    print("  Checks:")
    print(f"    ACAP findings exist:        {'PASS' if ok else 'FAIL'}")
    print(f"    Denied capability finding:  {'PASS' if denied_found else 'FAIL'}")
    print(f"    Approval missing finding:   {'PASS' if approval_found else 'FAIL'}")
    print()

    client.close()
    tmp.cleanup()
    os.environ.pop("EVIDENCE_DB_PATH", None)

    return 0 if (ok and denied_found and approval_found) else 1


if __name__ == "__main__":
    sys.exit(main())
