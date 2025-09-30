from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .routes import router

app = FastAPI(title="0Incidents SOC Triage")
app.include_router(router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
