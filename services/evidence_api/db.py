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
        """
    )
    conn.commit()
    _migrate_add_columns(conn)


def _migrate_add_columns(conn: sqlite3.Connection) -> None:
    """Add columns to tables created before they existed."""
    migrations = [
        ("events", "system_id"),
        ("findings", "system_id"),
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
    for table in ("discovery_uploads", "events", "acap_versions", "findings"):
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

