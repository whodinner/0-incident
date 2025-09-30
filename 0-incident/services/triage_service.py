from pathlib import Path
import json, os, tempfile
from datetime import datetime
from typing import Dict

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

def _atomic_write(path: Path, data: Dict):
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", text=True)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        try: os.remove(tmp_path)
        except FileNotFoundError: pass

def build_report(alert_id: str, analyst: str, verdict: str, action: str, notes: str, ai_suggestion=None, ai_accepted=False) -> Dict:
    return {
        "alert_id": alert_id,
        "analyst": analyst,
        "verdict": verdict,
        "action": action,
        "notes": notes,
        "ai_suggestion": ai_suggestion,
        "ai_accepted": ai_accepted,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

def save_report(report: Dict):
    out_file = DATA_DIR / f"{report['alert_id']}_report.json"
    _atomic_write(out_file, report)
    return out_file
