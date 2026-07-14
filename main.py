"""Entry point: run the lead enrichment & outreach pipeline on a CSV of leads.

Usage:
    python main.py
    python main.py --input data/raw_leads.csv --config config.json --output output
"""
from __future__ import annotations

import argparse
import json
import os

from src.pipeline import run_pipeline

HERE = os.path.dirname(os.path.abspath(__file__))


def _print_summary(report: dict) -> None:
    s = report["summary"]
    print("\n" + "=" * 56)
    print("  RUN REPORT")
    print("=" * 56)
    print(f"  Input records            : {s['input_records']}")
    print(f"  Valid ingested           : {s['valid_ingested']}")
    print(f"  Contacted                : {s['contacted']}")
    print(f"  Ingest -> contact rate   : {s['ingest_to_contact_rate_pct']} %")
    print(f"  Dead-lettered            : {s['dead_lettered']}")
    print(f"  Retries performed        : {s['total_retries']}")
    print(f"  Simulated spend          : ${s['simulated_spend_usd']}")
    print("-" * 56)
    print("  Funnel:")
    for stage, n in report["funnel"].items():
        print(f"    {stage:<12} {n}")
    print("-" * 56)
    print("  Final status breakdown:")
    for status, n in sorted(report["final_status_breakdown"].items()):
        print(f"    {status:<20} {n}")
    print("-" * 56)
    print("  Providers:")
    for name, p in report["providers"].items():
        print(f"    {name:<13} calls={p['calls']:<3} "
              f"credits_left={p['credits_remaining']:<3} spend=${p['spend_usd']}")
    print("=" * 56 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=os.path.join(HERE, "data", "raw_leads.csv"))
    parser.add_argument("--config", default=os.path.join(HERE, "config.json"))
    parser.add_argument("--output", default=os.path.join(HERE, "output"))
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as fh:
        config = json.load(fh)

    report = run_pipeline(config, args.input, args.output)
    _print_summary(report)
    print(f"Artifacts written to: {args.output}/")
    print("  - processed_leads.csv   (every lead + final status)")
    print("  - dead_letter.jsonl     (failed records + reason)")
    print("  - run_report.json       (machine-readable metrics)")


if __name__ == "__main__":
    main()
