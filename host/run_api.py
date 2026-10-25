"""Start the Windows host platform using private generated credentials."""
import json
import os
from pathlib import Path
import uvicorn

root = Path(__file__).resolve().parent.parent
os.chdir(root)
values = json.loads((root / "work/runtime-secrets.json").read_text(encoding="utf-8"))
os.environ["ADMIN_PASSWORD"] = values["admin_password"]
os.environ["INGEST_KEY"] = values["ingest_key"]
os.environ["RECOVERY_KEY"] = values["recovery_key"]
os.environ["FACTOREDGE_DB"] = str(root / "work/live.db")
os.environ["WEB_ORIGIN"] = "http://localhost:5173,http://127.0.0.1:5173"
uvicorn.run("server.app:app", host="0.0.0.0", port=8000, log_level="info")
