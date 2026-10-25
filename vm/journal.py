"""Durable bounded source journal shared by Modbus and MQTT simulators."""
import json
import sqlite3
import time
from pathlib import Path


class Journal:
    def __init__(self, path, max_rows=86400):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.max_rows = max_rows
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS records(seq INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value INTEGER NOT NULL)")
            db.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('last_sequence',COALESCE((SELECT MAX(seq) FROM records),0))")

    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        return db

    def append(self, item):
        with self.db() as db:
            db.execute("DELETE FROM records WHERE acknowledged=1 AND created_at<?", (time.time()-7*86400,))
            count = db.execute("SELECT COUNT(*) FROM records WHERE acknowledged=0").fetchone()[0]
            if count >= self.max_rows:
                raise RuntimeError("journal full: source must stop generating measurements")
            try:
                db.execute("INSERT INTO records(seq,event_id,payload,created_at) VALUES(?,?,?,?)", (item.sequence, item.event_id, json.dumps(item.json()), time.time()))
                db.execute("UPDATE meta SET value=? WHERE key='last_sequence'", (item.sequence,))
            except sqlite3.OperationalError as exc:
                raise RuntimeError("journal disk failure: source must stop generating measurements") from exc

    def has_capacity(self):
        with self.db() as db:
            return db.execute("SELECT COUNT(*) FROM records WHERE acknowledged=0").fetchone()[0] < self.max_rows

    def pending(self, limit=100):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM records WHERE acknowledged=0 ORDER BY seq LIMIT ?", (limit,))]

    def after(self, cursor=0, limit=500):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM records WHERE seq>? ORDER BY seq LIMIT ?", (cursor, limit))]

    def acknowledge(self, sequence, event_id):
        with self.db() as db:
            db.execute("UPDATE records SET acknowledged=1 WHERE seq=? AND event_id=?", (sequence, event_id))

    def acknowledge_through(self, sequence):
        with self.db() as db:
            db.execute("UPDATE records SET acknowledged=1 WHERE seq<=?", (sequence,))

    def next_sequence(self):
        with self.db() as db:
            return db.execute("SELECT value+1 FROM meta WHERE key='last_sequence'").fetchone()[0]
