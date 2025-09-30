from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.status import HTTP_401_UNAUTHORIZED
from pathlib import Path
from datetime import datetime
import json, csv

from .models import Verdict, Action, Status
from .services import alert_service, triage_service
from worker import celery_app
from app.services.ai_tasks import ai_suggest_task

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
security = HTTPBasic()

def require_basic(creds: HTTPBasicCredentials = Depends(security)):
    if creds.username != "analyst" or creds.password != "changeme":
        raise JSONResponse({"error":"Unauthorized"}, status_code=HTTP_401_UNAUTHORIZED)
    return creds.username

@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    alerts = alert_service.load_alerts()
    return templates.TemplateResponse("dashboard.html", {"request": request, "alerts": alerts})

@router.get("/alerts/{alert_id}", response_class=HTMLResponse)
def alert_detail(request: Request, alert_id: str):
    alert = alert_service.get_alert(alert_id)
    if not alert:
        return HTMLResponse("Alert not found", status_code=404)
    artifacts = {k: alert_service.load_artifact_text(p) for k,p in alert.get("artifacts", {}).items()}
    return templates.TemplateResponse("alert_detail.html", {"request": request, "alert": alert, "artifacts": artifacts})

@router.post("/alerts/{alert_id}/assist")
def request_ai_suggestion(alert_id: str, _user=Depends(require_basic)):
    alert = alert_service.get_alert(alert_id)
    if not alert:
        return JSONResponse({"error": "Alert not found"}, status_code=404)
    artifacts = {k: alert_service.load_artifact_text(p) for k,p in alert.get("artifacts", {}).items()}
    task = ai_suggest_task.delay(alert, artifacts)
    return {"task_id": task.id, "status": "queued"}

@router.get("/assist/{task_id}")
def get_ai_result(task_id: str):
    task = celery_app.AsyncResult(task_id)
    if not task or not task.status:
        return {"task_id": task_id, "status": "unknown"}
    if not task.ready():
        return {"task_id": task_id, "status": task.status}
    result = task.result or {}
    for noisy in ("artifacts", "raw"):
        result.pop(noisy, None)
    return {"task_id": task_id, "status": "done", "result": result}

@router.post("/alerts/{alert_id}/triage")
def triage_alert(
    alert_id: str,
    analyst: str = Form(...),
    verdict: Verdict = Form(...),
    action: Action = Form(...),
    notes: str = Form(""),
    ai_verdict: str = Form(None),
    ai_action: str = Form(None),
    ai_confidence: float = Form(None),
    ai_rationale: str = Form(None),
    ai_task_id: str = Form(None),
    ai_accepted: str = Form(None),
    _user=Depends(require_basic)
):
    ai_suggestion = None
    if ai_verdict and ai_action:
        ai_suggestion = {
            "verdict": ai_verdict,
            "action": ai_action,
            "confidence": ai_confidence,
            "rationale": ai_rationale,
            "task_id": ai_task_id,
            "provided_at": datetime.utcnow().isoformat() + "Z"
        }
    report = triage_service.build_report(
        alert_id=alert_id,
        analyst=analyst[:64],
        verdict=verdict,
        action=action,
        notes=notes[:10000],
        ai_suggestion=ai_suggestion,
        ai_accepted=bool(ai_accepted)
    )
    triage_service.save_report(report)
    alert_service.update_alert_status(alert_id, "triaged", changed_by=analyst[:64])
    return RedirectResponse(url=f"/alerts/{alert_id}", status_code=303)

@router.post("/alerts/{alert_id}/status")
def change_status(alert_id: str, new_status: Status = Form(...), analyst: str = Form("unknown"), _user=Depends(require_basic)):
    ok = alert_service.update_alert_status(alert_id, new_status, changed_by=analyst[:64])
    if not ok:
        return JSONResponse({"error": "Alert not found"}, status_code=404)
    return RedirectResponse(url=f"/alerts/{alert_id}", status_code=303)

# -------- Audit & Metrics --------

@router.get("/audit", response_class=HTMLResponse)
def audit_log(request: Request):
    reports = []
    for f in DATA_DIR.glob("*_report.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                reports.append(json.load(fh))
        except Exception:
            continue
    reports.sort(key=lambda r: r.get("timestamp", ""), reverse=True)

    # metrics
    total = len(reports)
    with_ai = [r for r in reports if r.get("ai_suggestion")]
    accepted = [r for r in reports if r.get("ai_accepted")]
    agreement = [r for r in with_ai if r.get("verdict")==r["ai_suggestion"].get("verdict") and r.get("action")==r["ai_suggestion"].get("action")]
    metrics = {
        "total_reports": total,
        "ai_suggestions": len(with_ai),
        "ai_accepted": len(accepted),
        "agreement": len(agreement),
        "agreement_rate": (len(agreement)/len(with_ai)*100) if with_ai else 0,
        "acceptance_rate": (len(accepted)/len(with_ai)*100) if with_ai else 0,
        "lifecycle_avg_minutes": lifecycle_averages()
    }
    return templates.TemplateResponse("audit.html", {"request": request, "reports": reports, "metrics": metrics})

def _parse_time(ts: str):
    from datetime import datetime
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None

def lifecycle_averages():
    durations = {s: [] for s in ["new","in_progress","triaged","escalated","closed"]}
    try:
        alerts = json.load(open(DATA_DIR / "alerts.json", "r", encoding="utf-8"))
    except Exception:
        alerts = []
    for a in alerts:
        hist = a.get("status_history", [])
        for i in range(len(hist)-1):
            start = _parse_time(hist[i].get("timestamp",""))
            end   = _parse_time(hist[i+1].get("timestamp",""))
            if start and end:
                state = hist[i].get("status","new")
                delta = (end - start).total_seconds()/60.0
                durations.setdefault(state, []).append(delta)
    avg = {}
    for state, vals in durations.items():
        avg[state] = round(sum(vals)/len(vals), 2) if vals else 0
    return avg

@router.get("/audit/metrics.json")
def export_metrics_json():
    # reuse logic from audit route
    reports = []
    for f in DATA_DIR.glob("*_report.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                reports.append(json.load(fh))
        except Exception:
            continue

    total = len(reports)
    with_ai = [r for r in reports if r.get("ai_suggestion")]
    accepted = [r for r in reports if r.get("ai_accepted")]
    agreement = [r for r in with_ai if r.get("verdict")==r["ai_suggestion"].get("verdict") and r.get("action")==r["ai_suggestion"].get("action")]
    global_metrics = {
        "total_reports": total,
        "ai_suggestions": len(with_ai),
        "ai_accepted": len(accepted),
        "agreement": len(agreement),
        "agreement_rate": (len(agreement)/len(with_ai)*100) if with_ai else 0,
        "acceptance_rate": (len(accepted)/len(with_ai)*100) if with_ai else 0,
        "lifecycle_avg_minutes": lifecycle_averages()
    }

    per_analyst = {}
    for r in reports:
        analyst = r.get("analyst","unknown")
        stats = per_analyst.setdefault(analyst, {"total_reports":0,"ai_suggestions":0,"ai_accepted":0,"agreement":0})
        stats["total_reports"] += 1
        if r.get("ai_suggestion"):
            stats["ai_suggestions"] += 1
            if r.get("ai_accepted"): stats["ai_accepted"] += 1
            if r.get("verdict")==r["ai_suggestion"].get("verdict") and r.get("action")==r["ai_suggestion"].get("action"):
                stats["agreement"] += 1
    for a, s in per_analyst.items():
        if s["ai_suggestions"]>0:
            s["agreement_rate"] = round(s["agreement"]/s["ai_suggestions"]*100,1)
            s["acceptance_rate"] = round(s["ai_accepted"]/s["ai_suggestions"]*100,1)
        else:
            s["agreement_rate"] = 0
            s["acceptance_rate"] = 0

    return {"global": global_metrics, "per_analyst": per_analyst}

@router.get("/audit/export.csv")
def export_reports_csv():
    reports = []
    for f in DATA_DIR.glob("*_report.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                reports.append(json.load(fh))
        except Exception:
            continue

    def generate():
        fieldnames = ["alert_id","analyst","verdict","action","notes","ai_verdict","ai_action","ai_confidence","ai_rationale","ai_accepted","timestamp"]
        yield ",".join(fieldnames) + "\n"
        for r in reports:
            row = {
                "alert_id": r.get("alert_id",""),
                "analyst": r.get("analyst",""),
                "verdict": r.get("verdict",""),
                "action": r.get("action",""),
                "notes": (r.get("notes") or "").replace("\n"," "),
                "ai_verdict": r.get("ai_suggestion",{}).get("verdict",""),
                "ai_action": r.get("ai_suggestion",{}).get("action",""),
                "ai_confidence": r.get("ai_suggestion",{}).get("confidence",""),
                "ai_rationale": (r.get("ai_suggestion",{}).get("rationale","") or "").replace("\n"," "),
                "ai_accepted": r.get("ai_accepted",""),
                "timestamp": r.get("timestamp","")
            }
            values = [str(row[k]) if row[k] is not None else "" for k in fieldnames]
            # naive CSV quoting
            yield ",".join(['"'+v.replace('"','""')+'"' if ("," in v or " " in v) else v for v in values]) + "\n"

    return StreamingResponse(generate(), media_type="text/csv")
