"""Brand sourcing stage — discover brands from Instagram paid-partnership signals.

This models the top of the funnel: creators disclose brand deals on Instagram in
several ways, and we scan those posts to surface the brands actively running
creator campaigns (the ones worth pitching). Deterministic and synthetic — for the
demo only; no real scraping happens.

The signal sources are the realistic ways a paid partnership shows up on IG:
  * the official "Paid partnership with …" label
  * disclosure hashtags (#ad, #publi, #sponsored)
  * brand accounts tagged in a sponsored post
  * story mentions and link stickers pointing at a brand
"""
from __future__ import annotations

# (label, share of detected signals). Shares sum to 1.0.
SIGNAL_SOURCES = [
    ("Paid-partnership label", 0.46),
    ("#ad / #publi / #sponsored", 0.27),
    ("Tagged brand accounts", 0.18),
    ("Story mentions & link stickers", 0.09),
]

# Roughly how many disclosed posts we see per unique brand, and the share of
# scanned posts that carry any partnership signal at all.
POSTS_PER_BRAND = 2.4
SIGNAL_HIT_RATE = 0.22


def discover(unique_brands: int) -> dict:
    """Return synthetic sourcing stats that resolve to ``unique_brands`` brands."""
    signals = round(unique_brands * POSTS_PER_BRAND)
    posts = round(signals / SIGNAL_HIT_RATE)

    breakdown, allocated = [], 0
    for i, (name, share) in enumerate(SIGNAL_SOURCES):
        n = signals - allocated if i == len(SIGNAL_SOURCES) - 1 else round(signals * share)
        allocated += n
        breakdown.append((name, n))

    return {
        "posts_scanned": posts,
        "partnership_signals": signals,
        "unique_brands": unique_brands,
        "breakdown": breakdown,
    }
