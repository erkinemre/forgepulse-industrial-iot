import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, protocol TEXT NOT NULL, config TEXT NOT NULL, connected INTEGER NOT NULL DEFAULT 0, last_data TEXT);
CREATE TABLE IF NOT EXISTS measurements(event_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, sequence INTEGER NOT NULL, source_time TEXT NOT NULL, ingested_at TEXT NOT NULL, produced INTEGER NOT NULL, temperature_c REAL NOT NULL, current_a REAL NOT NULL, state INTEGER NOT NULL, rejected INTEGER NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS ix_measure_seq ON measurements(source_id,sequence);
CREATE INDEX IF NOT EXISTS ix_measure_source_time ON measurements(source_id,source_time);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, actor TEXT NOT NULL, source TEXT NOT NULL, type TEXT NOT NULL, at_utc TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS alarms(id INTEGER PRIMARY KEY, source_id TEXT NOT NULL, active INTEGER NOT NULL, at_utc TEXT NOT NULL, temperature_c REAL NOT NULL);
CREATE TABLE IF NOT EXISTS alarm_config(source_id TEXT PRIMARY KEY, threshold REAL NOT NULL, hysteresis REAL NOT NULL);
CREATE TABLE IF NOT EXISTS camera(id INTEGER PRIMARY KEY, class TEXT NOT NULL, at_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS live_snapshots(source_id TEXT PRIMARY KEY, polled_at TEXT NOT NULL, produced INTEGER NOT NULL, temperature_c REAL NOT NULL, current_a REAL NOT NULL, state INTEGER NOT NULL, rejected INTEGER NOT NULL);
"""


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def event(self, db, actor, source, kind, detail=None):
        # Callers pass only explicit safe metadata, never credentials/configuration.
        db.execute("INSERT INTO events(actor,source,type,at_utc,detail) VALUES(?,?,?,?,?)",
                   (actor, source, kind, datetime.now(timezone.utc).isoformat(), json.dumps(detail or {})))

    def ingest(self, item):
        item.validate()
        with self.connect() as db:
            try:
                db.execute("INSERT INTO measurements VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (item.event_id, item.source_id, item.sequence, item.source_time,
                            datetime.now(timezone.utc).isoformat(), item.produced,
                            item.temperature_c, item.current_a, item.state, item.rejected))
            except sqlite3.IntegrityError:
                # A conflicting sequence must never silently acknowledge different data.
                existing = db.execute("SELECT * FROM measurements WHERE event_id=? OR (source_id=? AND sequence=?)",
                                      (item.event_id, item.source_id, item.sequence)).fetchone()
                if not existing or existing["event_id"] != item.event_id or any(existing[k] != getattr(item, k) for k in
                        ("source_id", "sequence", "source_time", "produced", "temperature_c", "current_a", "state", "rejected")):
                    raise ValueError("conflicting event identity")
                return False
            device = db.execute("SELECT connected FROM devices WHERE id=?", (item.source_id,)).fetchone()
            if device and not device["connected"]:
                self.event(db, "system", item.source_id, "source_recovered")
            db.execute("UPDATE devices SET connected=1,last_data=? WHERE id=?", (item.source_time, item.source_id))
            cfg = db.execute("SELECT threshold,hysteresis FROM alarm_config WHERE source_id=?", (item.source_id,)).fetchone()
            if cfg:
                from server.logic import alarm_transition
                prev = db.execute("SELECT active FROM alarms WHERE source_id=? ORDER BY id DESC LIMIT 1", (item.source_id,)).fetchone()
                was = bool(prev[0]) if prev else False
                now = datetime.now(timezone.utc).isoformat()
                active = alarm_transition(was, item.temperature_c, item.source_time, now, cfg["threshold"], cfg["hysteresis"])
                if active != was:
                    db.execute("INSERT INTO alarms(source_id,active,at_utc,temperature_c) VALUES(?,?,?,?)",
                               (item.source_id, int(active), now, item.temperature_c))
                    self.event(db, "system", item.source_id, "alarm_open" if active else "alarm_close")
            return True

    def connection(self, source_id, connected):
        with self.connect() as db:
            row = db.execute("SELECT connected FROM devices WHERE id=?", (source_id,)).fetchone()
            if row and bool(row[0]) != bool(connected):
                db.execute("UPDATE devices SET connected=? WHERE id=?", (int(connected), source_id))
                self.event(db, "system", source_id, "source_recovered" if connected else "source_lost")
