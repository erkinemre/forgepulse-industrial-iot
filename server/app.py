import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from shared.model import Measurement
from server.db import Store
from server.auth import Sessions, hash_password, verify_password
from server.logic import period_metrics

DB_PATH = os.getenv("FACTOREDGE_DB", "work/factoredge.db")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
store = Store(DB_PATH)
sessions = Sessions()
app = FastAPI(title="ForgePulse Mini Akıllı Fabrika")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("WEB_ORIGIN", "http://localhost:5173").split(","),
                   allow_methods=["*"], allow_headers=["*"])


def bootstrap():
    admin_password = os.getenv("ADMIN_PASSWORD")
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            if not admin_password:
                raise RuntimeError("Set ADMIN_PASSWORD before first startup")
            db.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                       ("admin", hash_password(admin_password), "admin"))


@app.on_event("startup")
def startup():
    bootstrap()
    from server.collectors import start_collectors
    start_collectors(store)


def user(authorization: str = Header(default="")):
    name = sessions.get(authorization.removeprefix("Bearer "))
    if not name:
        raise HTTPException(401, "Login required")
    with store.connect() as db:
        row = db.execute("SELECT username,role FROM users WHERE username=?", (name,)).fetchone()
    if not row:
        raise HTTPException(401, "Session expired")
    return dict(row)


def allow(*roles):
    def check(actor=Depends(user)):
        if actor["role"] not in roles:
            raise HTTPException(403, "Forbidden")
        return actor
    return check


class Login(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: Login):
    with store.connect() as db:
        row = db.execute("SELECT * FROM users WHERE username=?", (body.username,)).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    return {"token": sessions.create(row["username"]), "role": row["role"]}


@app.get("/api/me")
def me(actor=Depends(user)):
    return actor


class Device(BaseModel):
    id: str
    protocol: str
    config: dict


def valid_device(d):
    if d.protocol == "modbus":
        from shared.register_map import REGISTER_MAP
        required = {"host", "port", "unit_id"}
        if not required <= d.config.keys() or d.config["unit_id"] != 1 or not 1 <= int(d.config["port"]) <= 65535:
            raise HTTPException(400, "Invalid Modbus config")
        if "register_map" in d.config and d.config["register_map"] != REGISTER_MAP:
            raise HTTPException(400, "Register map must match PDF contract")
        d.config["register_map"] = REGISTER_MAP
    elif d.protocol == "mqtt":
        if not {"host", "port", "topic"} <= d.config.keys():
            raise HTTPException(400, "Invalid MQTT config")
    else:
        raise HTTPException(400, "Unsupported protocol")


@app.get("/api/devices")
def devices(actor=Depends(user)):
    with store.connect() as db:
        return [{**dict(r), "config": json.loads(r["config"])} for r in db.execute("SELECT * FROM devices ORDER BY id")]


@app.post("/api/devices")
def add_device(d: Device, actor=Depends(allow("admin", "engineer"))):
    valid_device(d)
    with store.connect() as db:
        if db.execute("SELECT 1 FROM devices WHERE id=?", (d.id,)).fetchone():
            raise HTTPException(409, "Device exists")
        db.execute("INSERT INTO devices(id,protocol,config) VALUES(?,?,?)", (d.id, d.protocol, json.dumps(d.config)))
        store.event(db, actor["username"], d.id, "device_added")
    return {"ok": True}


@app.put("/api/devices/{device_id}")
def edit_device(device_id: str, d: Device, actor=Depends(allow("admin", "engineer"))):
    if d.id != device_id:
        raise HTTPException(400, "Device ID mismatch")
    valid_device(d)
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM devices WHERE id=?", (device_id,)).fetchone():
            raise HTTPException(404, "Missing device")
        db.execute("UPDATE devices SET protocol=?,config=?,connected=0 WHERE id=?", (d.protocol, json.dumps(d.config), device_id))
        store.event(db, actor["username"], device_id, "device_updated")
    return {"ok": True}


@app.delete("/api/devices/{device_id}")
def delete_device(device_id: str, actor=Depends(allow("admin"))):
    with store.connect() as db:
        db.execute("DELETE FROM devices WHERE id=?", (device_id,))
        store.event(db, actor["username"], device_id, "device_deleted")
    return {"ok": True}


class NewUser(BaseModel):
    username: str
    password: str
    role: str


@app.get("/api/users")
def users(actor=Depends(allow("admin"))):
    with store.connect() as db:
        return [dict(r) for r in db.execute("SELECT username,role FROM users ORDER BY username")]


@app.post("/api/users")
def add_user(body: NewUser, actor=Depends(allow("admin"))):
    if body.role not in ("admin", "engineer", "viewer") or len(body.password) < 12:
        raise HTTPException(400, "Invalid role or short password")
    with store.connect() as db:
        try:
            db.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                       (body.username, hash_password(body.password), body.role))
        except Exception:
            raise HTTPException(409, "User exists")
        store.event(db, actor["username"], body.username, "user_added", {"role": body.role})
    return {"ok": True}


@app.put("/api/users/{username}")
def edit_user(username: str, body: NewUser, actor=Depends(allow("admin"))):
    if body.username != username or body.role not in ("admin", "engineer", "viewer"):
        raise HTTPException(400, "Invalid user")
    if body.password and len(body.password) < 12:
        raise HTTPException(400, "Short password")
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise HTTPException(404, "Missing user")
        if body.password:
            db.execute("UPDATE users SET role=?,password_hash=? WHERE username=?", (body.role,hash_password(body.password),username))
        else:
            db.execute("UPDATE users SET role=? WHERE username=?", (body.role,username))
        store.event(db, actor["username"], username, "user_updated", {"role":body.role})
    return {"ok": True}


@app.delete("/api/users/{username}")
def delete_user(username: str, actor=Depends(allow("admin"))):
    if username == actor["username"]:
        raise HTTPException(400, "Cannot delete self")
    with store.connect() as db:
        db.execute("DELETE FROM users WHERE username=?", (username,))
        store.event(db, actor["username"], username, "user_deleted")
    return {"ok": True}


@app.get("/api/live")
def live(actor=Depends(user)):
    with store.connect() as db:
        return [dict(r) for r in db.execute("""SELECT d.id,d.protocol,d.connected,d.last_data,
        CASE WHEN d.protocol='modbus' AND d.connected=1 THEN s.produced ELSE m.produced END AS produced,
        CASE WHEN d.protocol='modbus' AND d.connected=1 THEN s.temperature_c ELSE m.temperature_c END AS temperature_c,
        CASE WHEN d.protocol='modbus' AND d.connected=1 THEN s.current_a ELSE m.current_a END AS current_a,
        CASE WHEN d.protocol='modbus' AND d.connected=1 THEN s.state ELSE m.state END AS state,
        CASE WHEN d.protocol='modbus' AND d.connected=1 THEN s.rejected ELSE m.rejected END AS rejected,
        CASE WHEN d.protocol='modbus' AND d.connected=1 THEN s.polled_at ELSE m.source_time END AS source_time
        FROM devices d LEFT JOIN live_snapshots s ON s.source_id=d.id
        LEFT JOIN measurements m ON m.event_id=(SELECT event_id FROM measurements WHERE source_id=d.id ORDER BY source_time DESC LIMIT 1) ORDER BY d.id""")]


@app.get("/api/history/{source_id}")
def history(source_id: str, signal: str = "temperature_c", actor=Depends(user)):
    if signal not in ("produced", "temperature_c", "current_a", "state", "rejected"):
        raise HTTPException(400, "Invalid signal")
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with store.connect() as db:
        return [dict(r) for r in db.execute(f"SELECT source_time,{signal} AS value FROM measurements WHERE source_id=? AND source_time>=? ORDER BY source_time", (source_id, cutoff))]


@app.get("/api/events")
def events(source: str = "", type: str = "", actor=Depends(user)):
    with store.connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM events WHERE (?='' OR source=?) AND (?='' OR type=?) ORDER BY id DESC LIMIT 500", (source, source, type, type))]


class AlarmConfig(BaseModel):
    threshold: float
    hysteresis: float


@app.put("/api/alarm-config/{source_id}")
def alarm_config(source_id: str, c: AlarmConfig, actor=Depends(allow("admin", "engineer"))):
    if c.hysteresis <= 0 or c.threshold <= c.hysteresis:
        raise HTTPException(400, "Invalid threshold")
    with store.connect() as db:
        db.execute("INSERT INTO alarm_config VALUES(?,?,?) ON CONFLICT(source_id) DO UPDATE SET threshold=excluded.threshold,hysteresis=excluded.hysteresis", (source_id, c.threshold, c.hysteresis))
        store.event(db, actor["username"], source_id, "alarm_config_updated")
    return {"ok": True}


@app.get("/api/alarms")
def alarms(actor=Depends(user)):
    with store.connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM alarms ORDER BY id DESC LIMIT 500")]


@app.get("/api/metrics/{source_id}")
def metrics(source_id: str, minutes: int = 60, actor=Depends(user)):
    minutes = min(max(minutes, 1), 1440)
    end = datetime.now(timezone.utc).timestamp()
    start = end - minutes * 60
    with store.connect() as db:
        data = [dict(r) for r in db.execute("SELECT source_time,produced,rejected,state FROM measurements WHERE source_id=? AND source_time>=? ORDER BY source_time", (source_id, datetime.fromtimestamp(start - 10, timezone.utc).isoformat()))]
    for r in data:
        r["epoch"] = datetime.fromisoformat(r["source_time"]).timestamp()
    return period_metrics(data, start, end)


@app.post("/api/ingest")
def ingest(body: dict, x_ingest_key: str = Header(default="")):
    if not os.getenv("INGEST_KEY") or x_ingest_key != os.getenv("INGEST_KEY"):
        raise HTTPException(401, "Invalid ingest key")
    try:
        item = Measurement(**body).validate()
        inserted = store.ingest(item)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    return {"event_id": item.event_id, "sequence": item.sequence, "committed": True, "inserted": inserted}


@app.get("/api/ack/{event_id}")
def ack(event_id: str, x_ingest_key: str = Header(default="")):
    if not os.getenv("INGEST_KEY") or x_ingest_key != os.getenv("INGEST_KEY"):
        raise HTTPException(401)
    with store.connect() as db:
        row = db.execute("SELECT source_id,sequence FROM measurements WHERE event_id=?", (event_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    return {"committed": True, "source_id": row["source_id"], "sequence": row["sequence"], "event_id": event_id}


@app.post("/api/camera")
def camera_result(body: dict, x_ingest_key: str = Header(default="")):
    if not os.getenv("INGEST_KEY") or x_ingest_key != os.getenv("INGEST_KEY"):
        raise HTTPException(401)
    if body.get("class") not in ("normal", "tired", "absent"):
        raise HTTPException(400)
    datetime.fromisoformat(body["at_utc"])
    with store.connect() as db:
        db.execute("INSERT INTO camera(class,at_utc) VALUES(?,?)", (body["class"], body["at_utc"]))
    return {"committed": True}


@app.get("/api/camera")
def camera_latest(actor=Depends(user)):
    with store.connect() as db:
        row = db.execute("SELECT class,at_utc FROM camera ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    latest = dict(row)
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(latest["at_utc"])).total_seconds()
        latest["connected"] = -2 <= age <= 12
    except ValueError:
        latest["connected"] = False
    return latest
