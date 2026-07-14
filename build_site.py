"""Generate a self-contained static dashboard (site/index.html) from a live run.

Runs the pipeline, reads its real artifacts, and templates them into a single
dependency-free HTML file suitable for a static host (Render Static Site,
GitHub Pages, or just opening the file in a browser).

    python build_site.py     ->  writes site/index.html
"""
from __future__ import annotations

import csv
import html
import json
import os

from src.pipeline import run_pipeline


def esc(value) -> str:
    return html.escape(str(value))

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
SITE = os.path.join(HERE, "site")

# Repo link shown in the footer — edit after you create the GitHub repo.
REPO_URL = "https://github.com/your-username/lead-enrichment-pipeline"

STAGE_LABELS = {
    "ingested": "Ingested", "deduped": "Deduped", "enriched": "Enriched",
    "verified": "Verified", "scored": "Scored", "queued": "Queued",
    "contacted": "Contacted",
}
STATUS_LABELS = {
    "contacted": ("Contacted", "st-good"),
    "skipped": ("Skipped", "st-muted"),
    "duplicate": ("Duplicate", "st-warn"),
    "dead_lettered": ("Dead-lettered", "st-crit"),
    "paused_api_limit": ("Paused (API limit)", "st-serious"),
    "queued": ("Queued (deferred)", "st-muted"),
}

CSS = """
:root{
  --plane:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#898781; --grid:#e1e0d9; --line:#c3c2b7; --series1:#2a78d6;
  --border:rgba(11,11,11,0.10);
  --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --crit:#d03b3b;
}
@media (prefers-color-scheme:dark){
  :root{
    --plane:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7;
    --muted:#898781; --grid:#2c2c2a; --line:#383835; --series1:#3987e5;
    --border:rgba(255,255,255,0.10);
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.5}
.wrap{max-width:940px;margin:0 auto;padding:40px 20px 64px}
header{margin-bottom:28px}
h1{font-size:1.7rem;margin:0 0 6px;letter-spacing:-0.01em}
.sub{color:var(--ink2);margin:0;max-width:60ch}
.tag{display:inline-block;font-size:.72rem;font-weight:600;letter-spacing:.04em;
  text-transform:uppercase;color:var(--series1);border:1px solid var(--border);
  border-radius:999px;padding:3px 10px;margin-bottom:14px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:22px 24px;margin:16px 0}
.card h2{font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;
  color:var(--muted);margin:0 0 18px;font-weight:600}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:16px 0}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px 20px}
.tile .v{font-size:2rem;font-weight:650;letter-spacing:-0.02em}
.tile .l{color:var(--ink2);font-size:.86rem;margin-top:2px}
.tile .accent{height:3px;width:34px;border-radius:2px;background:var(--series1);margin-bottom:12px}
.bar-row{display:grid;grid-template-columns:120px 1fr 46px;align-items:center;gap:12px;margin:9px 0}
.bar-label{font-size:.9rem;color:var(--ink2)}
.bar-track{background:var(--grid);border-radius:5px;height:22px;overflow:hidden}
.bar-fill{height:100%;border-radius:5px;min-width:3px}
.bar-fill.funnel{background:var(--series1)}
.st-good{background:var(--good)} .st-warn{background:var(--warn)}
.st-crit{background:var(--crit)} .st-serious{background:var(--serious)}
.st-muted{background:var(--line)}
.bar-val{font-variant-numeric:tabular-nums;text-align:right;font-size:.9rem;color:var(--ink)}
table{width:100%;border-collapse:collapse;font-size:.88rem}
th{text-align:left;text-transform:uppercase;letter-spacing:.05em;font-size:.7rem;
  color:var(--muted);font-weight:600;padding:0 10px 8px;border-bottom:1px solid var(--line)}
td{padding:9px 10px;border-bottom:1px solid var(--grid);color:var(--ink2)}
td.n{font-variant-numeric:tabular-nums;text-align:right;color:var(--ink)}
td.strong{color:var(--ink)}
.scroll{overflow-x:auto}
code{background:var(--grid);padding:1px 5px;border-radius:4px;font-size:.85em}
footer{color:var(--muted);font-size:.82rem;margin-top:32px;text-align:center}
footer a{color:var(--series1);text-decoration:none}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:680px){.two{grid-template-columns:1fr}
  .bar-row{grid-template-columns:96px 1fr 40px}}
"""


def _tile(value, label):
    return (f'<div class="tile"><div class="accent"></div>'
            f'<div class="v">{value}</div><div class="l">{label}</div></div>')


def _funnel(funnel):
    maxv = max(funnel.values()) or 1
    rows = ""
    for key, count in funnel.items():
        pct = count / maxv * 100
        rows += (f'<div class="bar-row"><span class="bar-label">{STAGE_LABELS.get(key, key)}</span>'
                 f'<div class="bar-track"><div class="bar-fill funnel" style="width:{pct:.1f}%"></div></div>'
                 f'<span class="bar-val">{count}</span></div>')
    return rows


def _status(breakdown):
    total = sum(breakdown.values()) or 1
    rows = ""
    for key, count in sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True):
        label, cls = STATUS_LABELS.get(key, (key, "st-muted"))
        pct = count / total * 100
        rows += (f'<div class="bar-row"><span class="bar-label">{label}</span>'
                 f'<div class="bar-track"><div class="bar-fill {cls}" style="width:{pct:.1f}%"></div></div>'
                 f'<span class="bar-val">{count}</span></div>')
    return rows


def _providers(providers):
    rows = ""
    for name, p in providers.items():
        rows += (f'<tr><td class="strong">{esc(name)}</td>'
                 f'<td class="n">{p["calls"]}</td>'
                 f'<td class="n">{p["credits_remaining"]}</td>'
                 f'<td class="n">${p["spend_usd"]}</td></tr>')
    return rows


def _deadletters(dls):
    rows = ""
    for d in dls:
        rows += (f'<tr><td class="strong">{esc(d["lead_id"])}</td><td>{esc(d["stage"])}</td>'
                 f'<td>{esc(d["reason"])}</td><td>{esc(d.get("detail",""))}</td></tr>')
    return rows


def _sample_contacts(leads, limit=6):
    rows = ""
    picked = [l for l in leads if l.get("status") == "contacted"][:limit]
    for l in picked:
        rows += (f'<tr><td class="strong">{esc(l["company"])}</td><td>{esc(l["contact_name"])}</td>'
                 f'<td>{esc(l["title"])}</td><td class="n">{esc(l["score"])}</td></tr>')
    return rows


def build_html(report, dls, leads):
    s = report["summary"]
    tiles = "".join([
        _tile(s["contacted"], "Leads contacted"),
        _tile(f'{s["ingest_to_contact_rate_pct"]}%', "Ingest → contact rate"),
        _tile(s["total_retries"], "Transient failures retried"),
        _tile(s["dead_lettered"], "Dead-lettered (nothing lost)"),
        _tile(f'${s["simulated_spend_usd"]}', "Simulated API spend"),
    ])
    parts = []
    parts.append("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">")
    parts.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    parts.append("<title>Lead Enrichment & Outreach Pipeline — Run Report</title>")
    parts.append("<style>" + CSS + "</style></head><body><div class=\"wrap\">")
    parts.append('<header><div class="tag">Portfolio project · synthetic data</div>'
                 "<h1>Lead Enrichment &amp; Outreach Pipeline</h1>"
                 '<p class="sub">A resilient, config-driven pipeline that turns a raw company '
                 "list into verified, scored, contacted leads — with quota gating, retry-with-backoff, "
                 "and a dead-letter queue so no record is lost and no API budget is overspent. "
                 "Figures below are from a live, deterministic reference run.</p></header>")
    parts.append(f'<div class="tiles">{tiles}</div>')
    parts.append('<div class="card"><h2>Funnel — where every lead went</h2>' + _funnel(report["funnel"]) + "</div>")
    parts.append('<div class="two">')
    parts.append('<div class="card"><h2>Final outcome of each lead</h2>' + _status(report["final_status_breakdown"]) + "</div>")
    parts.append('<div class="card"><h2>Paid-provider usage &amp; spend</h2>'
                 '<div class="scroll"><table><thead><tr><th>Provider</th><th class="n">Calls</th>'
                 '<th class="n">Credits left</th><th class="n">Spend</th></tr></thead><tbody>'
                 + _providers(report["providers"]) + "</tbody></table></div></div>")
    parts.append("</div>")
    parts.append('<div class="card"><h2>Sample qualified &amp; contacted leads</h2>'
                 '<div class="scroll"><table><thead><tr><th>Company</th><th>Contact</th>'
                 '<th>Title</th><th class="n">Score</th></tr></thead><tbody>'
                 + _sample_contacts(leads) + "</tbody></table></div></div>")
    parts.append('<div class="card"><h2>Dead-letter queue — failures captured, not dropped</h2>'
                 '<div class="scroll"><table><thead><tr><th>Lead</th><th>Stage</th>'
                 '<th>Reason</th><th>Detail</th></tr></thead><tbody>'
                 + _deadletters(dls) + "</tbody></table></div></div>")
    parts.append(f'<footer>Generated by <code>build_site.py</code> from a live pipeline run · '
                 f'no third-party services or real data · '
                 f'<a href="{REPO_URL}">source on GitHub</a></footer>')
    parts.append("</div></body></html>")
    return "".join(parts)


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

    html = build_html(report, dls, leads)
    os.makedirs(SITE, exist_ok=True)
    out_path = os.path.join(SITE, "index.html")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"Wrote {out_path} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
