#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VM_HOME="${FACTOREDGE_VM_HOME:-$HOME/forgepulse}"
cd "$PROJECT_ROOT"
if [ -z "${RECOVERY_KEY:-}" ]; then
  SECRETS_FILE="${FACTOREDGE_SECRETS_FILE:-$PROJECT_ROOT/work/runtime-secrets.json}"
  export RECOVERY_KEY="$("$VM_HOME/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["recovery_key"])' "$SECRETS_FILE")"
fi
exec "$VM_HOME/.venv/bin/python" -m vm.modbus_sim --db "$VM_HOME/data/modbus.db" --host 127.0.0.1
