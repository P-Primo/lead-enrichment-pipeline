"""Webhook-driven CRM sync.

As a lead advances through the pipeline, an event is emitted to a CRM webhook so
the lead moves along a CRM funnel automatically — no manual data entry, and the
CRM always mirrors the live pipeline state. In the demo we build the payloads and
count them; a real deployment would POST them to the configured webhook URL.

Each pipeline stage maps to a coarser CRM funnel stage:
"""
from __future__ import annotations

# (pipeline stage shown to the user, CRM funnel stage, webhook event name)
CRM_FUNNEL = [
    ("Source from Instagram", "Sourced", "lead.created"),
    ("Ingest & validate", "New Lead", "lead.stage_changed"),
    ("Enrich", "Contact Found", "lead.stage_changed"),
    ("Score & qualify", "Qualified", "lead.qualified"),
    ("Queue", "Ready for Outreach", "lead.stage_changed"),
    ("Outreach", "Contacted", "lead.contacted"),
]

# Fixed timestamp so the generated page is reproducible (no live clock).
_DEMO_TS = "2026-07-14T09:00:00Z"


def build_event(lead_id, company, from_stage, to_stage, crm_stage, event, score=None):
    payload = {
        "event": event,
        "lead_id": lead_id,
        "company": company,
        "from_stage": from_stage,
        "to_stage": to_stage,
        "crm_funnel_stage": crm_stage,
        "received_at": _DEMO_TS,
    }
    if score is not None:
        payload["score"] = score
    return payload


def event_count(report) -> int:
    """One webhook fires per CRM-mapped stage a lead enters this run."""
    f = report["funnel"]
    s = report["summary"]
    return (s["input_records"]      # Sourced   (every discovered brand)
            + f["ingested"]         # New Lead
            + f["enriched"]         # Contact Found
            + f["scored"]           # Qualified
            + f["queued"]           # Ready for Outreach
            + f["contacted"])       # Contacted
