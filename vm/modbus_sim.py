"""Run on Linux VM: Modbus TCP 5020 plus separate recovery HTTP 8081."""
import argparse
import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext, ModbusDeviceContext
from pymodbus.server import StartTcpServer
from shared.model import Measurement, utcnow
from shared.simulator import Belt
from vm.journal import Journal
from vm.modbus_codec import encode


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="data/modbus.db")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--recovery-port", type=int, default=8081)
    p.add_argument("--recovery-key", default=os.getenv("RECOVERY_KEY"))
    args = p.parse_args()
    if not args.recovery_key:
        p.error("RECOVERY_KEY is required")
    journal = Journal(args.db)
    belt = Belt(state=1)
    device = ModbusDeviceContext(ir=ModbusSequentialDataBlock(0, [0]*32), hr=ModbusSequentialDataBlock(0, [0]*8))
    context = ModbusServerContext(devices={1: device}, single=False)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            from urllib.parse import urlsplit, parse_qs
            u = urlsplit(self.path)
            if self.headers.get("X-Recovery-Key") != args.recovery_key:
                self.send_error(401); return
            if u.path != "/recovery":
                self.send_error(404); return
            cursor = int(parse_qs(u.query).get("cursor", [0])[0])
            records = journal.after(cursor)
            payload = json.dumps({"records": records, "next_cursor": records[-1]["sequence"] if records else cursor}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)

        def do_POST(self):
            if self.headers.get("X-Recovery-Key") != args.recovery_key:
                self.send_error(401); return
            if self.path == "/recovery/ack":
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                journal.acknowledge_through(int(data["cursor"]))
                self.send_response(204); self.end_headers(); return
            if self.path != "/state":
                self.send_error(404); return
            n = int(self.rfile.read(int(self.headers["Content-Length"])).decode())
            if n not in (0, 1, 2):
                self.send_error(400); return
            belt.state = n
            self.send_response(204); self.end_headers()

        def log_message(self, *_): pass

    threading.Thread(target=lambda: ThreadingHTTPServer((args.host, args.recovery_port), Handler).serve_forever(), daemon=True).start()

    def tick():
        while True:
            previous = None
            try:
                if not journal.has_capacity():
                    raise RuntimeError("journal full: generation paused")
                previous = replace(belt)
                belt.step()
                seq = journal.next_sequence()
                item = Measurement("belt-1", str(uuid.uuid4()), seq, utcnow(), belt.produced,
                                   belt.temperature_c, belt.current_a, belt.state, belt.rejected)
                journal.append(item)
                ir, hr = encode(belt)
                device.setValues(4, 0, ir)
                device.setValues(3, 0, hr)
            except (RuntimeError, OSError, sqlite3.Error) as exc:
                if previous is not None:
                    belt.__dict__.update(previous.__dict__)
                print(exc, flush=True)
            time.sleep(1)
    threading.Thread(target=tick, daemon=True).start()
    StartTcpServer(context=context, address=(args.host, 5020))


if __name__ == "__main__":
    main()
