"""View layer — renders a pipeline run summary to the console (CLI output)."""
from __future__ import annotations


def render(report):
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
    for name, pr in report["providers"].items():
        print(f"    {name:<13} calls={pr['calls']:<3} "
              f"credits_left={pr['credits_remaining']:<3} spend=${pr['spend_usd']}")
    print("=" * 56 + "\n")
