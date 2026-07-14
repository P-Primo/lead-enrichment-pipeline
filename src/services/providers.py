"""Mock external providers.

In a real deployment each of these maps to a paid third-party API
(e.g. a data-enrichment vendor, an email-verification service, a
cold-outreach platform). Here they are fully simulated so the repo runs
with no credentials and no network.

Failures are DETERMINISTIC but pseudo-random per (lead, attempt), derived
from a hash. That gives realistic, reproducible behaviour: some leads fail
the first attempt and succeed on retry; some fail permanently; some return
no data at all. Same input -> same run, every time.
"""
from __future__ import annotations

import hashlib

from src.models.lead import Lead
from src.services.reliability import PermanentError, TransientError


def _unit(*parts: str) -> float:
    """Stable pseudo-random float in [0, 1) from the given key parts."""
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _pick(options, *parts: str):
    return options[int(_unit(*parts) * len(options)) % len(options)]


_FIRST = ["Alex", "Sam", "Jordan", "Taylor", "Morgan", "Casey", "Riley",
          "Jamie", "Cameron", "Devon", "Harper", "Quinn"]
_LAST = ["Reed", "Nguyen", "Silva", "Kowalski", "Okafor", "Bianchi",
         "Larsson", "Mendez", "Osei", "Petrov", "Yamamoto", "Dubois"]

# Titles span the full scoring range, including 0 (which gets filtered out).
_TITLES = [
    "Founder & CEO",
    "Chief Marketing Officer",
    "VP of Marketing",
    "Head of Growth",
    "Director of Marketing",
    "Marketing Manager",
    "Brand Manager",
    "Growth Team Lead",
    "Marketing Analyst",
    "Growth Coordinator",
    "Communications Specialist",
    "Marketing Intern",
    "Sales Assistant",
    "Support Agent",
    "Office Receptionist",
]


class EnrichmentProvider:
    """Finds a decision-maker contact for a company."""

    def __init__(self, transient_fail_rate: float, no_data_rate: float) -> None:
        self.transient_fail_rate = transient_fail_rate
        self.no_data_rate = no_data_rate

    def enrich(self, lead: Lead, attempt: int) -> dict:
        if _unit(lead.lead_id, "enrich-transient", str(attempt)) < self.transient_fail_rate:
            raise TransientError("enrichment provider timeout")
        if _unit(lead.lead_id, "enrich-nodata") < self.no_data_rate:
            raise PermanentError("no contact found for domain")

        first = _pick(_FIRST, lead.lead_id, "first")
        last = _pick(_LAST, lead.lead_id, "last")
        title = _pick(_TITLES, lead.lead_id, "title")
        email = f"{first}.{last}@{lead.domain}".lower()
        return {"contact_name": f"{first} {last}", "title": title, "email": email}


class VerificationProvider:
    """Confirms an email address is deliverable."""

    def __init__(self, transient_fail_rate: float, invalid_rate: float) -> None:
        self.transient_fail_rate = transient_fail_rate
        self.invalid_rate = invalid_rate

    def verify(self, lead: Lead, attempt: int) -> bool:
        if _unit(lead.lead_id, "verify-transient", str(attempt)) < self.transient_fail_rate:
            raise TransientError("verification provider 503")
        return _unit(lead.lead_id, "verify-invalid") >= self.invalid_rate


class OutreachProvider:
    """Sends a cold-outreach message and returns a message id."""

    def send(self, lead: Lead, attempt: int) -> str:
        digest = hashlib.sha256(f"send|{lead.lead_id}".encode()).hexdigest()[:12]
        return f"msg_{digest}"
