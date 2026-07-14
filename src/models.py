"""Domain models for the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Optional


class Stage(str, Enum):
    """Furthest stage a lead successfully reached."""
    INGESTED = "ingested"
    DEDUPED = "deduped"
    ENRICHED = "enriched"
    VERIFIED = "verified"
    SCORED = "scored"
    QUEUED = "queued_for_outreach"
    CONTACTED = "contacted"


class Status(str, Enum):
    """Terminal disposition of a lead after a run."""
    NEW = "new"
    CONTACTED = "contacted"
    QUEUED = "queued"                 # eligible, deferred to next run (rate cap hit)
    DUPLICATE = "duplicate"           # already seen — skipped intentionally
    SKIPPED = "skipped"               # valid outcome, not usable (low score / bad email)
    PAUSED_QUOTA = "paused_api_limit" # provider credits exhausted — safe to resume later
    DEAD_LETTERED = "dead_lettered"   # error path — needs investigation


@dataclass
class Lead:
    lead_id: str
    company: str
    domain: str
    contact_name: str = ""
    title: str = ""
    email: str = ""
    email_valid: Optional[bool] = None
    score: int = 0
    stage: str = Stage.INGESTED.value
    status: str = Status.NEW.value
    retries: int = 0
    reason: str = ""

    def to_row(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @staticmethod
    def fieldnames() -> list:
        return [f.name for f in fields(Lead)]
