#!/usr/bin/env python
"""Demonstrate manifest-based instrumentation.

Run from this directory:
    cd examples/manifest-instrumentation
    python run_example.py

Events are written to events.jsonl.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure the SDK is importable
SDK_ROOT = Path(__file__).resolve().parents[2] / "sdk-python"
sys.path.insert(0, str(SDK_ROOT))

# Ensure *this* directory is importable so "app" module resolves
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai_governance import GovernanceClient

OUT = Path(__file__).resolve().parent / "events.jsonl"
OUT.unlink(missing_ok=True)

# 1. Create client from manifest
gov = GovernanceClient.from_config("governance.yaml", jsonl_path=str(OUT))

# 2. Instrument approved capabilities
results = gov.instrument_from_config()
print("Instrumentation results:")
for r in results:
    print(f"  {r['name']}: {r['status']}")

# 3. Call functions normally — approved ones emit events automatically
from app import internal_helper, process_refund, send_notification

print("\nCalling process_refund...")
result = process_refund("ORD-001", 2599)
print(f"  Result: {result}")

print("Calling send_notification...")
result = send_notification("user@example.com", "Your refund is ready")
print(f"  Result: {result}")

print("Calling internal_helper (not wrapped)...")
result = internal_helper()
print(f"  Result: {result}")

# 4. Show captured events
events = [json.loads(line) for line in OUT.read_text(encoding="utf-8").splitlines() if line.strip()]
print(f"\nCaptured {len(events)} governance events:")
for e in events:
    print(f"  {e['event_type']:12s}  {(e.get('tool') or {}).get('name', '-'):20s}")
