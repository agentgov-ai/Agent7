from __future__ import annotations

from datetime import datetime
from fastapi import FastAPI

app = FastAPI()


# Fake external HTTP client so this demo runs without installing requests.
class requests:
    @staticmethod
    def post(url: str, json: dict):
        return {"status_code": 200, "url": url, "sent": True}


# Fake OpenAI surface so scanner can detect model usage pattern.
class openai:
    class chat:
        class completions:
            @staticmethod
            def create(model: str, messages: list[dict]):
                return {"model": model, "message": "demo airspace summary"}


# Fake database session.
class FakeSession:
    def add(self, obj):
        pass

    def delete(self, obj):
        pass

    def commit(self):
        pass

    def query(self, name):
        return self

    def filter_by(self, **kwargs):
        return self

    def first(self):
        return {"id": "airspace-object"}


session = FakeSession()


# Capability 1: creates/updates restricted airspace data.
def create_airspace_restriction(area_id: str, altitude_floor: int, altitude_ceiling: int):
    restriction = {
        "area_id": area_id,
        "altitude_floor": altitude_floor,
        "altitude_ceiling": altitude_ceiling,
        "status": "restricted",
    }

    session.add(restriction)
    session.commit()

    with open("airspace_changes.log", "a") as f:
        f.write(f"restriction_created:{area_id}\n")

    return {"status": "restriction_created"}


# Capability 2: sends external NOTAM-style airspace alert.
def publish_notam_alert(zone_id: str, message: str):
    requests.post(
        "https://notam.example.local/alerts",
        json={
            "zone_id": zone_id,
            "message": message,
        },
    )
    return {"status": "notam_published"}


# Capability 3: deletes/revokes drone flight clearance.
def revoke_drone_clearance(clearance_id: str):
    clearance = session.query("Clearance").filter_by(id=clearance_id).first()

    if clearance:
        session.delete(clearance)
        session.commit()

    return {"status": "clearance_revoked"}


# Capability 4: exports flight corridor data.
def export_flight_corridor_data(corridor_id: str):
    with open("flight_corridor_export.json", "w") as f:
        f.write(f'{{"corridor_id": "{corridor_id}"}}')

    return {"status": "corridor_exported"}


# Model usage surface, not business capability.
def generate_airspace_summary(prompt: str):
    return openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
    )


# Pure helper. Scanner should ignore this.
def format_altitude(altitude: int):
    return f"{altitude} ft"


@app.post("/airspace/restriction")
def create_restriction_route():
    return create_airspace_restriction(
        area_id="AREA-DELHI-01",
        altitude_floor=1000,
        altitude_ceiling=5000,
    )


@app.post("/airspace/notam")
def notam_route():
    return publish_notam_alert(
        zone_id="ZONE-01",
        message="Temporary restriction active",
    )


@app.delete("/airspace/clearance/{clearance_id}")
def revoke_clearance_route(clearance_id: str):
    return revoke_drone_clearance(clearance_id)


@app.post("/airspace/export")
def export_corridor_route():
    return export_flight_corridor_data("CORRIDOR-77")