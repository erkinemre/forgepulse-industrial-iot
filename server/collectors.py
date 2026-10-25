"""Transport adapters run independently and survive source outages."""
import json
import os
import threading
import time
from datetime import datetime, timezone
import urllib.request
from shared.model import Measurement, utcnow

_started = False


def start_collectors(store):
    global _started
    if _started or os.getenv("DISABLE_COLLECTORS") == "1":
        return
    _started = True
    threading.Thread(target=modbus_loop, args=(store,), daemon=True).start()
    threading.Thread(target=mqtt_loop, args=(store,), daemon=True).start()


def modbus_loop(store):
    from pymodbus.client import ModbusTcpClient
    from vm.modbus_codec import decode
    cursors = {}
    while True:
        with store.connect() as db:
            devices = [dict(r) for r in db.execute("SELECT * FROM devices WHERE protocol='modbus'")]
        for d in devices:
            c = json.loads(d["config"])
            client = ModbusTcpClient(c["host"], port=int(c["port"]), timeout=2)
            try:
                if not client.connect(): raise ConnectionError("Modbus unavailable")
                ir = client.read_input_registers(address=0, count=20, device_id=int(c["unit_id"]))
                hr = client.read_holding_registers(address=0, count=1, device_id=int(c["unit_id"]))
                if ir.isError() or hr.isError(): raise ConnectionError("Modbus exception")
                snapshot = decode(ir.registers, hr.registers)
                polled_at = utcnow()
                with store.connect() as db:
                    db.execute("INSERT INTO live_snapshots(source_id,polled_at,produced,temperature_c,current_a,state,rejected) VALUES(?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET polled_at=excluded.polled_at,produced=excluded.produced,temperature_c=excluded.temperature_c,current_a=excluded.current_a,state=excluded.state,rejected=excluded.rejected",
                               (d["id"], polled_at, snapshot["produced"], snapshot["temperature_c"], snapshot["current_a"], snapshot["state"], snapshot["rejected"]))
                    db.execute("UPDATE devices SET last_data=? WHERE id=?", (polled_at,d["id"]))
                store.connection(d["id"], True)
                recovery = c.get("recovery_url")
                if recovery:
                    try:
                        cursor = cursors.get(d["id"], 0)
                        req = urllib.request.Request(f"{recovery.rstrip('/')}/recovery?cursor={cursor}", headers={"X-Recovery-Key": os.environ.get("RECOVERY_KEY", "")})
                        with urllib.request.urlopen(req, timeout=3) as resp:
                            records = json.load(resp)["records"]
                        for payload in records:
                            store.ingest(Measurement(**payload))
                            cursors[d["id"]] = payload["sequence"]  # advance only after DB commit
                        if records:
                            ack = urllib.request.Request(f"{recovery.rstrip('/')}/recovery/ack",
                                data=json.dumps({"cursor":cursors[d["id"]]}).encode(), method="POST",
                                headers={"X-Recovery-Key":os.environ.get("RECOVERY_KEY", ""),"Content-Type":"application/json"})
                            with urllib.request.urlopen(ack, timeout=3): pass
                    except Exception as exc:
                        # Keep live Modbus health separate from history replay, but surface replay failures.
                        print(f"Modbus recovery retry for {d['id']}: {type(exc).__name__}: {exc}", flush=True)
            except Exception:
                store.connection(d["id"], False)
            finally:
                client.close()
        time.sleep(2)


def mqtt_loop(store):
    import paho.mqtt.client as mqtt
    clients = {}
    while True:
        with store.connect() as db:
            devices = [dict(r) for r in db.execute("SELECT * FROM devices WHERE protocol='mqtt'")]
        current = {d["id"]: d for d in devices}
        for device_id in list(clients):
            if device_id not in current or clients[device_id][0] != current[device_id]["config"]:
                clients[device_id][1].loop_stop()
                clients[device_id][1].disconnect()
                del clients[device_id]
        for d in devices:
            if d["id"] in clients:
                continue
            c = json.loads(d["config"])
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            def callbacks(source_id, topic):
                def on_connect(client, userdata, flags, reason_code, properties):
                    if reason_code == 0:
                        client.subscribe(topic, qos=1)
                def on_message(client, userdata, msg):
                    try:
                        item = Measurement(**json.loads(msg.payload)).validate()
                        if item.source_id == source_id:
                            store.ingest(item)
                    except (ValueError, TypeError, json.JSONDecodeError):
                        pass
                def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
                    store.connection(source_id, False)
                return on_connect, on_message, on_disconnect
            on_connect, on_message, on_disconnect = callbacks(d["id"], c["topic"])
            client.on_connect, client.on_message = on_connect, on_message
            client.on_disconnect = on_disconnect
            try:
                client.reconnect_delay_set(min_delay=1, max_delay=30)
                client.connect_async(c["host"], int(c["port"]), 10)
                client.loop_start()
                clients[d["id"]] = (d["config"], client)
            except Exception:
                store.connection(d["id"], False)
        with store.connect() as db:
            recent = [dict(r) for r in db.execute("""SELECT d.id,
                (SELECT MAX(m.ingested_at) FROM measurements m WHERE m.source_id=d.id) AS last_ingested
                FROM devices d WHERE d.protocol='mqtt' AND d.connected=1""")]
        for row in recent:
            try:
                age = (datetime.now(timezone.utc)-datetime.fromisoformat(row["last_ingested"])).total_seconds()
            except (TypeError, ValueError):
                age = 999
            if age > 10:
                store.connection(row["id"], False)
        time.sleep(2)
