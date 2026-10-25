"""Persistent outbox; MQTT PUBACK never removes a row. Platform DB ack does."""
import argparse
import json
import os
import sqlite3
import time
import threading
import urllib.request
import uuid
from dataclasses import replace
import paho.mqtt.client as mqtt
from shared.model import Measurement, utcnow
from shared.simulator import Belt
from vm.journal import Journal


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="data/mqtt.db")
    p.add_argument("--broker", required=True)
    p.add_argument("--platform", required=True)
    p.add_argument("--key", default=os.getenv("INGEST_KEY"))
    p.add_argument("--topic", default="factory/belt-2/measurements")
    args = p.parse_args()
    if not args.key:
        p.error("INGEST_KEY is required")
    journal = Journal(args.db)
    belt = Belt(state=1)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    def produce():
        while True:
            previous = None
            try:
                if not journal.has_capacity():
                    raise RuntimeError("journal full: generation paused")
                previous = replace(belt)
                belt.step()
                seq = journal.next_sequence()
                journal.append(Measurement("belt-2", str(uuid.uuid4()), seq, utcnow(), belt.produced,
                                           belt.temperature_c, belt.current_a, belt.state, belt.rejected))
            except (RuntimeError, sqlite3.Error) as exc:
                if previous is not None:
                    belt.__dict__.update(previous.__dict__)
                print(exc, flush=True)
            time.sleep(1)
    threading.Thread(target=produce, daemon=True).start()
    last_error_log = 0.0
    while True:
        try:
            client.connect(args.broker, 1883, 10)
            client.loop_start()
            for record in journal.pending():
                info = client.publish(args.topic, json.dumps(record), qos=1)
                info.wait_for_publish(timeout=3)
                if not info.is_published(): break
                req = urllib.request.Request(f"{args.platform.rstrip('/')}/api/ack/{record['event_id']}", headers={"X-Ingest-Key": args.key})
                with urllib.request.urlopen(req, timeout=3) as response:
                    ack = json.load(response)
                if ack.get("committed") and ack.get("sequence") == record["sequence"]:
                    journal.acknowledge(record["sequence"], record["event_id"])
            client.loop_stop()
            client.disconnect()
        except Exception as exc:
            if time.monotonic() - last_error_log >= 5:
                print(f"MQTT replay retry: {type(exc).__name__}: {exc}", flush=True)
                last_error_log = time.monotonic()
            try: client.loop_stop(); client.disconnect()
            except Exception: pass
        time.sleep(0.2)


if __name__ == "__main__":
    main()
