from worker import celery_app
from . import ai_assist

@celery_app.task(name="ai.suggest", soft_time_limit=20, time_limit=30, max_retries=2, acks_late=True)
def ai_suggest_task(alert: dict, artifacts: dict):
    try:
        out = ai_assist.suggest_decision(alert, artifacts)
        out.pop("raw", None)
        return out
    except Exception as e:
        return {"verdict":"uncertain","action":"monitor","confidence":0.0,"rationale":f"AI task failed: {e}"}
