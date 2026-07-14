"""Generate a synthetic raw-leads CSV for the demo.

Deterministic (no randomness) so the pipeline run — and the dashboard built
from it — is reproducible. Produces ~120 unique companies plus a handful of
duplicate and malformed rows so the dedupe and dead-letter stages have
something real to do.

    python scripts/generate_leads.py    ->  writes data/raw_leads.csv
"""
from __future__ import annotations

import csv
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "raw_leads.csv")

ADJ = ["North", "Blue", "Green", "Copper", "Iron", "Silver", "Golden", "Crimson",
       "Amber", "Cobalt", "Coral", "Ivory", "Jade", "Onyx", "Pearl", "Ruby",
       "Slate", "Teal", "Violet", "Willow", "Cedar", "Maple", "Pine", "Aspen",
       "Birch", "Summit", "Ridge", "Harbor", "Meadow", "River", "Bright", "Swift",
       "Bold", "Nova", "Orbit", "Lumen", "Vertex", "Apex", "Zenith", "Prime",
       "Vivid", "Halcyon", "Aurora", "Nimbus", "Kestrel"]

NOUN = ["Outdoors", "Robotics", "Skincare", "Apparel", "Analytics", "Foods",
        "Fitness", "Coffee", "Home", "Footwear", "Tools", "Beauty", "Furniture",
        "Travel", "Optics", "Toys", "Kitchenware", "Candles", "Botanicals",
        "Beverages", "Studios", "Labs", "Systems", "Goods", "Supply", "Collective",
        "Works", "Craft", "Trading", "Digital", "Bikes", "Wines", "Snacks",
        "Textiles", "Ceramics", "Gardens", "Wellness", "Media", "Cloud", "Ventures"]

TLDS = ["com", "io", "co", "studio", "shop", "design", "com.br"]

N_UNIQUE = 120


def build_rows():
    rows, seen, idx = [], set(), 0
    while len(rows) < N_UNIQUE:
        adj = ADJ[idx % len(ADJ)]
        noun = NOUN[(idx // len(ADJ)) % len(NOUN)]
        tld = TLDS[idx % len(TLDS)]
        idx += 1
        company = f"{adj} {noun}"
        domain = f"{(adj + noun).lower()}.{tld}"
        if domain in seen:
            continue
        seen.add(domain)
        rows.append([f"L{len(rows) + 1:03d}", company, domain])

    # A few genuine duplicates (same domain again) to exercise the dedupe stage.
    for src in (rows[3], rows[17], rows[41], rows[76], rows[103]):
        rows.append([f"L{len(rows) + 1:03d}", src[1], src[2]])

    # A few malformed rows to exercise ingest validation + dead-letter.
    malformed = [
        ["Broken Record Inc", "not a domain"],
        ["", "orphanrow.com"],
        ["No Domain Co", ""],
        ["Spaces Co", "bad domain .com"],
    ]
    for company, domain in malformed:
        rows.append([f"L{len(rows) + 1:03d}", company, domain])
    return rows


def main():
    rows = build_rows()
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["lead_id", "company", "domain"])
        writer.writerows(rows)
    print(f"Wrote {OUT} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
