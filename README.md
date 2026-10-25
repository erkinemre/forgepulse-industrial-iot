# ForgePulse — Industrial IoT Mini Factory

ForgePulse is a local smart-factory demonstration with two simulated production belts. A Modbus TCP source and an MQTT source feed a FastAPI + SQLite platform and a React dashboard. The project explores durable source journals, recovery after interruptions, duplicate detection, alarms with hysteresis, and role-based access. An optional camera classifier sends only a class and timestamp to the platform; it does not persist raw frames.

This is a **demonstration**, not production machinery control or a complete OEE system. It has no production TLS, broker authentication, central secret store, or multi-host database. The camera classification is not suitable for health or employment decisions.

## Components

| Path | Purpose |
| --- | --- |
| `vm/` | Modbus simulator, MQTT publisher, durable journals, optional camera classifier |
| `server/` | FastAPI API, collectors, auth, SQLite storage, alarm and efficiency logic |
| `shared/` | Measurement model and simulator |
| `web/` | React dashboard |
| `tests/` | Core, API, protocol and recovery tests |
| `host/` | Windows setup and launch scripts |

The Modbus and MQTT sources run in an Ubuntu WSL2 VM in the demonstrated setup; the API and dashboard run on Windows. One machine is enough for the demo. Other layouts require adapting the addresses and launch scripts.

## Quick start on Windows with Ubuntu WSL2

Requirements: Python 3.11+, Node 20+, Ubuntu WSL2, and Mosquitto in Ubuntu. Clone the repository into a local folder and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File host/setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File host/start.ps1
```

In another terminal, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File host/start-web.ps1
```

Open `http://127.0.0.1:5173`. The first username is `admin`; its generated password is in `work/runtime-secrets.json`. Keep that file private. On Ubuntu, install the VM requirements with `bash vm/setup-ubuntu.sh`, start Mosquitto, and run `bash vm/run_modbus.sh` and `bash vm/run_mqtt.sh` in separate terminals. See `docs/code-tour.md` for the code map.

The Windows launch scripts were developed for Ubuntu WSL2. Set `FORGEPULSE_WSL_DISTRO` and `FORGEPULSE_WSL_USER` if your distribution or Linux username differs from the defaults. Set `FACTOREDGE_VM_HOME` to a writable Linux directory for VM data and virtual environment. Network and firewall rules depend on the local WSL configuration. The optional camera requires a reachable MJPEG/RTSP feed and `opencv-python` in the VM; do not expose the feed publicly.

## Tests

```powershell
python -m pip install -e '.[test]'
python -m pytest -q
cd web
npm ci
npm run build
```

The automated tests cover storage, authorization, Modbus/MQTT transport, recovery and interruption cases. Manual camera and full-capacity scripts are available in `tests/`. The original live device demonstration was performed on a specific local setup; automated tests do not claim to reproduce that device setup.

## Data handling

Runtime credentials, logs, test databases, Python environments, Node modules, and generated web bundles stay out of Git through `.gitignore`. The project generates credentials locally on first setup. Rotate them if a local copy is ever exposed.
