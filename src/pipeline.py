"""Pipeline orchestrator.

Wires the mock providers together through the reliability primitives across
seven stages. Every paid stage is gated on credits first, retries transient
failures, and dead-letters (rather than drops) anything that errors out.

Run it via ``main.py`` — this module exposes ``run_pipeline`` returning a
report dict.
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from typing import Dict, List

from .models import Lead, Stage, Status
from .providers import EnrichmentProvider, OutreachProvider, VerificationProvider
from .reliability import (
    DeadLetterQueue,
    DedupRegistry,
    PermanentError,
    QuotaGate,
    RateLimiter,
    TransientError,
    with_retry,
)

# Title scoring — a strong signal wins. Mirrors a real lead-qualification rule.
_SCORE_KEYWORDS = {
    3: ("influencer",),
    2: ("partnership", "creator", "social", "content", "community", "collaboration"),
    1: ("marketing", "brand", "pr", "communications", "growth"),
}


def score_title(title: str) -> int:
    low = title.lower()
    for score in (3, 2, 1):
        if any(word in low for word in _SCORE_KEYWORDS[score]):
            return score
    return 0


def _valid_domain(domain: str) -> bool:
    return bool(domain) and "." in domain and " " not in domain.strip()


def ingest(input_path: str, dlq: DeadLetterQueue) -> List[Lead]:
    leads: List[Lead] = []
    with open(input_path, newline="", encoding="utf-8") as fh:
        for i, row in enumerate(csv.DictReader(fh), start=1):
            lead_id = (row.get("lead_id") or f"row{i}").strip()
            company = (row.get("company") or "").strip()
            domain = (row.get("domain") or "").strip().lower()
            if not company or not _valid_domain(domain):
                dlq.add(lead_id, "ingest", "invalid_input",
                        f"company={company!r} domain={domain!r}")
                continue
            leads.append(Lead(lead_id=lead_id, company=company, domain=domain))
    return leads


def run_pipeline(config: dict, input_path: str, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    pcfg = config["providers"]
    rcfg = config["retry"]
    rules = config["rules"]

    dlq = DeadLetterQueue()
    dedup = DedupRegistry()

    gates: Dict[str, QuotaGate] = {
        "enrichment": QuotaGate("enrichment", **_gate_kwargs(pcfg["enrichment"])),
        "verification": QuotaGate("verification", **_gate_kwargs(pcfg["verification"])),
        "outreach": QuotaGate("outreach", **_gate_kwargs(pcfg["outreach"])),
    }
    enricher = EnrichmentProvider(pcfg["enrichment"]["transient_fail_rate"],
                                  pcfg["enrichment"]["no_data_rate"])
    verifier = VerificationProvider(pcfg["verification"]["transient_fail_rate"],
                                    pcfg["verification"]["invalid_rate"])
    outreach = OutreachProvider()
    limiter = RateLimiter(rules["daily_outreach_cap"])

    retry_kwargs = dict(attempts=rcfg["attempts"],
                        base_delay=rcfg["base_delay_seconds"],
                        factor=rcfg["backoff_factor"])

    funnel: Counter = Counter()
    total_retries = 0

    leads = ingest(input_path, dlq)
    ingested = list(leads)
    funnel["ingested"] = len(ingested)

    # ---- Stage: dedupe --------------------------------------------------
    survivors: List[Lead] = []
    for lead in ingested:
        key = getattr(lead, rules["dedup_key"])
        if dedup.is_duplicate(key):
            lead.status = Status.DUPLICATE.value
            lead.reason = f"duplicate_{rules['dedup_key']}"
            continue
        dedup.add(key)
        lead.stage = Stage.DEDUPED.value
        survivors.append(lead)
    funnel["deduped"] = len(survivors)

    # ---- Stage: enrich (paid) ------------------------------------------
    enriched: List[Lead] = []
    for lead in survivors:
        if not gates["enrichment"].can_afford():
            lead.status = Status.PAUSED_QUOTA.value
            lead.reason = "enrichment_credits_exhausted"
            dlq.add(lead.lead_id, "enrich", "quota_exhausted")
            continue
        gates["enrichment"].charge()
        try:
            result = with_retry(
                lambda a: enricher.enrich(lead, a),
                retry_on=(TransientError,),
                on_retry=lambda *_: _bump(lead),
                **retry_kwargs,
            )
        except PermanentError as exc:
            lead.status = Status.DEAD_LETTERED.value
            lead.reason = str(exc)
            dlq.add(lead.lead_id, "enrich", "no_data", str(exc))
            total_retries += lead.retries
            continue
        except TransientError as exc:
            lead.status = Status.DEAD_LETTERED.value
            lead.reason = "enrichment_failed_after_retries"
            dlq.add(lead.lead_id, "enrich", "transient_exhausted", str(exc))
            total_retries += lead.retries
            continue
        lead.contact_name = result["contact_name"]
        lead.title = result["title"]
        lead.email = result["email"]
        lead.stage = Stage.ENRICHED.value
        total_retries += lead.retries
        enriched.append(lead)
    funnel["enriched"] = len(enriched)

    # ---- Stage: verify email (paid) ------------------------------------
    verified: List[Lead] = []
    for lead in enriched:
        if not gates["verification"].can_afford():
            lead.status = Status.PAUSED_QUOTA.value
            lead.reason = "verification_credits_exhausted"
            dlq.add(lead.lead_id, "verify", "quota_exhausted")
            continue
        gates["verification"].charge()
        try:
            ok = with_retry(
                lambda a: verifier.verify(lead, a),
                retry_on=(TransientError,),
                on_retry=lambda *_: _bump(lead),
                **retry_kwargs,
            )
        except TransientError as exc:
            lead.status = Status.DEAD_LETTERED.value
            lead.reason = "verification_failed_after_retries"
            dlq.add(lead.lead_id, "verify", "transient_exhausted", str(exc))
            continue
        lead.email_valid = ok
        if not ok:
            lead.status = Status.SKIPPED.value
            lead.reason = "unverifiable_email"
            continue
        lead.stage = Stage.VERIFIED.value
        verified.append(lead)
    funnel["verified"] = len(verified)

    # ---- Stage: score & qualify ----------------------------------------
    scored: List[Lead] = []
    for lead in verified:
        lead.score = score_title(lead.title)
        if lead.score < rules["min_title_score"]:
            lead.status = Status.SKIPPED.value
            lead.reason = f"title_score_{lead.score}_below_min"
            continue
        lead.stage = Stage.SCORED.value
        scored.append(lead)
    funnel["scored"] = len(scored)

    # ---- Stage: queue (per-company cap, best scores first) -------------
    scored.sort(key=lambda l: l.score, reverse=True)
    per_company: Counter = Counter()
    queued: List[Lead] = []
    for lead in scored:
        if per_company[lead.domain] >= rules["max_contacts_per_company"]:
            lead.status = Status.SKIPPED.value
            lead.reason = "over_contact_cap"
            continue
        per_company[lead.domain] += 1
        lead.stage = Stage.QUEUED.value
        queued.append(lead)
    funnel["queued"] = len(queued)

    # ---- Stage: outreach (rate-limited, paid) --------------------------
    contacted = 0
    for lead in queued:
        if not limiter.allow():
            lead.status = Status.QUEUED.value
            lead.reason = "deferred_daily_cap"
            continue
        if not gates["outreach"].can_afford():
            lead.status = Status.PAUSED_QUOTA.value
            lead.reason = "outreach_credits_exhausted"
            dlq.add(lead.lead_id, "outreach", "quota_exhausted")
            continue
        gates["outreach"].charge()
        outreach.send(lead, 1)
        lead.stage = Stage.CONTACTED.value
        lead.status = Status.CONTACTED.value
        contacted += 1
    funnel["contacted"] = contacted

    all_leads = ingested  # every lead carries its final status
    report = _build_report(all_leads, ingested_count=len(ingested), funnel=funnel,
                           gates=gates, dlq=dlq, limiter=limiter,
                           total_retries=total_retries)

    _write_outputs(output_dir, all_leads, dlq, report)
    return report


def _gate_kwargs(cfg: dict) -> dict:
    return {"remaining": cfg["credits"],
            "cost_per_call": cfg.get("cost_per_call", 1),
            "unit_cost_usd": cfg.get("unit_cost_usd", 0.0)}


def _bump(lead: Lead) -> None:
    lead.retries += 1


def _build_report(all_leads, ingested_count, funnel, gates, dlq, limiter,
                  total_retries) -> dict:
    by_status: Counter = Counter(l.status for l in all_leads)
    contacted = funnel["contacted"]
    conversion = round(100 * contacted / ingested_count, 1) if ingested_count else 0.0
    total_spend = round(sum(g.spend_usd for g in gates.values()), 4)
    return {
        "summary": {
            "input_records": ingested_count + len(
                [e for e in dlq.entries if e.stage == "ingest"]),
            "valid_ingested": ingested_count,
            "contacted": contacted,
            "ingest_to_contact_rate_pct": conversion,
            "dead_lettered": len(dlq),
            "total_retries": total_retries,
            "simulated_spend_usd": total_spend,
        },
        "funnel": dict(funnel),
        "final_status_breakdown": dict(by_status),
        "providers": {
            name: {"calls": g.charged_calls,
                   "credits_remaining": g.remaining,
                   "spend_usd": g.spend_usd}
            for name, g in gates.items()
        },
        "outreach_capacity_remaining": limiter.remaining,
    }


def _write_outputs(output_dir, all_leads, dlq, report) -> None:
    leads_path = os.path.join(output_dir, "processed_leads.csv")
    with open(leads_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=Lead.fieldnames())
        writer.writeheader()
        for lead in all_leads:
            writer.writerow(lead.to_row())

    dlq.write_jsonl(os.path.join(output_dir, "dead_letter.jsonl"))

    with open(os.path.join(output_dir, "run_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
