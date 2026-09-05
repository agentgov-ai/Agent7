"""Map local governance JSONL evidence to OTLP traces.

Milestone 5 deliberately treats ``artifacts/governance/events.jsonl`` as the
source of truth. This module does not instrument LangChain or any framework;
it only converts the validated governance event model into vendor-neutral
OpenTelemetry trace payloads and optionally posts them to a local collector.

Usage:
    python -m governance_probe.otel_export --no-send
    python -m governance_probe.otel_export --endpoint http://127.0.0.1:4318/v1/traces
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parents[2]
ART = REPO_ROOT / "artifacts" / "governance"
EVENTS_FILE = ART / "events.jsonl"
OTEL_OUT = ART / "otel"
PAYLOAD_OUT = OTEL_OUT / "otlp-traces.json"
REPORT_OUT = OTEL_OUT / "mapping-report.json"
DEFAULT_ENDPOINT = "http://127.0.0.1:4318/v1/traces"

RAW_TEXT_PROBES = {
    "system_prompt_text": re.compile(r"restaurant waiter bot", re.IGNORECASE),
    "stdin_order_text": re.compile(r"I want to order", re.IGNORECASE),
    "adversarial_input_text": re.compile(r"ignore (all|previous) instructions", re.IGNORECASE),
    "known_fake_response": re.compile(r"SECRET-RESPONSE-TEXT", re.IGNORECASE),
    "known_fake_prompt": re.compile(r"SECRET-PROMPT-TEXT", re.IGNORECASE),
}

PRIVACY_FILTERED_FIELDS = {
    "tool.sanitized_arguments": "tool argument values may contain stdin/adversarial text; arguments_hash is exported instead",
    "attributes.result_summary": "tool result summaries may contain raw response text; result_hash is exported instead",
}


def load_events(path: str | Path = EVENTS_FILE) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            event = json.loads(line)
            event["_jsonl_line"] = line_number
            events.append(event)
    return events


def _to_unix_nano(value: str | None) -> str:
    if not value:
        return "0"
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return str(int(dt.timestamp() * 1_000_000_000))


def _stable_hex(value: Any, length: int) -> str:
    text = "" if value is None else str(value)
    try:
        if length == 32:
            candidate = UUID(text).hex
        else:
            candidate = UUID(text).hex[-length:]
    except Exception:
        candidate = hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]
    if not candidate or set(candidate) == {"0"}:
        candidate = "1".rjust(length, "0")
    return candidate[:length]


def otel_trace_id(governance_trace_id: Any) -> str:
    return _stable_hex(governance_trace_id, 32)


def otel_span_id(governance_span_id: Any) -> str:
    return _stable_hex(governance_span_id, 16)


def _any_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {"stringValue": ""}
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    # OTLP attributes do not support maps directly. JSON keeps nested evidence
    # deterministic without flattening arbitrary user/application structures.
    return {"stringValue": json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)}


def _kv(key: str, value: Any) -> dict[str, Any]:
    return {"key": key, "value": _any_value(value)}


def _attrs(items: dict[str, Any]) -> list[dict[str, Any]]:
    return [_kv(k, v) for k, v in sorted(items.items()) if v is not None]


def _flatten_prefixed(prefix: str, value: Any, out: dict[str, Any], *, skip: set[str] | None = None) -> None:
    if not isinstance(value, dict):
        return
    skip = skip or set()
    for key, item in value.items():
        if key in skip:
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            out[f"{prefix}.{key}"] = item
        elif isinstance(item, (list, tuple)):
            out[f"{prefix}.{key}_json"] = list(item)
        else:
            out[f"{prefix}.{key}_json"] = item


def _safe_attribute_fields(event: dict[str, Any], out: dict[str, Any]) -> None:
    attrs = event.get("attributes") or {}
    if not isinstance(attrs, dict):
        return
    for key in (
        "response_hash",
        "output_hash",
        "result_hash",
        "query_hash",
        "document_count",
        "input_shape",
        "error_message",
    ):
        if key in attrs:
            out[f"governance.attributes.{key}"] = attrs[key]


def safe_event_attributes(event: dict[str, Any]) -> dict[str, Any]:
    """Return OTLP-safe attributes for a single governance event.

    This is a whitelist. It preserves the validated governance evidence fields
    needed for transport while intentionally excluding raw-ish payload fields
    such as sanitized arguments and tool result summaries.
    """
    out: dict[str, Any] = {
        "governance.schema_version": event.get("schema_version"),
        "governance.event_id": event.get("event_id"),
        "governance.jsonl_line": event.get("_jsonl_line"),
        "governance.event_type": event.get("event_type"),
        "governance.trace_id": event.get("trace_id"),
        "governance.span_id": event.get("span_id"),
        "governance.parent_span_id": event.get("parent_span_id"),
        "governance.session_id": event.get("session_id"),
        "governance.system_id": event.get("system_id"),
        "governance.deployment_id": event.get("deployment_id"),
        "governance.environment": event.get("environment"),
        "governance.raw_content_exported": False,
        "governance.privacy.tool_arguments_capture": "hash_only",
        "governance.privacy.result_capture": "hash_only",
    }
    for field in ("source", "actor", "component", "model", "prompt", "data", "approval", "outcome"):
        _flatten_prefixed(f"governance.{field}", event.get(field), out)
    _flatten_prefixed("governance.tool", event.get("tool"), out, skip={"sanitized_arguments"})

    tool = event.get("tool") or {}
    if isinstance(tool, dict) and "sanitized_arguments" in tool:
        out["governance.tool.sanitized_arguments_exported"] = False
    attrs = event.get("attributes") or {}
    if isinstance(attrs, dict) and "result_summary" in attrs:
        out["governance.attributes.result_summary_exported"] = False
    _safe_attribute_fields(event, out)
    return out


def _span_name(events: list[dict[str, Any]]) -> str:
    chosen = next((e for e in events if str(e.get("event_type", "")).endswith("_start")), events[0])
    component = chosen.get("component") or {}
    kind = component.get("kind") or "governance"
    name = component.get("name") or chosen.get("event_type") or "event"
    return f"{kind}:{name}"


def _span_status(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in events:
        outcome = event.get("outcome") or {}
        if outcome.get("status") == "error":
            return {"code": "STATUS_CODE_ERROR", "message": str(outcome.get("error_type") or "error")}
    if any((event.get("outcome") or {}).get("status") == "success" for event in events):
        return {"code": "STATUS_CODE_OK"}
    return {"code": "STATUS_CODE_UNSET"}


def _span_times(events: list[dict[str, Any]]) -> tuple[str, str]:
    starts = [e for e in events if str(e.get("event_type", "")).endswith("_start")]
    terminals = [e for e in events if str(e.get("event_type", "")).endswith(("_end", "_error"))]
    start_ns = min(int(_to_unix_nano(e.get("timestamp"))) for e in (starts or events))
    end_source = terminals or events
    end_ns = max(int(_to_unix_nano(e.get("timestamp"))) for e in end_source)
    if end_ns <= start_ns:
        end_ns = start_ns + 1
    return str(start_ns), str(end_ns)


def _span_attributes(trace_id: str, span_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    first = events[0]
    component = first.get("component") or {}
    attrs = {
        "governance.trace_id": trace_id,
        "governance.span_id": span_id,
        "governance.parent_span_id": first.get("parent_span_id"),
        "governance.session_id": first.get("session_id"),
        "governance.system_id": first.get("system_id"),
        "governance.deployment_id": first.get("deployment_id"),
        "governance.environment": first.get("environment"),
        "governance.component.kind": component.get("kind"),
        "governance.component.name": component.get("name"),
        "governance.event_count": len(events),
        "governance.event_ids_json": [e.get("event_id") for e in events],
        "governance.raw_content_exported": False,
    }
    return attrs


def build_otlp_payload(events: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_span: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_span[(str(event.get("trace_id")), str(event.get("span_id")))].append(event)

    spans: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []
    for (trace_id, span_id), span_events in by_span.items():
        span_events.sort(key=lambda e: (e.get("timestamp") or "", e.get("_jsonl_line") or 0))
        parent_id = span_events[0].get("parent_span_id")
        start_ns, end_ns = _span_times(span_events)
        otel_events = []
        for event in span_events:
            attrs = safe_event_attributes(event)
            otel_events.append(
                {
                    "timeUnixNano": _to_unix_nano(event.get("timestamp")),
                    "name": f"governance.{event.get('event_type')}",
                    "attributes": _attrs(attrs),
                }
            )
            dispositions.append(
                {
                    "event_id": event.get("event_id"),
                    "jsonl_line": event.get("_jsonl_line"),
                    "event_type": event.get("event_type"),
                    "disposition": "mapped",
                    "otel_trace_id": otel_trace_id(trace_id),
                    "otel_span_id": otel_span_id(span_id),
                    "governance_trace_id": trace_id,
                    "governance_span_id": span_id,
                    "privacy_filtered_fields": [
                        {"field": field, "reason": reason}
                        for field, reason in PRIVACY_FILTERED_FIELDS.items()
                        if _has_dotted_field(event, field)
                    ],
                }
            )
        span: dict[str, Any] = {
            "traceId": otel_trace_id(trace_id),
            "spanId": otel_span_id(span_id),
            "name": _span_name(span_events),
            "kind": "SPAN_KIND_INTERNAL",
            "startTimeUnixNano": start_ns,
            "endTimeUnixNano": end_ns,
            "attributes": _attrs(_span_attributes(trace_id, span_id, span_events)),
            "events": otel_events,
            "status": _span_status(span_events),
        }
        if parent_id:
            span["parentSpanId"] = otel_span_id(parent_id)
        spans.append(span)

    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": _attrs(
                        {
                            "service.name": "restaurant-agent",
                            "service.namespace": "governance-probe",
                            "deployment.environment": events[0].get("environment") if events else "local",
                            "governance.source": "local-jsonl",
                            "governance.schema_version": events[0].get("schema_version") if events else None,
                        }
                    )
                },
                "scopeSpans": [
                    {
                        "scope": {
                            "name": "governance_probe.otel_export",
                            "version": "0.1",
                        },
                        "spans": sorted(spans, key=lambda s: (s["traceId"], s["startTimeUnixNano"], s["spanId"])),
                    }
                ],
            }
        ]
    }
    return payload, dispositions


def _has_dotted_field(event: dict[str, Any], dotted: str) -> bool:
    value: Any = event
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return False
        value = value[part]
    return True


def _iter_otel_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for resource_span in payload.get("resourceSpans", []):
        for scope_span in resource_span.get("scopeSpans", []):
            for span in scope_span.get("spans", []):
                out.extend(span.get("events", []))
    return out


def _attr_value(value: dict[str, Any]) -> Any:
    any_value = value.get("value", {})
    for key in ("stringValue", "boolValue", "intValue", "doubleValue"):
        if key in any_value:
            return any_value[key]
    return None


def _event_id_set_from_payload(payload: dict[str, Any]) -> set[str]:
    ids = set()
    for event in _iter_otel_events(payload):
        for attr in event.get("attributes", []):
            if attr.get("key") == "governance.event_id":
                ids.add(str(_attr_value(attr)))
    return ids


def verify_payload(
    source_events: list[dict[str, Any]],
    payload: dict[str, Any],
    dispositions: list[dict[str, Any]],
    *,
    expect_count: int | None = None,
) -> dict[str, Any]:
    source_ids = {str(e.get("event_id")) for e in source_events}
    payload_ids = _event_id_set_from_payload(payload)
    disposition_ids = {str(d.get("event_id")) for d in dispositions}
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    raw_hits = {
        name: pattern.findall(payload_text)
        for name, pattern in RAW_TEXT_PROBES.items()
        if pattern.search(payload_text)
    }
    report = {
        "schema_version": "0.1",
        "source": str(EVENTS_FILE.relative_to(REPO_ROOT)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_event_count": len(source_events),
        "expected_event_count": expect_count,
        "otel_span_count": sum(
            len(scope.get("spans", []))
            for resource in payload.get("resourceSpans", [])
            for scope in resource.get("scopeSpans", [])
        ),
        "otel_span_event_count": len(_iter_otel_events(payload)),
        "mapped_event_count": sum(1 for d in dispositions if d["disposition"] == "mapped"),
        "not_applicable_event_count": sum(1 for d in dispositions if d["disposition"] == "not_applicable"),
        "missing_from_payload": sorted(source_ids - payload_ids),
        "extra_in_payload": sorted(payload_ids - source_ids),
        "missing_dispositions": sorted(source_ids - disposition_ids),
        "raw_text_export_hits": raw_hits,
        "raw_text_export_clean": not raw_hits,
        "privacy_filtered_field_counts": _privacy_filter_counts(dispositions),
        "required_preservation": _required_preservation(source_events, payload),
        "dispositions": dispositions,
    }
    problems = []
    if expect_count is not None and len(source_events) != expect_count:
        problems.append(f"expected {expect_count} source events, found {len(source_events)}")
    if source_ids != payload_ids:
        problems.append("payload event IDs do not match source event IDs")
    if source_ids != disposition_ids:
        problems.append("mapping dispositions do not match source event IDs")
    if raw_hits:
        problems.append("raw text probes matched exported OTLP payload")
    failed_preservation = [p for p in report["required_preservation"] if not p["ok"]]
    if failed_preservation:
        problems.append("required governance fields were not preserved")
    report["ok"] = not problems
    report["problems"] = problems
    return report


def _privacy_filter_counts(dispositions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for disposition in dispositions:
        for item in disposition.get("privacy_filtered_fields") or []:
            field = item["field"]
            counts[field] = counts.get(field, 0) + 1
    return counts


def _required_preservation(source_events: list[dict[str, Any]], payload: dict[str, Any]) -> list[dict[str, Any]]:
    attrs_by_event: dict[str, dict[str, Any]] = {}
    for otel_event in _iter_otel_events(payload):
        attrs = {a["key"]: _attr_value(a) for a in otel_event.get("attributes", [])}
        event_id = attrs.get("governance.event_id")
        if event_id:
            attrs_by_event[str(event_id)] = attrs

    checks = [
        ("trace_id", "governance.trace_id"),
        ("span_id", "governance.span_id"),
        ("parent_span_id", "governance.parent_span_id"),
        ("session_id", "governance.session_id"),
        ("event_id", "governance.event_id"),
        ("event_type", "governance.event_type"),
        ("component.kind", "governance.component.kind"),
        ("component.name", "governance.component.name"),
        ("tool.name", "governance.tool.name"),
        ("tool.action_type", "governance.tool.action_type"),
        ("approval.required", "governance.approval.required"),
        ("approval.granted", "governance.approval.granted"),
        ("approval.policy_id", "governance.approval.policy_id"),
        ("outcome.status", "governance.outcome.status"),
        ("outcome.error_type", "governance.outcome.error_type"),
        ("outcome.input_tokens", "governance.outcome.input_tokens"),
        ("outcome.output_tokens", "governance.outcome.output_tokens"),
        ("outcome.total_tokens", "governance.outcome.total_tokens"),
        ("prompt.content_capture", "governance.prompt.content_capture"),
        ("prompt.template_hash", "governance.prompt.template_hash"),
        ("data.classifications", "governance.data.classifications_json"),
    ]
    results = []
    for source_field, otel_attr in checks:
        applicable = 0
        preserved = 0
        for event in source_events:
            source_value = _get_dotted(event, source_field)
            if source_value is None:
                continue
            applicable += 1
            attrs = attrs_by_event.get(str(event.get("event_id")), {})
            exported = attrs.get(otel_attr)
            if isinstance(source_value, (list, dict)):
                ok = exported == json.dumps(source_value, sort_keys=True, ensure_ascii=False, default=str)
            elif isinstance(source_value, bool):
                ok = exported is source_value
            else:
                ok = str(exported) == str(source_value)
            if ok:
                preserved += 1
        results.append(
            {
                "source_field": source_field,
                "otel_attribute": otel_attr,
                "applicable_events": applicable,
                "preserved_events": preserved,
                "ok": applicable == preserved,
                "classification": "not_applicable" if applicable == 0 else "mapped",
            }
        )
    return results


def _get_dotted(value: dict[str, Any], dotted: str) -> Any:
    current: Any = value
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def write_outputs(payload: dict[str, Any], report: dict[str, Any], out_dir: Path = OTEL_OUT) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / PAYLOAD_OUT.name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / REPORT_OUT.name).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def send_otlp_http(payload: dict[str, Any], endpoint: str = DEFAULT_ENDPOINT, timeout: float = 10.0) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"ok": 200 <= response.status < 300, "status": response.status, "endpoint": endpoint}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "endpoint": endpoint, "error": exc.read().decode("utf-8", "replace")}
    except OSError as exc:
        return {"ok": False, "status": None, "endpoint": endpoint, "error": str(exc)}


def collector_connectivity_test(endpoint: str = DEFAULT_ENDPOINT, timeout: float = 5.0) -> dict[str, Any]:
    now_ns = str(int(datetime.now(timezone.utc).timestamp() * 1_000_000_000))
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": _attrs(
                        {
                            "service.name": "restaurant-agent",
                            "governance.source": "collector-connectivity-test",
                        }
                    )
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "governance_probe.otel_export.connectivity", "version": "0.1"},
                        "spans": [
                            {
                                "traceId": "11111111111111111111111111111111",
                                "spanId": "1111111111111111",
                                "name": "governance.collector_connectivity",
                                "kind": "SPAN_KIND_INTERNAL",
                                "startTimeUnixNano": now_ns,
                                "endTimeUnixNano": str(int(now_ns) + 1),
                                "attributes": _attrs({"governance.connectivity_test": True}),
                                "status": {"code": "STATUS_CODE_OK"},
                            }
                        ],
                    }
                ],
            }
        ]
    }
    result = send_otlp_http(payload, endpoint=endpoint, timeout=timeout)
    result["payload_shape"] = "resourceSpans.scopeSpans.spans"
    result["content_type"] = "application/json"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export local governance JSONL events as OTLP traces.")
    parser.add_argument("--events", type=Path, default=EVENTS_FILE)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--out-dir", type=Path, default=OTEL_OUT)
    parser.add_argument("--expect-count", type=int, default=376)
    parser.add_argument("--no-send", action="store_true", help="Build and verify payload without posting to the collector.")
    parser.add_argument("--connectivity-test", action="store_true", help="Send a one-span OTLP JSON payload before the full export.")
    args = parser.parse_args(argv)

    events = load_events(args.events)
    payload, dispositions = build_otlp_payload(events)
    report = verify_payload(events, payload, dispositions, expect_count=args.expect_count)
    connectivity_result = {"skipped": not args.connectivity_test}
    if args.connectivity_test:
        connectivity_result = collector_connectivity_test(args.endpoint)
    report["collector_connectivity_test"] = connectivity_result
    send_result = {"skipped": True}
    if report["ok"] and not args.no_send and connectivity_result.get("ok", True):
        send_result = send_otlp_http(payload, args.endpoint)
        report["collector_send"] = send_result
    else:
        report["collector_send"] = send_result
    write_outputs(payload, report, args.out_dir)

    print(f"source events: {report['source_event_count']}")
    print(f"otel spans: {report['otel_span_count']}")
    print(f"otel span events: {report['otel_span_event_count']}")
    print(f"mapped: {report['mapped_event_count']} not_applicable: {report['not_applicable_event_count']}")
    print(f"raw text export clean: {report['raw_text_export_clean']}")
    print(f"wrote: {args.out_dir / PAYLOAD_OUT.name}")
    print(f"wrote: {args.out_dir / REPORT_OUT.name}")
    if not report["ok"]:
        for problem in report["problems"]:
            print(f"problem: {problem}", file=sys.stderr)
        return 1
    if args.connectivity_test:
        print(f"collector connectivity test: {connectivity_result}")
        if not connectivity_result.get("ok"):
            return 3
    if not args.no_send and not send_result.get("ok"):
        print(f"collector send failed: {send_result}", file=sys.stderr)
        return 2
    if not args.no_send:
        print(f"collector send: {send_result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
