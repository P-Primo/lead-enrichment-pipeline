"""Entry point (composition root): run the pipeline and print a run summary.

Usage:
    python main.py
    python main.py --input data/raw_leads.csv --config config.json --output output
"""
from __future__ import annotations

import argparse
import json
import os

from src.controllers.pipeline import run_pipeline
from src.views import console

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=os.path.join(HERE, "data", "raw_leads.csv"))
    parser.add_argument("--config", default=os.path.join(HERE, "config.json"))
    parser.add_argument("--output", default=os.path.join(HERE, "output"))
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as fh:
        config = json.load(fh)

    report = run_pipeline(config, args.input, args.output)
    console.render(report)
    print(f"Artifacts written to: {args.output}/")
    print("  - processed_leads.csv   (every lead + final status)")
    print("  - dead_letter.jsonl     (failed records + reason)")
    print("  - run_report.json       (machine-readable metrics)")


if __name__ == "__main__":
    main()
