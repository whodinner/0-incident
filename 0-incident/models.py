from pydantic import BaseModel, Field
from typing import Literal

Verdict = Literal["tp", "fp", "uncertain"]
Action  = Literal["isolate", "blockip", "monitor", "resetpw"]
Status  = Literal["new", "in_progress", "triaged", "escalated", "closed"]

class TriageDecision(BaseModel):
    analyst: str = Field(min_length=1, max_length=64)
    verdict: Verdict
    action: Action
    notes: str = Field(default="", max_length=10000)
