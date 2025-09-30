from pathlib import Path
import json, os, tempfile, threading
from typing import List, Dict, Optional
from datetime import datetime

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
ALERTS_FILE = DATA_DIR / "alerts.json"
_WRITE_LOCK = threading.Lock()

def _atomic_write_json(path: Path, data):
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", text=True)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        try: os.remove(tmp_path)
        except FileNotFoundError: pass

def load_alerts() -> List[Dict]:
    with open(ALERTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def get_alert(alert_id: str) -> Optional[Dict]:
    for a in load_alerts():
        if a.get("id") == alert_id:
            return a
    return None

def _resolve_artifact(path_str: str) -> Optional[Path]:
    p = (DATA_DIR / path_str).resolve()
    if not str(p).startswith(str(DATA_DIR.resolve())):
        return None
    return p

def load_artifact_text(path: str) -> str:
    p = _resolve_artifact(path)
    if not p or not p.is_file():
        return "[missing artifact]"
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "[unreadable artifact]"

def update_alert_status(alert_id: str, new_status: str, changed_by: str = "unknown") -> bool:
    with _WRITE_LOCK:
        alerts = load_alerts()
        updated = False
        for a in alerts:
            if a["id"] == alert_id:
                a["status"] = new_status
                history = a.get("status_history", [])
                history.append({
                    "status": new_status,
                    "changed_by": changed_by,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
                a["status_history"] = history
                updated = True
                break
        if updated:
            _atomic_write_json(ALERTS_FILE, alerts)
        return updated
