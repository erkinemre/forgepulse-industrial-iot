"""Generate private demo credentials once; never print or commit their values."""
import json
import secrets
from pathlib import Path

target = Path("work/runtime-secrets.json")
target.parent.mkdir(parents=True, exist_ok=True)
if not target.exists():
    values = {"admin_password": secrets.token_urlsafe(24),
              "ingest_key": secrets.token_urlsafe(32),
              "recovery_key": secrets.token_urlsafe(32)}
    with target.open("x", encoding="utf-8") as stream:
        json.dump(values, stream)
    print("Created private runtime credentials in work/runtime-secrets.json")
else:
    print("Existing private runtime credentials retained")
