"""Generate coverage.json and run-summary.md from scenario-run evidence.

Reads artifacts/governance/scenarios/manifest.json plus the referenced
events.jsonl line ranges. Purely derived outputs; raw evidence is not touched.

Usage: python -m governance_probe.coverage_report
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ART = REPO_ROOT / "artifacts" / "governance"
EVENTS_FILE = ART / "events.jsonl"
MANIFEST = ART / "scenarios" / "manifest.json"
COVERAGE_OUT = ART / "coverage.json"
SUMMARY_OUT = ART / "run-summary.md"

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
# Hex/UUID guard: sha256 hashes and UUID segments legitimately contain long
# digit runs, so a card-like run only counts when not embedded in a longer
# hex string and not attached to a hyphenated identifier.
_LONG_DIGITS = re.compile(r"(?<![0-9a-fA-F-])\d{12,19}(?![0-9a-fA-F-])")
# Values that must never appear in evidence (fake test users + secret shapes).
_LEAK_PATTERNS = {
    # "TestUser" catches the full fake names; bare first names with safe word
    # boundaries are also checked ("Deny"/"Failure" collide with normal event
    # vocabulary and are only detectable via the TestUser prefix).
    "test_user_name": re.compile(r"TestUser|Priya|Mallory|\bRaj\b", re.IGNORECASE),
    "openrouter_key_shape": re.compile(r"sk-or-[A-Za-z0-9-]{8,}"),
    "bearer_header": re.compile(r"Bearer\s+[A-Za-z0-9._-]{10,}"),
    "system_prompt_text": re.compile(r"restaurant waiter bot", re.IGNORECASE),
    "raw_email": _EMAIL,
    "card_like_digits": _LONG_DIGITS,
}


def _load_events(start: int, end: int) -> list[dict]:
    out = []
    with EVENTS_FILE.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if start <= i < end:
                out.append(json.loads(line))
    return out


def _connectivity(events: list[dict]) -> dict:
    spans_by_trace: dict[str, set] = defaultdict(set)
    for e in events:
        spans_by_trace[e["trace_id"]].add(e["span_id"])
    orphans = []
    roots = 0
    for e in events:
        parent = e.get("parent_span_id")
        if parent is None:
            if e["event_type"].endswith("_start"):
                roots += 1
        elif parent not in spans_by_trace[e["trace_id"]]:
            orphans.append(e["event_id"])
    return {
        "trace_count": len(spans_by_trace),
        "root_start_events": roots,
        "orphan_events": orphans,
        "fully_connected": not orphans,
    }


def _duplicates(events: list[dict]) -> dict:
    id_counts = Counter(e["event_id"] for e in events)
    pair_counts = Counter((e["span_id"], e["event_type"]) for e in events)
    return {
        "duplicate_event_ids": [k for k, v in id_counts.items() if v > 1],
        "duplicate_span_event_pairs": [list(k) for k, v in pair_counts.items() if v > 1],
    }


def _sanitization(events: list[dict]) -> dict:
    hits: dict[str, list[str]] = {k: [] for k in _LEAK_PATTERNS}
    redacted_results = 0
    for e in events:
        line = json.dumps(e, ensure_ascii=False)
        for name, pattern in _LEAK_PATTERNS.items():
            if pattern.search(line):
                hits[name].append(e["event_id"])
        summary = (e.get("attributes") or {}).get("result_summary")
        if isinstance(summary, str) and summary.startswith("<redacted-data-class:"):
            redacted_results += 1
    return {
        "leak_hits": {k: v for k, v in hits.items() if v},
        "clean": not any(hits.values()),
        "data_class_redacted_tool_results": redacted_results,
        "note": "menu text in get_menu/place_order summaries is public test data by design",
    }


def _external_actions(events: list[dict], scenario: str, order_written: bool) -> list[dict]:
    """Every external/write tool_start must have a paired outcome event."""
    ends: dict[str, dict] = {}
    for e in events:
        if e["event_type"] in ("tool_end", "tool_error"):
            ends[e["span_id"]] = e
    actions = []
    for e in events:
        if e["event_type"] != "tool_start":
            continue
        tool = e.get("tool") or {}
        if not (tool.get("external_side_effect") or tool.get("action_type") == "write"):
            continue
        outcome = ends.get(e["span_id"])
        approval = e.get("approval") or {}
        actions.append(
            {
                "scenario": scenario,
                "tool": tool.get("name"),
                "start_event_id": e["event_id"],
                "outcome_event_id": outcome["event_id"] if outcome else None,
                "outcome_status": (outcome or {}).get("outcome", {}).get("status"),
                "outcome_error_type": (outcome or {}).get("outcome", {}).get("error_type"),
                "approval_required": approval.get("required"),
                # None means "no approval evidence" — never treated as granted.
                "approval_granted": approval.get("granted"),
                "order_log_write_observed": order_written,
            }
        )
    return actions


def _field_presence(events: list[dict]) -> list[dict]:
    llm_end = [e for e in events if e["event_type"] == "llm_end"]
    llm_start = [e for e in events if e["event_type"] == "llm_start"]
    tool_start = [e for e in events if e["event_type"] == "tool_start"]
    terminal = [e for e in events if e["event_type"].endswith(("_end", "_error"))]

    def rate(items, fn):
        items = list(items)
        if not items:
            return None
        return round(sum(1 for i in items if fn(i)) / len(items), 3)

    return [
        {"field": "schema_version/event_id/timestamp", "status": "captured", "presence": rate(events, lambda e: all(k in e for k in ("schema_version", "event_id", "timestamp")))},
        {"field": "system_id/deployment_id/environment", "status": "captured", "presence": rate(events, lambda e: all(e.get(k) for k in ("system_id", "deployment_id", "environment")))},
        {"field": "session_id", "status": "captured_for_new_events", "presence": rate(events, lambda e: bool(e.get("session_id"))), "note": "historical scenario events may predate first-class session_id"},
        {"field": "trace_id/span_id/parent link", "status": "captured", "presence": rate(events, lambda e: bool(e.get("trace_id") and e.get("span_id")))},
        {"field": "event_type + component kind/name", "status": "captured", "presence": rate(events, lambda e: bool(e.get("event_type") and (e.get("component") or {}).get("kind")))},
        {"field": "model provider/name", "status": "captured", "presence": rate(llm_start + llm_end, lambda e: bool((e.get("model") or {}).get("name") and (e.get("model") or {}).get("provider")))},
        {"field": "prompt template_hash / message shape", "status": "captured", "presence": rate(llm_start, lambda e: bool((e.get("prompt") or {}).get("template_hash")))},
        {"field": "prompt template_id", "status": "annotation_required", "presence": rate(llm_start, lambda e: (e.get("prompt") or {}).get("template_id") is not None), "note": "no template registry exists; hash only"},
        {"field": "tool name + action classification", "status": "captured_with_annotation", "presence": rate(tool_start, lambda e: (e.get("tool") or {}).get("action_type") not in (None, "unknown")), "note": "action_type from governance-tool-overrides.yaml"},
        {"field": "tool sanitized arguments + outcome", "status": "captured", "presence": rate(tool_start, lambda e: "sanitized_arguments" in (e.get("tool") or {}))},
        {"field": "retrieval source identifiers", "status": "missing", "presence": 0.0, "note": "FAISS similarity_search is called inside get_menu/show_receipt, not via a retriever run; no retriever events are emitted"},
        {"field": "agent identity", "status": "captured", "presence": rate(events, lambda e: bool((e.get("actor") or {}).get("agent_id")))},
        {"field": "approval required/granted", "status": "captured_with_annotation", "presence": rate([e for e in tool_start if (e.get("tool") or {}).get("name") == "confirm_order"], lambda e: (e.get("approval") or {}).get("required") is not None), "note": "approval.required declared in overrides; approval.granted is not derived from model-supplied response arguments"},
        {"field": "data classification", "status": "annotation_required", "presence": rate(tool_start, lambda e: bool((e.get("data") or {}).get("classifications"))), "note": "from overrides file only"},
        {"field": "status + duration", "status": "captured", "presence": rate(terminal, lambda e: (e.get("outcome") or {}).get("duration_ms") is not None)},
        {"field": "error type on failures", "status": "captured", "presence": rate([e for e in events if e["event_type"].endswith("_error")], lambda e: bool((e.get("outcome") or {}).get("error_type")))},
        {"field": "token usage", "status": "partial", "presence": rate(llm_end, lambda e: (e.get("outcome") or {}).get("total_tokens") is not None), "note": "depends on provider returning usage metadata"},
    ]


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    runs = manifest["runs"]
    baseline_runs = [r for r in runs if r["mode"] == "baseline"]
    instr_runs = [r for r in runs if r["mode"] == "instrumented"]

    all_events: list[dict] = []
    per_scenario: list[dict] = []
    external_actions: list[dict] = []
    for r in instr_runs:
        events = _load_events(r["events_line_start"], r["events_line_end"])
        all_events.extend(events)
        counts = Counter(e["event_type"] for e in events)
        conn = _connectivity(events)
        tool_names = sorted(
            {(e.get("tool") or {}).get("name") for e in events if e["event_type"] == "tool_start"} - {None}
        )
        external_actions.extend(_external_actions(events, r["scenario"], r["order_written"]))
        per_scenario.append(
            {
                "scenario": r["scenario"],
                "scenario_class": r["scenario_class"],
                "returncode": r["returncode"],
                "event_counts": dict(counts),
                "tools_invoked": tool_names,
                "trace_connectivity": conn,
                "order_written": r["order_written"],
                "expect_order_write": r["expect_order_write"],
            }
        )

    coverage = {
        "schema_version": "0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str(MANIFEST.relative_to(REPO_ROOT)),
        "baseline": {
            "runs": len(baseline_runs),
            "governance_events_written": sum(r["new_event_count"] for r in baseline_runs),
            "orders_written": [r["scenario"] for r in baseline_runs if r["order_written"]],
            "returncodes": {r["scenario"]: r["returncode"] for r in baseline_runs},
        },
        "instrumented": {
            "runs": len(instr_runs),
            "total_events": len(all_events),
            "event_counts_by_type": dict(Counter(e["event_type"] for e in all_events)),
            "scenarios": per_scenario,
        },
        "trace_connectivity_overall": _connectivity(all_events),
        "duplicates": _duplicates(all_events),
        "sanitization": _sanitization(all_events),
        "external_actions": external_actions,
        "approval_policy_note": "approval_granted=null means no approval evidence was captured; it is reported as missing, never as approval success",
        "required_field_coverage": _field_presence(all_events),
    }
    COVERAGE_OUT.write_text(json.dumps(coverage, indent=2), encoding="utf-8")

    # ---- markdown summary ----
    lines = [
        "# Scenario run summary",
        "",
        f"Generated: {coverage['generated_at']}",
        f"Source: `{coverage['source_manifest']}`, events `artifacts/governance/events.jsonl`",
        "",
        "Fake test users only; the only side effect in this application is an append to the local `orders_log.json` test file (status `PENDING STAFF VERIFICATION`). No real order, payment, message or reservation was executed.",
        "",
        "## Runs",
        "",
        "| Scenario | Class | Baseline rc | Instr. rc | Events | Traces | Connected | Order written (base/instr) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    base_by_name = {r["scenario"]: r for r in baseline_runs}
    for s in per_scenario:
        b = base_by_name.get(s["scenario"], {})
        lines.append(
            f"| {s['scenario']} | {s['scenario_class']} | {b.get('returncode')} | {s['returncode']} | "
            f"{sum(s['event_counts'].values())} | {s['trace_connectivity']['trace_count']} | "
            f"{'yes' if s['trace_connectivity']['fully_connected'] else 'NO'} | "
            f"{b.get('order_written')}/{s['order_written']} |"
        )
    lines += [
        "",
        f"Baseline governance events written: **{coverage['baseline']['governance_events_written']}** (must be 0).",
        "",
        "## Event counts by type (instrumented)",
        "",
        "| Event type | Count |",
        "|---|---|",
    ]
    for etype, count in sorted(coverage["instrumented"]["event_counts_by_type"].items()):
        lines.append(f"| {etype} | {count} |")
    conn = coverage["trace_connectivity_overall"]
    dup = coverage["duplicates"]
    san = coverage["sanitization"]
    lines += [
        "",
        "## Trace connectivity",
        "",
        f"- Traces: {conn['trace_count']} (one per agent.invoke turn plus startup model probe)",
        f"- Orphan events: {len(conn['orphan_events'])}",
        f"- Fully connected: {'yes' if conn['fully_connected'] else 'NO — see coverage.json orphan_events'}",
        "",
        "## Duplicates",
        "",
        f"- Duplicate event IDs: {len(dup['duplicate_event_ids'])}",
        f"- Duplicate (span, event_type) pairs: {len(dup['duplicate_span_event_pairs'])}",
        "",
        "## Sanitization",
        "",
        f"- Leak scan clean: {'yes' if san['clean'] else 'NO'}",
        f"- Leak hits: {json.dumps(san['leak_hits']) if san['leak_hits'] else 'none'}",
        f"- Tool results redacted by data class: {san['data_class_redacted_tool_results']}",
        f"- {san['note']}",
        "",
        "## External / write actions",
        "",
        "| Scenario | Tool | Start event | Outcome status | Error type | Approval required | Approval granted | orders_log write |",
        "|---|---|---|---|---|---|---|---|",
    ]
    if not external_actions:
        lines.append("| (none observed) | | | | | | | |")
    for a in external_actions:
        lines.append(
            f"| {a['scenario']} | {a['tool']} | `{a['start_event_id'][:8]}` | {a['outcome_status']} | "
            f"{a['outcome_error_type'] or '-'} | {a['approval_required']} | "
            f"{'MISSING' if a['approval_granted'] is None else a['approval_granted']} | {a['order_log_write_observed']} |"
        )
    lines += [
        "",
        "Approval semantics: `approval_granted=null` is reported as **missing approval evidence**, never as approval success.",
        "",
        "## Required-field coverage",
        "",
        "| Field | Status | Presence | Note |",
        "|---|---|---|---|",
    ]
    for f in coverage["required_field_coverage"]:
        lines.append(f"| {f['field']} | {f['status']} | {f['presence']} | {f.get('note', '')} |")
    lines += [
        "",
        "## Artifacts",
        "",
        "- Raw events: `artifacts/governance/events.jsonl` (append-only)",
        "- Per-run transcripts: `artifacts/governance/scenarios/*__{baseline,instrumented}.stdout.txt`",
        "- Run manifest: `artifacts/governance/scenarios/manifest.json`",
        "- Machine-readable coverage: `artifacts/governance/coverage.json`",
        "",
    ]
    SUMMARY_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {COVERAGE_OUT}")
    print(f"wrote {SUMMARY_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
