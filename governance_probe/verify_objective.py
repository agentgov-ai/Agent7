"""Structural verification for the first objective (no new features).

Checks, over the FULL artifacts/governance/events.jsonl:
1. Minimal structural validation against schemas/governance-event.schema.json
   (required fields, enums, nested source/outcome requirements) — hand-rolled
   because jsonschema is not installed and adding deps requires asking.
2. Trace parentage: parent_span_id resolves to a span within the same trace.
3. Event IDs unique; timestamps UTC-parseable.
4. No duplicate terminal events per span (span_id + terminal event_type).
5. Raw-content absence: no system-prompt text, no raw customer utterances,
   prompt.content_capture never 'full'/'sanitized' beyond policy.
6. Baseline vs instrumented wall-clock per scenario from the manifest.

Usage: python -m governance_probe.verify_objective
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ART = REPO_ROOT / "artifacts" / "governance"
EVENTS = ART / "events.jsonl"
MANIFEST = ART / "scenarios" / "manifest.json"

REQUIRED = [
    "schema_version", "event_id", "timestamp", "system_id", "deployment_id",
    "environment", "event_type", "trace_id", "span_id", "source", "outcome",
]
EVENT_TYPES = {
    "chain_start", "chain_end", "chain_error", "agent_action", "agent_finish",
    "llm_start", "llm_end", "llm_error", "tool_start", "tool_end", "tool_error",
    "retriever_start", "retriever_end", "retriever_error",
    "approval_requested", "approval_decision", "custom",
}
OUTCOME_STATUS = {"started", "success", "error", "unknown"}
ACTION_TYPES = {"read", "write", "communicate", "execute", "unknown", None}
CONTENT_CAPTURE = {"none", "hash", "sanitized", "full"}
TERMINAL = {"chain_end", "chain_error", "llm_end", "llm_error", "tool_end",
            "tool_error", "retriever_end", "retriever_error"}

# Raw-content probes: system prompt fragment and raw utterance markers.
RAW_PROBES = [
    re.compile(r"restaurant waiter bot", re.IGNORECASE),
    re.compile(r"I want to order", re.IGNORECASE),  # scenario stdin text
    re.compile(r"ignore (all|previous) instructions", re.IGNORECASE),  # s5 injection text
]


def main() -> int:
    lines = EVENTS.read_text(encoding="utf-8").splitlines()
    problems: list[str] = []
    event_ids: set[str] = set()
    spans_by_trace: dict[str, set[str]] = {}
    parents: list[tuple[int, str, str]] = []  # (line, trace, parent_span)
    terminal_seen: set[tuple[str, str]] = set()
    events = []

    for i, line in enumerate(lines):
        try:
            e = json.loads(line)
        except json.JSONDecodeError as ex:
            problems.append(f"line {i}: invalid JSON: {ex}")
            continue
        events.append((i, e))
        for f in REQUIRED:
            if f not in e:
                problems.append(f"line {i}: missing required field '{f}'")
        et = e.get("event_type")
        if et not in EVENT_TYPES:
            problems.append(f"line {i}: bad event_type {et!r}")
        src = e.get("source")
        if not isinstance(src, dict) or "type" not in src:
            problems.append(f"line {i}: source missing 'type'")
        out = e.get("outcome")
        if not isinstance(out, dict) or out.get("status") not in OUTCOME_STATUS:
            problems.append(f"line {i}: bad outcome.status {out!r}")
        tool = e.get("tool")
        if tool and tool.get("action_type") not in ACTION_TYPES:
            problems.append(f"line {i}: bad tool.action_type {tool.get('action_type')!r}")
        prompt = e.get("prompt")
        if prompt:
            cc = prompt.get("content_capture")
            if cc not in CONTENT_CAPTURE:
                problems.append(f"line {i}: bad prompt.content_capture {cc!r}")
            if cc in ("full", "sanitized"):
                problems.append(f"line {i}: content_capture={cc} violates privacy default")
        eid = e.get("event_id")
        if eid in event_ids:
            problems.append(f"line {i}: duplicate event_id {eid}")
        event_ids.add(eid)
        try:
            ts = datetime.fromisoformat(e["timestamp"])
            if ts.tzinfo is None:
                problems.append(f"line {i}: naive timestamp")
        except Exception:
            problems.append(f"line {i}: unparseable timestamp {e.get('timestamp')!r}")
        tr, sp = e.get("trace_id"), e.get("span_id")
        spans_by_trace.setdefault(tr, set()).add(sp)
        if e.get("parent_span_id"):
            parents.append((i, tr, e["parent_span_id"]))
        if et in TERMINAL:
            key = (sp, et)
            if key in terminal_seen:
                problems.append(f"line {i}: duplicate terminal event {et} for span {sp}")
            terminal_seen.add(key)

    for i, tr, parent in parents:
        if parent not in spans_by_trace.get(tr, set()):
            problems.append(f"line {i}: parent_span_id {parent} not found in trace {tr}")

    # Raw-content scan across the whole file text.
    raw_hits = [(p.pattern, p.findall(EVENTS.read_text(encoding="utf-8"))) for p in RAW_PROBES]
    raw_hits = [(pat, hits) for pat, hits in raw_hits if hits]
    for pat, hits in raw_hits:
        problems.append(f"raw-content probe matched {len(hits)}x: {pat}")

    print(f"events: {len(events)} lines, {len(event_ids)} unique event IDs, "
          f"{len(spans_by_trace)} traces")
    print(f"structural problems: {len(problems)}")
    for p in problems[:40]:
        print(f"  - {p}")

    # Baseline vs instrumented wall-clock per scenario.
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    timing: dict[str, dict[str, float]] = {}
    for r in manifest["runs"]:
        try:
            dur = (datetime.fromisoformat(r["finished_utc"]) -
                   datetime.fromisoformat(r["started_utc"])).total_seconds()
        except Exception:
            continue
        timing.setdefault(r["scenario"], {})[r["mode"]] = dur
    print("\nbaseline vs instrumented wall-clock (s) [includes LLM latency variance]:")
    for scen, modes in sorted(timing.items()):
        b, ins = modes.get("baseline"), modes.get("instrumented")
        delta = f"{ins - b:+.1f}s" if b is not None and ins is not None else "n/a"
        print(f"  {scen}: baseline={b if b is not None else 'n/a'} "
              f"instrumented={ins if ins is not None else 'n/a'} delta={delta}")

    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
