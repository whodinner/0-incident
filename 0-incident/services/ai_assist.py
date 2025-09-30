import os, re
from typing import Dict

USE_OPENAI = bool(os.environ.get("LLM_API"))
OPENAI_MODEL = os.environ.get("LLM_MODEL", "chooseyourAI")

def heuristic_suggest(alert: Dict, artifacts: Dict) -> Dict:
    text_blob = " ".join([artifacts.get(k, "") for k in artifacts.keys()]).lower()
    suggestion = {"verdict": "uncertain", "action": "monitor", "confidence": 0.40, "rationale": "Insufficient indicators. Monitor and enrich."}

    if "powershell" in text_blob or "iex (" in text_blob or "downloadstring" in text_blob:
        ip_match = re.search(r"(\d{1,3}\.){3}\d{1,3}", text_blob)
        if ip_match:
            return {"verdict":"tp","action":"isolate","confidence":0.93,"rationale":"PowerShell downloader + external IP observed — likely compromise."}
        return {"verdict":"tp","action":"isolate","confidence":0.80,"rationale":"PowerShell downloader observed; treat as likely compromise."}

    if any(k in text_blob for k in ["attachment","macro","urgent","reset_instructions"]):
        return {"verdict":"uncertain","action":"monitor","confidence":0.55,"rationale":"Phishing indicators present. Recommend enrichment and monitoring; isolate if endpoint confirms outbound connections."}

    return suggestion

def call_openai_suggestion(alert: Dict, artifacts: Dict) -> Dict:
    try:
        import openai
        openai.api_key = os.environ.get("LLM_API_KEY")
        prompt = [
            {"role":"system","content":"You are an expert SOC triage assistant. Provide a concise triage suggestion with verdict, action, rationale, confidence 0-1."},
            {"role":"user","content": f"Alert: {alert.get('summary')}\n\nArtifacts:\n" + "\n\n".join([f"{k}:\n{(v[:2000] + '...[truncated]' if len(v)>2000 else v)}" for k,v in artifacts.items()])}
        ]
        resp = openai.ChatCompletion.create(model=OPENAI_MODEL, messages=prompt, max_tokens=300, temperature=0.0)
        text = resp["choices"][0]["message"]["content"].strip()
        return {"verdict":"uncertain","action":"monitor","confidence":0.6,"rationale":text}
    except Exception as e:
        return {"verdict":"uncertain","action":"monitor","confidence":0.0,"rationale":f"openai failed: {e}. Fallback heuristic used."}

def suggest_decision(alert: Dict, artifacts: Dict) -> Dict:
    if USE_OPENAI:
        s = call_openai_suggestion(alert, artifacts)
        if not s or s.get("confidence", 0) < 0.01:
            s = heuristic_suggest(alert, artifacts)
        return s
    return heuristic_suggest(alert, artifacts)
