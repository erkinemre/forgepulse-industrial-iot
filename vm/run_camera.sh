#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VM_HOME="${FACTOREDGE_VM_HOME:-$HOME/forgepulse}"
cd "$PROJECT_ROOT"
if [ "$#" -lt 1 ]; then
  echo "Usage: bash vm/run_camera.sh http://phone-ip:port/video [--preview]" >&2
  exit 2
fi
if [ -z "${INGEST_KEY:-}" ]; then
  SECRETS_FILE="${FACTOREDGE_SECRETS_FILE:-$PROJECT_ROOT/work/runtime-secrets.json}"
  export INGEST_KEY="$("$VM_HOME/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["ingest_key"])' "$SECRETS_FILE")"
fi
CAMERA_URL="$1"
shift
if [ -z "${PLATFORM_URL:-}" ]; then
  HOST_IP="$(ip route show default | awk '{print $3; exit}')"
  PLATFORM_URL="http://${HOST_IP}:8000"
fi
exec "$VM_HOME/.venv/bin/python" -m vm.camera --url "$CAMERA_URL" --platform "$PLATFORM_URL" "$@"
