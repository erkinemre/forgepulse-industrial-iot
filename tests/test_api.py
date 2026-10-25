import os
import uuid
os.environ["FACTOREDGE_DB"] = "work/test-api-" + uuid.uuid4().hex + ".db"
os.environ["DISABLE_COLLECTORS"] = "1"
os.environ["INGEST_KEY"] = "test-ingest-key"
from fastapi.testclient import TestClient
from server.app import app, store, sessions
from server.auth import hash_password


def client_for(role):
    name = "test-" + role
    with store.connect() as db:
        db.execute("INSERT OR REPLACE INTO users(username,password_hash,role) VALUES(?,?,?)", (name,hash_password("long-test-password"),role))
    return TestClient(app), {"Authorization": "Bearer " + sessions.create(name)}


def test_role_matrix_and_event_safety():
    admin, ah = client_for("admin")
    engineer, eh = client_for("engineer")
    viewer, vh = client_for("viewer")
    body={"id":"test-device","protocol":"modbus","config":{"host":"127.0.0.1","port":5020,"unit_id":1}}
    assert viewer.post("/api/devices",json=body,headers=vh).status_code==403
    assert engineer.post("/api/devices",json=body,headers=eh).status_code==200
    assert engineer.put("/api/devices/test-device",json=body,headers=eh).status_code==200
    assert viewer.put("/api/devices/test-device",json=body,headers=vh).status_code==403
    assert engineer.delete("/api/devices/test-device",headers=eh).status_code==403
    assert engineer.get("/api/users",headers=eh).status_code==403
    user={"username":"test-other","password":"very-long-secret-password","role":"viewer"}
    assert engineer.post("/api/users",json=user,headers=eh).status_code==403
    assert admin.post("/api/users",json=user,headers=ah).status_code==200
    assert admin.delete("/api/devices/test-device",headers=ah).status_code==200
    assert admin.delete("/api/users/test-other",headers=ah).status_code==200
    events=admin.get("/api/events",headers=ah).json()
    assert any(e["type"]=="device_added" for e in events)
    assert "very-long-secret-password" not in str(events)
    assert viewer.get("/api/live",headers=vh).status_code==200


def test_ingest_ack_idempotence():
    from datetime import datetime, timezone
    c,h=client_for("admin")
    body={"source_id":"belt-2","event_id":"api-id-1","sequence":9001,"source_time":datetime.now(timezone.utc).isoformat(),"produced":100,"temperature_c":40,"current_a":5,"state":1,"rejected":2}
    k={"X-Ingest-Key":"test-ingest-key"}
    assert c.post("/api/ingest",json=body,headers=k).json()["inserted"] is True
    assert c.post("/api/ingest",json=body,headers=k).json()["inserted"] is False
    assert c.get("/api/ack/api-id-1",headers=k).json()["committed"] is True
    assert c.get("/api/ack/missing",headers=k).status_code==404


def test_camera_class_time_only_and_auth():
    from datetime import datetime, timezone, timedelta
    c, viewer = client_for("viewer")
    at = datetime.now(timezone.utc).isoformat()
    body = {"class": "tired", "at_utc": at}
    assert c.post("/api/camera", json=body).status_code == 401
    assert c.post("/api/camera", json={**body, "class": "raw-frame"},
                  headers={"X-Ingest-Key": "test-ingest-key"}).status_code == 400
    assert c.post("/api/camera", json=body,
                  headers={"X-Ingest-Key": "test-ingest-key"}).json() == {"committed": True}
    assert c.get("/api/camera", headers=viewer).json() == {**body, "connected": True}
    old = {"class": "absent", "at_utc": (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()}
    assert c.post("/api/camera", json=old,
                  headers={"X-Ingest-Key": "test-ingest-key"}).status_code == 200
    assert c.get("/api/camera", headers=viewer).json() == {**old, "connected": False}
