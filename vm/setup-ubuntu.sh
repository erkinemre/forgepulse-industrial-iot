#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VM_HOME="${FACTOREDGE_VM_HOME:-$HOME/forgepulse}"
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip mosquitto mosquitto-clients curl libsm6 libice6
mkdir -p "$VM_HOME/data"
python3 -m venv "$VM_HOME/.venv"
"$VM_HOME/.venv/bin/python" -m pip install --upgrade pip
"$VM_HOME/.venv/bin/python" -m pip install -e "$PROJECT_ROOT[camera,test]"
printf 'VM data: %s\n' "$VM_HOME/data"
printf 'VM IPv4 addresses: '; hostname -I
