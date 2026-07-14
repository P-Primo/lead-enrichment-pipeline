"""B2B lead enrichment & outreach pipeline — portfolio demo.

A self-contained, standard-library-only demonstration of a resilient
multi-stage data pipeline: ingest -> dedupe -> enrich -> verify -> score
-> queue -> outreach, with production-grade reliability primitives
(quota gating, retry with backoff, dead-letter queue, dedup registry,
rate limiting).

All external providers are mocked. No third-party services, credentials,
or real data are involved.
"""

__version__ = "1.0.0"
