# 0Incidents — SOC Triage (Production-Ready Starter)

A realistic SOC triage platform: FastAPI backend, Jinja UI, Celery/Redis async AI assistance, lifecycle states, audit log with exportable metrics.

## Features
- Alert dashboard and detail views with artifacts
- Lifecycle states (New → In Progress → Triaged → Escalated → Closed) with status history (who/when)
- Triage submissions with AI suggestion capture and acceptance flag
- Async AI suggestions (heuristic baseline; optional OpenAI via `OPENAI_API_KEY`)
- Audit dashboard + metrics (agreement rate, acceptance rate, lifecycle averages)
- Export endpoints: `metrics.json` and `export.csv`
- Security hardening: escaping, path safety, atomic writes, basic auth (demo)

## Quick Start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Run Redis (dev)
redis-server
# Start Celery worker
celery -A worker.celery_app worker --loglevel=info
# Start API
python run.py
```

Open: http://127.0.0.1:8000/

> Demo Basic Auth for AI endpoints: `analyst` / `changeme`

## Optional: Enable OpenAI
```bash
pip install openai
export OPENAI_API_KEY="sk-..."
# optionally: export OPENAI_MODEL="gpt-4o-mini"
```
The system will try LLM first, then fallback to heuristics if unavailable.

## Hardening Notes
- Change Basic Auth to real auth (JWT/SSO).
- Bind Redis to localhost and set a password (configure `REDIS_URL`), e.g. `redis://:password@127.0.0.1:6379/0`
- Put FastAPI behind TLS (nginx, Caddy) and set proper CORS if exposing APIs.
- Consider migrating alerts/reports to a DB (SQLite/Postgres) for concurrency and integrity.
- Never log raw artifacts or PII.

## Project Layout
```
0incidents_full/
├── app/
│   ├── main.py
│   ├── models.py
│   ├── routes.py
│   ├── services/
│   │   ├── alert_service.py
│   │   ├── ai_assist.py
│   │   ├── ai_tasks.py
│   │   └── triage_service.py
│   └── templates/
│       ├── base.html
│       ├── dashboard.html
│       ├── alert_detail.html
│       └── audit.html
├── data/
│   ├── alerts.json
│   └── artifacts/
│       ├── email1.txt
│       └── sysmon1.txt
├── run.py
├── worker.py
├── requirements.txt
└── README.md
```

## Test it
- Visit dashboard → open alert-001
- Click **Request suggestion** (uses Basic Auth demo creds)
- Accept AI suggestion or submit manual triage
- Check `data/alert-001_report.json`
- See **Audit Log** for metrics; download CSV/JSON

Enjoy building 0Incidents 🔧
