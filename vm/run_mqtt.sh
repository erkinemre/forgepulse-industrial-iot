#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VM_HOME="${FACTOREDGE_VM_HOME:-$HOME/forgepulse}"
cd "$PROJECT_ROOT"
if [ -z "${INGEST_KEY:-}" ]; then
  SECRETS_FILE="${FACTOREDGE_SECRETS_FILE:-$PROJECT_ROOT/work/runtime-secrets.json}"
  export INGEST_KEY="$("$VM_HOME/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["ingest_key"])' "$SECRETS_FILE")"
fi
if [ -z "${PLATFORM_URL:-}" ]; then
  HOST_IP="$(ip route show default | awk '{print $3; exit}')"
  PLATFORM_URL="http://${HOST_IP}:8000"
fi
exec "$VM_HOME/.venv/bin/python" -m vm.mqtt_publisher --db "$VM_HOME/data/mqtt.db" --broker 127.0.0.1 --platform "$PLATFORM_URL"
