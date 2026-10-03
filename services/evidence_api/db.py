from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "services" / "evidence_api" / "evidence.db"


def db_path() -> Path:
    return Path(os.environ.get("EVIDENCE_DB_PATH", DEFAULT_DB))


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    target = Path(path) if path else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            session_ref TEXT NOT NULL,
            session_id TEXT,
            system_id TEXT,
            trace_id TEXT NOT NULL,
            span_id TEXT NOT NULL,
            parent_span_id TEXT,
            event_type TEXT NOT NULL,
            component_kind TEXT,
            component_name TEXT,
            tool_name TEXT,
            payload_json TEXT NOT NULL,
            jsonl_line INTEGER,
            ingested_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS findings (
            finding_id TEXT PRIMARY KEY,
            rule_id TEXT NOT NULL,
            system_id TEXT,
            session_ref TEXT NOT NULL,
            severity TEXT NOT NULL,
            event_ids_json TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS assessments (
            assessment_id TEXT PRIMARY KEY,
            system_id TEXT NOT NULL,
            overall_status TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS acap_reviews (
            system_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            field TEXT NOT NULL,
            value TEXT NOT NULL,
            basis TEXT,
            condition TEXT,
            provenance TEXT NOT NULL DEFAULT 'human_decision',
            reviewed_by TEXT,
            reviewed_at TEXT NOT NULL,
            PRIMARY KEY (system_id, tool_name, field)
        );

        CREATE TABLE IF NOT EXISTS discovery_uploads (
            upload_id TEXT PRIMARY KEY,
            system_id TEXT NOT NULL,
            scanner_version TEXT,
            schema_version TEXT,
            project_hash TEXT,
            candidates_count INTEGER,
            model_surface_count INTEGER,
            scan_summary_json TEXT NOT NULL,
            model_surface_json TEXT,
            uploaded_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS capabilities (
            capability_id TEXT NOT NULL,
            upload_id TEXT NOT NULL,
            system_id TEXT NOT NULL,
            name TEXT NOT NULL,
            module_path TEXT,
            file_path TEXT,
            line_start INTEGER,
            line_end INTEGER,
            suggested_action_type TEXT,
            suggested_data_classes TEXT,
            suggested_approval_required INTEGER,
            external_side_effect INTEGER,
            risk TEXT,
            confidence REAL,
            confidence_source TEXT,
            evidence_json TEXT,
            call_chain_json TEXT,
            review_status TEXT NOT NULL DEFAULT 'pending',
            source TEXT DEFAULT 'deterministic_scanner',
            PRIMARY KEY (capability_id, upload_id)
        );

        CREATE TABLE IF NOT EXISTS capability_reviews (
            review_id TEXT PRIMARY KEY,
            capability_id TEXT NOT NULL,
            upload_id TEXT NOT NULL,
            system_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            reviewer TEXT NOT NULL DEFAULT 'local_user',
            previous_values_json TEXT,
            edited_values_json TEXT,
            evidence_shown_json TEXT,
            reviewed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS acap_versions (
            acap_version_id TEXT PRIMARY KEY,
            system_id TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            generated_at TEXT NOT NULL,
            upload_id TEXT NOT NULL,
            scanner_version TEXT,
            project_hash TEXT,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS governed_actions (
            action_id TEXT PRIMARY KEY,
            system_id TEXT NOT NULL,
            deployment_id TEXT,
            environment TEXT,
            agent_id TEXT,
            capability_id TEXT,
            capability_name TEXT NOT NULL,
            module_path TEXT,
            action_type TEXT,
            enforcement_mode TEXT NOT NULL,
            requested_enforcement_mode TEXT,
            session_id TEXT,
            trace_id TEXT,
            parent_span_id TEXT,
            arguments_hash TEXT,
            external_side_effect INTEGER,
            approval_required INTEGER,
            request_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS action_decisions (
            decision_id TEXT PRIMARY KEY,
            action_id TEXT NOT NULL,
            system_id TEXT NOT NULL,
            verdict TEXT NOT NULL,
            reason TEXT,
            reason_code TEXT,
            decided_by TEXT NOT NULL,
            matched_capability_id TEXT,
            kill_switch_id TEXT,
            matched_pattern_id TEXT,
            acap_version_id TEXT,
            acap_version_number INTEGER,
            approval_required INTEGER,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS action_records (
            record_id TEXT PRIMARY KEY,
            action_id TEXT NOT NULL UNIQUE,
            decision_id TEXT,
            system_id TEXT NOT NULL,
            executed INTEGER NOT NULL,
            execution_status TEXT NOT NULL,
            would_have_blocked INTEGER,
            duration_ms REAL,
            error_type TEXT,
            event_ids_json TEXT,
            evidence_hash TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS kill_switches (
            kill_switch_id TEXT PRIMARY KEY,
            system_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            target_capabilities_json TEXT NOT NULL,
            verdict TEXT NOT NULL DEFAULT 'DENY',
            reason TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS system_assessment_inputs (
            system_id TEXT PRIMARY KEY,
            jurisdiction TEXT,
            use_case TEXT,
            high_risk_category INTEGER NOT NULL DEFAULT 0,
            data_sensitivity TEXT,
            updated_by TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS system_enforcement_modes (
            system_id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            updated_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    _migrate_add_columns(conn)


def _migrate_add_columns(conn: sqlite3.Connection) -> None:
    """Add columns to tables created before they existed."""
    migrations = [
        ("events", "system_id"),
        ("findings", "system_id"),
        ("governed_actions", "requested_enforcement_mode"),
        ("discovery_uploads", "previous_upload_id"),
        ("discovery_uploads", "scan_sequence_number"),
    ]
    for table, column in migrations:
        try:
            conn.execute(f"SELECT {column} FROM {table} LIMIT 0")
        except sqlite3.OperationalError:
            col_type = "INTEGER" if column == "scan_sequence_number" else "TEXT"
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            conn.commit()


def reset_db(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM action_records")
    conn.execute("DELETE FROM action_decisions")
    conn.execute("DELETE FROM governed_actions")
    conn.execute("DELETE FROM kill_switches")
    conn.execute("DELETE FROM system_enforcement_modes")
    conn.execute("DELETE FROM system_assessment_inputs")
    conn.execute("DELETE FROM acap_versions")
    conn.execute("DELETE FROM capability_reviews")
    conn.execute("DELETE FROM capabilities")
    conn.execute("DELETE FROM discovery_uploads")
    conn.execute("DELETE FROM findings")
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM acap_reviews")
    conn.execute("DELETE FROM assessments")
    conn.commit()


def event_session_ref(event: dict[str, Any], fallback: str | None = None) -> str:
    return str(event.get("session_id") or fallback or "session:missing")


def insert_event(
    conn: sqlite3.Connection,
    event: dict[str, Any],
    *,
    session_ref: str | None = None,
    jsonl_line: int | None = None,
) -> bool:
    component = event.get("component") or {}
    tool = event.get("tool") or {}
    ref = event_session_ref(event, session_ref)
    try:
        conn.execute(
            """
            INSERT INTO events (
                event_id, timestamp, session_ref, session_id, system_id, trace_id, span_id,
                parent_span_id, event_type, component_kind, component_name,
                tool_name, payload_json, jsonl_line, ingested_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event["timestamp"],
                ref,
                event.get("session_id"),
                event.get("system_id"),
                event["trace_id"],
                event["span_id"],
                event.get("parent_span_id"),
                event["event_type"],
                component.get("kind"),
                component.get("name"),
                tool.get("name"),
                json.dumps(event, sort_keys=True, ensure_ascii=False, default=str),
                jsonl_line,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def list_events(conn: sqlite3.Connection, limit: int = 1000, offset: int = 0) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT payload_json, session_ref, jsonl_line
        FROM events
        ORDER BY COALESCE(jsonl_line, 1000000000), timestamp, event_id
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    out = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        payload["_session_ref"] = row["session_ref"]
        if row["jsonl_line"] is not None:
            payload["_jsonl_line"] = row["jsonl_line"]
        out.append(payload)
    return out


def all_events_for_rules(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT payload_json, session_ref, jsonl_line
        FROM events
        ORDER BY session_ref, COALESCE(jsonl_line, 1000000000), timestamp, event_id
        """
    ).fetchall()
    events = []
    for row in rows:
        event = json.loads(row["payload_json"])
        event["_session_ref"] = row["session_ref"]
        event["_jsonl_line"] = row["jsonl_line"]
        events.append(event)
    return events


def event_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])


def insert_findings(
    conn: sqlite3.Connection,
    findings: list[dict[str, Any]],
    *,
    system_id: str | None = None,
) -> None:
    if system_id:
        conn.execute("DELETE FROM findings WHERE system_id = ?", (system_id,))
    else:
        conn.execute("DELETE FROM findings")
    now = datetime.now(timezone.utc).isoformat()
    for finding in findings:
        sid = system_id or finding.get("system_id")
        conn.execute(
            """
            INSERT OR REPLACE INTO findings (
                finding_id, rule_id, system_id, session_ref, severity, event_ids_json, payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding["finding_id"],
                finding["rule_id"],
                sid,
                finding["session"],
                finding["severity"],
                json.dumps(finding["event_ids"], sort_keys=True),
                json.dumps(finding, sort_keys=True, ensure_ascii=False, default=str),
                now,
            ),
        )
    conn.commit()


def list_findings(conn: sqlite3.Connection, system_id: str | None = None) -> list[dict[str, Any]]:
    if system_id:
        rows = conn.execute(
            "SELECT payload_json FROM findings WHERE system_id = ? ORDER BY finding_id",
            (system_id,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT payload_json FROM findings ORDER BY finding_id").fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def all_events_for_system(conn: sqlite3.Connection, system_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT payload_json, session_ref, jsonl_line
        FROM events
        WHERE system_id = ?
        ORDER BY session_ref, COALESCE(jsonl_line, 1000000000), timestamp, event_id
        """,
        (system_id,),
    ).fetchall()
    events = []
    for row in rows:
        event = json.loads(row["payload_json"])
        event["_session_ref"] = row["session_ref"]
        event["_jsonl_line"] = row["jsonl_line"]
        events.append(event)
    return events


def insert_review_decision(
    conn: sqlite3.Connection,
    system_id: str,
    tool_name: str,
    field: str,
    value: str,
    basis: str | None = None,
    condition: str | None = None,
    reviewed_by: str | None = None,
) -> bool:
    conn.execute(
        """
        INSERT OR REPLACE INTO acap_reviews
            (system_id, tool_name, field, value, basis, condition, provenance, reviewed_by, reviewed_at)
        VALUES (?, ?, ?, ?, ?, ?, 'human_decision', ?, ?)
        """,
        (system_id, tool_name, field, value, basis, condition, reviewed_by,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return True


def list_review_decisions(conn: sqlite3.Connection, system_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT system_id, tool_name, field, value, basis, condition,
               provenance, reviewed_by, reviewed_at
        FROM acap_reviews
        WHERE system_id = ?
        ORDER BY tool_name, field
        """,
        (system_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def insert_assessment(conn: sqlite3.Connection, assessment: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO assessments (assessment_id, system_id, overall_status, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            assessment["assessment_id"],
            assessment["system_id"],
            assessment.get("overall_status"),
            json.dumps(assessment, sort_keys=True, ensure_ascii=False, default=str),
            assessment["assessed_at"],
        ),
    )
    conn.commit()


def list_assessments(conn: sqlite3.Connection, system_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT assessment_id, overall_status, created_at
        FROM assessments
        WHERE system_id = ?
        ORDER BY created_at DESC
        """,
        (system_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_assessment_by_id(conn: sqlite3.Connection, assessment_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT payload_json FROM assessments WHERE assessment_id = ?",
        (assessment_id,),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload_json"])


# ---------------------------------------------------------------------------
# Discovery / capability review
# ---------------------------------------------------------------------------

def insert_discovery_upload(
    conn: sqlite3.Connection,
    upload_id: str,
    system_id: str,
    scanner_version: str | None,
    schema_version: str | None,
    project_hash: str | None,
    candidates_count: int,
    model_surface_count: int,
    scan_summary_json: str,
    model_surface_json: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO discovery_uploads
            (upload_id, system_id, scanner_version, schema_version,
             project_hash, candidates_count, model_surface_count,
             scan_summary_json, model_surface_json, uploaded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            upload_id, system_id, scanner_version, schema_version,
            project_hash, candidates_count, model_surface_count,
            scan_summary_json, model_surface_json,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def insert_capabilities(
    conn: sqlite3.Connection,
    upload_id: str,
    system_id: str,
    candidates: list[dict[str, Any]],
) -> int:
    count = 0
    for cap in candidates:
        conn.execute(
            """
            INSERT OR REPLACE INTO capabilities (
                capability_id, upload_id, system_id, name, module_path, file_path,
                line_start, line_end, suggested_action_type, suggested_data_classes,
                suggested_approval_required, external_side_effect, risk,
                confidence, confidence_source, evidence_json, call_chain_json,
                review_status, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cap["capability_id"], upload_id, system_id,
                cap["name"], cap.get("module_path"), cap.get("file_path"),
                cap.get("line_start"), cap.get("line_end"),
                cap.get("suggested_action_type"),
                json.dumps(cap.get("suggested_data_classes", []), ensure_ascii=False),
                int(bool(cap.get("suggested_approval_required"))),
                int(bool(cap.get("external_side_effect"))),
                cap.get("risk"),
                cap.get("confidence"),
                cap.get("confidence_source"),
                json.dumps(cap.get("evidence", []), sort_keys=True, ensure_ascii=False, default=str),
                json.dumps(cap.get("call_chain", []), ensure_ascii=False),
                cap.get("review_status", "pending"),
                cap.get("source", "deterministic_scanner"),
            ),
        )
        count += 1
    conn.commit()
    return count


def _capability_from_row(row: sqlite3.Row) -> dict[str, Any]:
    """Deserialise a capabilities row into a plain dict."""
    return {
        "capability_id": row["capability_id"],
        "upload_id": row["upload_id"],
        "name": row["name"],
        "module_path": row["module_path"],
        "file_path": row["file_path"],
        "line_start": row["line_start"],
        "line_end": row["line_end"],
        "suggested_action_type": row["suggested_action_type"],
        "suggested_data_classes": json.loads(row["suggested_data_classes"]) if row["suggested_data_classes"] else [],
        "suggested_approval_required": bool(row["suggested_approval_required"]),
        "external_side_effect": bool(row["external_side_effect"]),
        "risk": row["risk"],
        "confidence": row["confidence"],
        "confidence_source": row["confidence_source"],
        "evidence": json.loads(row["evidence_json"]) if row["evidence_json"] else [],
        "call_chain": json.loads(row["call_chain_json"]) if row["call_chain_json"] else [],
        "review_status": row["review_status"],
        "source": row["source"],
    }


def get_discovery(conn: sqlite3.Connection, system_id: str) -> dict[str, Any] | None:
    upload = conn.execute(
        """
        SELECT upload_id, system_id, scanner_version, schema_version,
               project_hash, candidates_count, model_surface_count,
               scan_summary_json, model_surface_json, uploaded_at
        FROM discovery_uploads
        WHERE system_id = ?
        ORDER BY uploaded_at DESC LIMIT 1
        """,
        (system_id,),
    ).fetchone()
    if upload is None:
        return None

    upload_id = upload["upload_id"]
    rows = conn.execute(
        "SELECT * FROM capabilities WHERE upload_id = ? AND system_id = ? ORDER BY risk DESC, name",
        (upload_id, system_id),
    ).fetchall()
    capabilities = [_capability_from_row(r) for r in rows]

    scan_summary = json.loads(upload["scan_summary_json"]) if upload["scan_summary_json"] else {}
    model_surface = json.loads(upload["model_surface_json"]) if upload["model_surface_json"] else []

    return {
        "upload_id": upload_id,
        "system_id": system_id,
        "scanner_version": upload["scanner_version"],
        "schema_version": upload["schema_version"],
        "project_hash": upload["project_hash"],
        "uploaded_at": upload["uploaded_at"],
        "scan_summary": scan_summary,
        "model_surface": model_surface,
        "capabilities": capabilities,
    }


def get_capability(
    conn: sqlite3.Connection, system_id: str, capability_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT c.* FROM capabilities c
        JOIN discovery_uploads u ON c.upload_id = u.upload_id
        WHERE c.system_id = ? AND c.capability_id = ?
        ORDER BY u.uploaded_at DESC LIMIT 1
        """,
        (system_id, capability_id),
    ).fetchone()
    if row is None:
        return None
    return _capability_from_row(row)


def update_capability_status(
    conn: sqlite3.Connection, system_id: str, capability_id: str, status: str,
) -> bool:
    cur = conn.execute(
        """
        UPDATE capabilities SET review_status = ?
        WHERE system_id = ? AND capability_id = ?
          AND upload_id = (
              SELECT upload_id FROM discovery_uploads
              WHERE system_id = ? ORDER BY uploaded_at DESC LIMIT 1
          )
        """,
        (status, system_id, capability_id, system_id),
    )
    conn.commit()
    return cur.rowcount > 0


_ALLOWED_CAP_FIELDS = frozenset({
    "suggested_action_type", "suggested_data_classes",
    "suggested_approval_required", "external_side_effect",
    "risk", "review_status",
})


def update_capability_fields(
    conn: sqlite3.Connection,
    system_id: str,
    capability_id: str,
    updates: dict[str, Any],
) -> bool:
    sets: list[str] = []
    vals: list[Any] = []
    for col, val in updates.items():
        if col not in _ALLOWED_CAP_FIELDS:
            continue
        if col == "suggested_data_classes":
            val = json.dumps(val, ensure_ascii=False) if isinstance(val, list) else val
        elif col in ("suggested_approval_required", "external_side_effect"):
            val = int(bool(val))
        sets.append(f"{col} = ?")
        vals.append(val)
    if not sets:
        return False
    vals.extend([system_id, capability_id, system_id])
    cur = conn.execute(
        f"""
        UPDATE capabilities SET {', '.join(sets)}
        WHERE system_id = ? AND capability_id = ?
          AND upload_id = (
              SELECT upload_id FROM discovery_uploads
              WHERE system_id = ? ORDER BY uploaded_at DESC LIMIT 1
          )
        """,
        vals,
    )
    conn.commit()
    return cur.rowcount > 0


def insert_capability_review(
    conn: sqlite3.Connection,
    review_id: str,
    capability_id: str,
    upload_id: str,
    system_id: str,
    decision: str,
    reviewer: str,
    previous_values_json: str | None,
    edited_values_json: str | None,
    evidence_shown_json: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO capability_reviews (
            review_id, capability_id, upload_id, system_id, decision,
            reviewer, previous_values_json, edited_values_json,
            evidence_shown_json, reviewed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_id, capability_id, upload_id, system_id, decision,
            reviewer, previous_values_json, edited_values_json,
            evidence_shown_json, datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def list_capability_reviews(
    conn: sqlite3.Connection,
    system_id: str,
    capability_id: str | None = None,
) -> list[dict[str, Any]]:
    if capability_id:
        rows = conn.execute(
            """
            SELECT * FROM capability_reviews
            WHERE system_id = ? AND capability_id = ?
            ORDER BY reviewed_at DESC
            """,
            (system_id, capability_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM capability_reviews WHERE system_id = ? ORDER BY reviewed_at DESC",
            (system_id,),
        ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# ACAP versions
# ---------------------------------------------------------------------------

def next_acap_version_number(conn: sqlite3.Connection, system_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(version_number), 0) + 1 FROM acap_versions WHERE system_id = ?",
        (system_id,),
    ).fetchone()
    return int(row[0])


def insert_acap_version(conn: sqlite3.Connection, version: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO acap_versions
            (acap_version_id, system_id, version_number, generated_at,
             upload_id, scanner_version, project_hash, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version["acap_version_id"],
            version["system_id"],
            version["version_number"],
            version["generated_at"],
            version["generated_from"]["upload_id"],
            version["generated_from"].get("scanner_version"),
            version["generated_from"].get("project_hash"),
            json.dumps(version, sort_keys=True, ensure_ascii=False, default=str),
        ),
    )
    conn.commit()


def list_acap_versions(conn: sqlite3.Connection, system_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT acap_version_id, version_number, generated_at
        FROM acap_versions
        WHERE system_id = ?
        ORDER BY version_number DESC
        """,
        (system_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_acap_version(
    conn: sqlite3.Connection, system_id: str, version_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT payload_json FROM acap_versions WHERE system_id = ? AND acap_version_id = ?",
        (system_id, version_id),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload_json"])


# ---------------------------------------------------------------------------
# Dynamic system discovery
# ---------------------------------------------------------------------------

def list_known_system_ids(conn: sqlite3.Connection) -> set[str]:
    """Return all system_ids that appear anywhere in the database."""
    ids: set[str] = set()
    for table in ("discovery_uploads", "events", "acap_versions", "findings", "governed_actions"):
        try:
            rows = conn.execute(f"SELECT DISTINCT system_id FROM {table} WHERE system_id IS NOT NULL").fetchall()
            ids.update(row[0] for row in rows)
        except sqlite3.OperationalError:
            pass
    return ids


# ---------------------------------------------------------------------------
# Discovery changeset + review preservation
# ---------------------------------------------------------------------------

def _previous_upload(conn: sqlite3.Connection, system_id: str, current_upload_id: str) -> dict[str, Any] | None:
    """Get the upload immediately before *current_upload_id* for a system."""
    row = conn.execute(
        """
        SELECT upload_id FROM discovery_uploads
        WHERE system_id = ? AND upload_id != ?
        ORDER BY uploaded_at DESC LIMIT 1
        """,
        (system_id, current_upload_id),
    ).fetchone()
    if row is None:
        return None
    prev_id = row["upload_id"]
    caps = conn.execute(
        "SELECT * FROM capabilities WHERE upload_id = ? AND system_id = ?",
        (prev_id, system_id),
    ).fetchall()
    return {"upload_id": prev_id, "capabilities": [_capability_from_row(r) for r in caps]}


def compute_discovery_changeset(conn: sqlite3.Connection, system_id: str) -> dict[str, Any] | None:
    """Compare latest vs previous discovery upload for a system."""
    latest = get_discovery(conn, system_id)
    if latest is None:
        return None
    prev = _previous_upload(conn, system_id, latest["upload_id"])
    if prev is None:
        return None  # first scan, no changeset

    # Build lookup by capability_id, fallback name+module_path
    def _key(cap: dict) -> str:
        return cap.get("capability_id") or f"{cap.get('name', '')}:{cap.get('module_path', '')}"

    prev_map = {_key(c): c for c in prev["capabilities"]}
    curr_map = {_key(c): c for c in latest["capabilities"]}

    _CHANGE_FIELDS = ("suggested_action_type", "suggested_data_classes", "risk",
                      "confidence_source", "file_path", "line_start", "line_end",
                      "suggested_approval_required", "external_side_effect")

    new_caps = []
    changed_caps = []
    unchanged_caps = []
    removed_caps = []

    for key, cap in curr_map.items():
        prev_cap = prev_map.get(key)
        if prev_cap is None:
            new_caps.append(cap["name"])
        else:
            changed = False
            for field in _CHANGE_FIELDS:
                cv = cap.get(field)
                pv = prev_cap.get(field)
                if cv != pv:
                    changed = True
                    break
            if changed:
                changed_caps.append(cap["name"])
            else:
                unchanged_caps.append(cap["name"])

    for key, prev_cap in prev_map.items():
        if key not in curr_map:
            removed_caps.append(prev_cap["name"])

    return {
        "previous_upload_id": prev["upload_id"],
        "new": new_caps,
        "changed": changed_caps,
        "removed": removed_caps,
        "unchanged": unchanged_caps,
        "new_count": len(new_caps),
        "changed_count": len(changed_caps),
        "removed_count": len(removed_caps),
        "unchanged_count": len(unchanged_caps),
    }


def carry_forward_reviews(
    conn: sqlite3.Connection,
    system_id: str,
    new_upload_id: str,
) -> int:
    """Carry forward review_status from the previous upload to the new one.

    Returns the number of capabilities updated.
    """
    prev = _previous_upload(conn, system_id, new_upload_id)
    if prev is None:
        return 0

    def _key(cap: dict) -> str:
        return cap.get("capability_id") or f"{cap.get('name', '')}:{cap.get('module_path', '')}"

    _CHANGE_FIELDS = ("suggested_action_type", "suggested_data_classes", "risk",
                      "suggested_approval_required", "external_side_effect")

    prev_map = {_key(c): c for c in prev["capabilities"]}
    updated = 0

    new_caps = conn.execute(
        "SELECT * FROM capabilities WHERE upload_id = ? AND system_id = ?",
        (new_upload_id, system_id),
    ).fetchall()

    for row in new_caps:
        cap = _capability_from_row(row)
        key = _key(cap)
        prev_cap = prev_map.get(key)
        if prev_cap is None:
            continue  # new capability → stays pending

        prev_status = prev_cap.get("review_status", "pending")
        if prev_status == "pending":
            continue  # was pending, stays pending

        # Check if high-risk fields changed
        material_change = False
        for field in _CHANGE_FIELDS:
            if cap.get(field) != prev_cap.get(field):
                material_change = True
                break

        if material_change and prev_status in ("approved_for_acap", "edited"):
            # High-risk change on approved capability → needs_reapproval
            new_status = "needs_reapproval"
        else:
            new_status = prev_status

        conn.execute(
            """
            UPDATE capabilities SET review_status = ?
            WHERE capability_id = ? AND upload_id = ? AND system_id = ?
            """,
            (new_status, cap["capability_id"], new_upload_id, system_id),
        )
        updated += 1

    conn.commit()
    return updated


# ---------------------------------------------------------------------------
# Audit status
# ---------------------------------------------------------------------------

def get_audit_status(conn: sqlite3.Connection, system_id: str) -> dict[str, Any]:
    """Compute audit freshness for a system."""
    # Latest scan
    scan_row = conn.execute(
        "SELECT uploaded_at FROM discovery_uploads WHERE system_id = ? ORDER BY uploaded_at DESC LIMIT 1",
        (system_id,),
    ).fetchone()
    latest_scan_at = scan_row["uploaded_at"] if scan_row else None

    # Latest ACAP version
    acap_row = conn.execute(
        "SELECT acap_version_id, version_number, generated_at FROM acap_versions WHERE system_id = ? ORDER BY version_number DESC LIMIT 1",
        (system_id,),
    ).fetchone()
    acap_version_id = acap_row["acap_version_id"] if acap_row else None
    acap_generated_at = acap_row["generated_at"] if acap_row else None

    # Latest runtime event
    event_row = conn.execute(
        "SELECT MAX(timestamp) as latest FROM events WHERE system_id = ?",
        (system_id,),
    ).fetchone()
    latest_runtime_at = event_row["latest"] if event_row and event_row["latest"] else None

    # Latest assessment
    assess_row = conn.execute(
        "SELECT created_at FROM assessments WHERE system_id = ? ORDER BY created_at DESC LIMIT 1",
        (system_id,),
    ).fetchone()
    latest_assessment_at = assess_row["created_at"] if assess_row else None

    # Needs reapproval count
    reapproval_count = 0
    if scan_row:
        latest_upload = conn.execute(
            "SELECT upload_id FROM discovery_uploads WHERE system_id = ? ORDER BY uploaded_at DESC LIMIT 1",
            (system_id,),
        ).fetchone()
        if latest_upload:
            reapproval_row = conn.execute(
                "SELECT COUNT(*) FROM capabilities WHERE upload_id = ? AND system_id = ? AND review_status = 'needs_reapproval'",
                (latest_upload["upload_id"], system_id),
            ).fetchone()
            reapproval_count = reapproval_row[0] if reapproval_row else 0

    # Determine status
    if not latest_scan_at:
        status = "discovery_missing"
        next_action = "Run agent-governance scan . and upload governance-discovery.json."
    elif not acap_version_id:
        if reapproval_count > 0:
            status = "needs_reapproval"
            next_action = f"Re-approve {reapproval_count} changed capability(ies), then generate ACAP."
        else:
            status = "acap_missing"
            next_action = "Review capabilities and generate ACAP version."
    elif reapproval_count > 0:
        status = "needs_reapproval"
        next_action = f"Re-approve {reapproval_count} changed capability(ies) and regenerate ACAP."
    elif latest_scan_at and acap_generated_at and latest_scan_at > acap_generated_at:
        status = "scan_changed_since_acap"
        next_action = "Codebase changed since ACAP. Review new candidates and regenerate."
    elif not latest_runtime_at:
        status = "runtime_missing"
        next_action = "Add SDK bootstrap snippet, run your app, then events appear here."
    elif latest_runtime_at and latest_assessment_at and latest_runtime_at > latest_assessment_at:
        status = "runtime_changed_since_assessment"
        next_action = "Runtime evidence changed since assessment. Run ACAP rules and assessment."
    else:
        status = "up_to_date"
        next_action = "Audit is up to date."

    return {
        "system_id": system_id,
        "latest_scan_at": latest_scan_at,
        "active_acap_version": acap_version_id,
        "acap_generated_at": acap_generated_at,
        "latest_runtime_event_at": latest_runtime_at,
        "latest_assessment_at": latest_assessment_at,
        "needs_reapproval_count": reapproval_count,
        "status": status,
        "next_action": next_action,
    }



# ---------------------------------------------------------------------------
# Governed actions, decisions, records and kill switches
# ---------------------------------------------------------------------------


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _bool_or_none(value: Any) -> int | None:
    return None if value is None else int(bool(value))


def insert_governed_action(
    conn: sqlite3.Connection, request: dict[str, Any], *, replace: bool = True
) -> None:
    """Store a governed action.

    ``replace=False`` keeps an already-evaluated request intact, so reporting
    an outcome can never rewrite what was actually authorized.
    """
    verb = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"
    conn.execute(
        f"""
        {verb} INTO governed_actions (
            action_id, system_id, deployment_id, environment, agent_id,
            capability_id, capability_name, module_path, action_type,
            enforcement_mode, requested_enforcement_mode, session_id,
            trace_id, parent_span_id,
            arguments_hash, external_side_effect, approval_required,
            request_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request["action_id"],
            request["system_id"],
            request.get("deployment_id"),
            request.get("environment"),
            request.get("agent_id"),
            request.get("capability_id"),
            request.get("capability_name"),
            request.get("module_path"),
            request.get("action_type"),
            request.get("enforcement_mode", "observe"),
            request.get("requested_enforcement_mode"),
            request.get("session_id"),
            request.get("trace_id"),
            request.get("parent_span_id"),
            request.get("arguments_hash"),
            _bool_or_none(request.get("external_side_effect")),
            _bool_or_none(request.get("approval_required")),
            _json(request),
            request.get("created_at") or datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def insert_action_decision(
    conn: sqlite3.Connection, decision: dict[str, Any], *, system_id: str
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO action_decisions (
            decision_id, action_id, system_id, verdict, reason, reason_code,
            decided_by, matched_capability_id, kill_switch_id, matched_pattern_id,
            acap_version_id, acap_version_number, approval_required,
            payload_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision["decision_id"],
            decision["action_id"],
            system_id,
            decision["verdict"],
            decision.get("reason"),
            decision.get("reason_code"),
            decision.get("decided_by", "backend"),
            decision.get("matched_capability_id"),
            decision.get("kill_switch_id"),
            decision.get("matched_pattern_id"),
            decision.get("acap_version_id"),
            decision.get("acap_version_number"),
            _bool_or_none(decision.get("approval_required")),
            _json(decision),
            decision.get("created_at") or datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def upsert_action_record(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    """Store the execution outcome for an action, replacing any prior row."""
    request = record.get("request") or {}
    system_id = record.get("system_id") or request.get("system_id")
    conn.execute("DELETE FROM action_records WHERE action_id = ?", (record["action_id"],))
    conn.execute(
        """
        INSERT INTO action_records (
            record_id, action_id, decision_id, system_id, executed, execution_status,
            would_have_blocked, duration_ms, error_type, event_ids_json,
            evidence_hash, payload_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["record_id"],
            record["action_id"],
            record.get("decision_id"),
            system_id,
            int(bool(record.get("executed"))),
            record.get("execution_status", "unknown"),
            _bool_or_none(record.get("would_have_blocked")),
            record.get("duration_ms"),
            record.get("error_type"),
            _json(record.get("event_ids") or []),
            record.get("evidence_hash"),
            _json(record),
            record.get("created_at") or datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def list_governed_actions(
    conn: sqlite3.Connection, system_id: str, *, limit: int = 200, offset: int = 0
) -> list[dict[str, Any]]:
    """Return governed actions newest first, joined with decision and outcome."""
    rows = conn.execute(
        """
        SELECT a.action_id, a.system_id, a.capability_id, a.capability_name,
               a.module_path, a.action_type, a.enforcement_mode, a.session_id,
               a.trace_id, a.arguments_hash, a.external_side_effect, a.created_at,
               d.decision_id, d.verdict, d.reason, d.reason_code, d.decided_by,
               d.kill_switch_id, d.matched_pattern_id,
               r.executed, r.execution_status, r.would_have_blocked,
               r.duration_ms, r.error_type, r.evidence_hash
        FROM governed_actions AS a
        LEFT JOIN action_records AS r ON r.action_id = a.action_id
        LEFT JOIN action_decisions AS d ON d.decision_id = COALESCE(
            r.decision_id,
            (SELECT decision_id FROM action_decisions
             WHERE action_id = a.action_id ORDER BY created_at DESC, rowid DESC LIMIT 1)
        )
        WHERE a.system_id = ?
        ORDER BY a.created_at DESC, a.action_id DESC
        LIMIT ? OFFSET ?
        """,
        (system_id, limit, offset),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["executed"] = None if item["executed"] is None else bool(item["executed"])
        item["would_have_blocked"] = (
            None if item["would_have_blocked"] is None else bool(item["would_have_blocked"])
        )
        item["external_side_effect"] = (
            None if item["external_side_effect"] is None else bool(item["external_side_effect"])
        )
        out.append(item)
    return out


def get_governed_action(
    conn: sqlite3.Connection, system_id: str, action_id: str
) -> dict[str, Any] | None:
    action = conn.execute(
        "SELECT request_json FROM governed_actions WHERE system_id = ? AND action_id = ?",
        (system_id, action_id),
    ).fetchone()
    if action is None:
        return None
    decision = conn.execute(
        "SELECT payload_json FROM action_decisions WHERE action_id = ?", (action_id,)
    ).fetchone()
    record = conn.execute(
        "SELECT payload_json FROM action_records WHERE action_id = ?", (action_id,)
    ).fetchone()
    return {
        "action_id": action_id,
        "system_id": system_id,
        "request": json.loads(action["request_json"]),
        "decision": json.loads(decision["payload_json"]) if decision else None,
        "record": json.loads(record["payload_json"]) if record else None,
    }


def action_summary_counts(conn: sqlite3.Connection, system_id: str) -> dict[str, int]:
    """Headline counts for the Governed Actions dashboard tab."""
    total = int(
        conn.execute(
            "SELECT COUNT(*) FROM governed_actions WHERE system_id = ?", (system_id,)
        ).fetchone()[0]
    )
    verdicts = conn.execute(
        """
        SELECT d.verdict, COUNT(*)
        FROM governed_actions AS a
        LEFT JOIN action_records AS r ON r.action_id = a.action_id
        LEFT JOIN action_decisions AS d ON d.decision_id = COALESCE(
            r.decision_id,
            (SELECT decision_id FROM action_decisions
             WHERE action_id = a.action_id ORDER BY created_at DESC, rowid DESC LIMIT 1)
        )
        WHERE a.system_id = ?
        GROUP BY d.verdict
        """,
        (system_id,),
    ).fetchall()
    by_verdict = {str(row[0]): int(row[1]) for row in verdicts}
    statuses = conn.execute(
        """
        SELECT execution_status, COUNT(*) FROM action_records
        WHERE system_id = ? GROUP BY execution_status
        """,
        (system_id,),
    ).fetchall()
    by_status = {str(row[0]): int(row[1]) for row in statuses}
    would_block = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM action_records
            WHERE system_id = ? AND would_have_blocked = 1 AND execution_status = 'shadow_allowed'
            """,
            (system_id,),
        ).fetchone()[0]
    )
    return {
        "total": total,
        "allowed": by_verdict.get("ALLOW", 0),
        "denied": by_verdict.get("DENY", 0),
        "approval_required": by_verdict.get("REQUIRE_APPROVAL", 0),
        "blocked": by_status.get("denied_blocked", 0)
        + by_status.get("approval_required_blocked", 0),
        "executed": by_status.get("allowed_executed", 0),
        "shadow_would_block": would_block,
        "observe_only": by_status.get("observe_only", 0),
    }


def insert_kill_switch(conn: sqlite3.Connection, switch: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR REPLACE INTO kill_switches (
            kill_switch_id, system_id, enabled, target_capabilities_json,
            verdict, reason, created_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            switch["kill_switch_id"],
            switch["system_id"],
            int(bool(switch.get("enabled", True))),
            _json(switch.get("target_capabilities") or []),
            str(switch.get("verdict") or "DENY").upper(),
            switch.get("reason"),
            switch.get("created_by", "local_user"),
            now,
            now,
        ),
    )
    conn.commit()
    return get_kill_switch(conn, switch["system_id"], switch["kill_switch_id"]) or {}


def _kill_switch_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "kill_switch_id": row["kill_switch_id"],
        "system_id": row["system_id"],
        "enabled": bool(row["enabled"]),
        "target_capabilities": json.loads(row["target_capabilities_json"] or "[]"),
        "verdict": row["verdict"],
        "reason": row["reason"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_kill_switches(conn: sqlite3.Connection, system_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM kill_switches WHERE system_id = ? ORDER BY kill_switch_id",
        (system_id,),
    ).fetchall()
    return [_kill_switch_from_row(row) for row in rows]


def get_kill_switch(
    conn: sqlite3.Connection, system_id: str, kill_switch_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM kill_switches WHERE system_id = ? AND kill_switch_id = ?",
        (system_id, kill_switch_id),
    ).fetchone()
    return _kill_switch_from_row(row) if row else None


def update_kill_switch(
    conn: sqlite3.Connection,
    system_id: str,
    kill_switch_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    current = get_kill_switch(conn, system_id, kill_switch_id)
    if current is None:
        return None
    enabled = updates.get("enabled", current["enabled"])
    targets = updates.get("target_capabilities", current["target_capabilities"])
    verdict = str(updates.get("verdict", current["verdict"]) or "DENY").upper()
    reason = updates.get("reason", current["reason"])
    conn.execute(
        """
        UPDATE kill_switches
        SET enabled = ?, target_capabilities_json = ?, verdict = ?, reason = ?, updated_at = ?
        WHERE system_id = ? AND kill_switch_id = ?
        """,
        (
            int(bool(enabled)),
            _json(targets),
            verdict,
            reason,
            datetime.now(timezone.utc).isoformat(),
            system_id,
            kill_switch_id,
        ),
    )
    conn.commit()
    return get_kill_switch(conn, system_id, kill_switch_id)


def active_kill_switches(conn: sqlite3.Connection, system_id: str) -> list[dict[str, Any]]:
    return [switch for switch in list_kill_switches(conn, system_id) if switch["enabled"]]


# ----------------------------------------------------------------------
# Per-system enforcement-mode override
#
# The mode the SDK sends is the system's own configuration. A row here is the
# dashboard's override of it, so an operator can change a running system's
# enforcement posture without editing its governance.yaml or restarting it.
# ----------------------------------------------------------------------


def _enforcement_mode_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "system_id": row["system_id"],
        "mode": row["mode"],
        "updated_by": row["updated_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_enforcement_mode_override(
    conn: sqlite3.Connection, system_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM system_enforcement_modes WHERE system_id = ?",
        (system_id,),
    ).fetchone()
    return _enforcement_mode_from_row(row) if row else None


def set_enforcement_mode_override(
    conn: sqlite3.Connection,
    system_id: str,
    mode: str,
    updated_by: str = "local_user",
) -> dict[str, Any]:
    """Create or replace the override, preserving created_at across a re-set."""
    now = datetime.now(timezone.utc).isoformat()
    current = get_enforcement_mode_override(conn, system_id)
    created_at = current["created_at"] if current else now
    conn.execute(
        """
        INSERT OR REPLACE INTO system_enforcement_modes (
            system_id, mode, updated_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (system_id, mode, updated_by, created_at, now),
    )
    conn.commit()
    return get_enforcement_mode_override(conn, system_id) or {}


def clear_enforcement_mode_override(conn: sqlite3.Connection, system_id: str) -> bool:
    """Remove the override so the mode the SDK sends applies again."""
    cursor = conn.execute(
        "DELETE FROM system_enforcement_modes WHERE system_id = ?",
        (system_id,),
    )
    conn.commit()
    return cursor.rowcount > 0


def latest_action_enforcement_mode(
    conn: sqlite3.Connection, system_id: str
) -> str | None:
    """The mode most recently seen from the SDK, for display before any override."""
    row = conn.execute(
        """
        SELECT requested_enforcement_mode, enforcement_mode FROM governed_actions
        WHERE system_id = ?
        ORDER BY created_at DESC LIMIT 1
        """,
        (system_id,),
    ).fetchone()
    if row is None:
        return None
    # Rows written before the column existed only recorded the enforced mode.
    return row["requested_enforcement_mode"] or row["enforcement_mode"]


# ----------------------------------------------------------------------
# Per-system assessment inputs
#
# Human-declared context the scanner cannot infer -- jurisdiction, use case,
# high-risk classification, data sensitivity. These supplement discovered facts
# and a reviewed ACAP; they never override a reviewed ACAP.
# ----------------------------------------------------------------------


def _assessment_inputs_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "system_id": row["system_id"],
        "jurisdiction": row["jurisdiction"],
        "use_case": row["use_case"],
        "high_risk_category": bool(row["high_risk_category"]),
        "data_sensitivity": row["data_sensitivity"],
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"],
    }


def get_assessment_inputs(
    conn: sqlite3.Connection, system_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM system_assessment_inputs WHERE system_id = ?",
        (system_id,),
    ).fetchone()
    return _assessment_inputs_from_row(row) if row else None


def set_assessment_inputs(
    conn: sqlite3.Connection,
    system_id: str,
    inputs: dict[str, Any],
    updated_by: str = "local_user",
) -> dict[str, Any]:
    """Create or replace the declared inputs for a system."""
    conn.execute(
        """
        INSERT OR REPLACE INTO system_assessment_inputs (
            system_id, jurisdiction, use_case, high_risk_category,
            data_sensitivity, updated_by, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            system_id,
            inputs.get("jurisdiction") or None,
            inputs.get("use_case") or None,
            int(bool(inputs.get("high_risk_category"))),
            inputs.get("data_sensitivity") or None,
            updated_by,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return get_assessment_inputs(conn, system_id) or {}


def clear_assessment_inputs(conn: sqlite3.Connection, system_id: str) -> bool:
    cursor = conn.execute(
        "DELETE FROM system_assessment_inputs WHERE system_id = ?",
        (system_id,),
    )
    conn.commit()
    return cursor.rowcount > 0
