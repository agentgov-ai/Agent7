"""A small airspace-style backend used to demonstrate Agent7 enforcement.

Nothing here touches a real service. Every function appends to SIDE_EFFECTS on
entry, so the demo can prove that a blocked action never ran its body rather
than merely inspecting what it returned.
"""
from __future__ import annotations

from typing import Any

# Every executed function body appends here. A blocked action must leave this
# list untouched -- that is the whole point of the demo.
SIDE_EFFECTS: list[str] = []

_FLIGHTS = [
    {"callsign": "ANA842", "altitude_ft": 34000, "lat": 35.62, "lon": 139.78},
    {"callsign": "JAL006", "altitude_ft": 31000, "lat": 35.55, "lon": 139.91},
    {"callsign": "UAL838", "altitude_ft": 37000, "lat": 35.71, "lon": 139.60},
]

_AIRSPACE_RECORDS = {
    "AREA-TOKYO-01": {"name": "Tokyo TMA", "ceiling_ft": 40000},
    "AREA-TOKYO-02": {"name": "Haneda Approach", "ceiling_ft": 12000},
}


def reset() -> None:
    """Clear recorded side effects between demo scenarios."""
    SIDE_EFFECTS.clear()


def fetch_live_flights(region: str = "tokyo") -> list[dict[str, Any]]:
    """Read live traffic. Allowed, unless the kill switch is on."""
    SIDE_EFFECTS.append("fetch_live_flights")
    return [dict(flight) for flight in _FLIGHTS]


def run_trino_query(sql: str) -> dict[str, Any]:
    """Execute analytics SQL. A destructive statement is denied by policy."""
    SIDE_EFFECTS.append("run_trino_query")
    return {"sql_accepted": True, "row_count": len(_FLIGHTS)}


def export_query_result(dataset: str, destination: str) -> dict[str, Any]:
    """Send data outside the system. Requires a verified approval."""
    SIDE_EFFECTS.append("export_query_result")
    return {"exported": True, "dataset": dataset, "destination": destination}


def delete_airspace_record(record_id: str) -> dict[str, Any]:
    """Destructive write. Denied outright in the governance manifest."""
    SIDE_EFFECTS.append("delete_airspace_record")
    _AIRSPACE_RECORDS.pop(record_id, None)
    return {"deleted": record_id}


def remaining_airspace_records() -> list[str]:
    """Inspection helper so the demo can show nothing was actually deleted."""
    return sorted(_AIRSPACE_RECORDS)
