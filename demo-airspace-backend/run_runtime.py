from ai_governance import GovernanceClient

gov = GovernanceClient.from_config(
    "governance.yaml",
    api_endpoint="http://127.0.0.1:8000/evidence/events",
    jsonl_path="airspace-runtime-events.jsonl",
)

results = gov.instrument_from_config()
print("Instrumentation:")
for item in results:
    print(item)

from app import create_airspace_restriction, publish_notam_alert, export_flight_corridor_data

with gov.trace(name="airspace_runtime_test", session_id="airspace-session-001"):
    create_airspace_restriction("AREA-DELHI-01", 1000, 5000)
    publish_notam_alert("ZONE-01", "Temporary restriction active")
    export_flight_corridor_data("CORRIDOR-77")

print("Runtime evidence emitted")