"""Entry point (composition root): run the pipeline and render the HTML dashboard.

    python build_site.py     ->  writes site/index.html

Orchestrates the layers: the controller (pipeline) produces a run, and the view
(views.site) renders it to a static page.
"""
from __future__ import annotations

import csv
import json
import os

from src.controllers.pipeline import run_pipeline
from src.views import site

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
SITE = os.path.join(HERE, "site")


def main():
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as fh:
        config = json.load(fh)
    report = run_pipeline(config, os.path.join(HERE, "data", "raw_leads.csv"), OUT)

    dls = []
    with open(os.path.join(OUT, "dead_letter.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                dls.append(json.loads(line))
    with open(os.path.join(OUT, "processed_leads.csv"), newline="", encoding="utf-8") as fh:
        leads = list(csv.DictReader(fh))

    page = site.render(report, dls, leads, config)
    os.makedirs(SITE, exist_ok=True)
    out_path = os.path.join(SITE, "index.html")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"Wrote {out_path} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
