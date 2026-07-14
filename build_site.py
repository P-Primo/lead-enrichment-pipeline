"""Generate a self-contained static dashboard (site/index.html) from a live run.

Runs the pipeline on the synthetic dataset, reads its real artifacts, and
templates them into a single dependency-free HTML page that explains — in plain
language — what the pipeline does, how a batch of leads flows through it, and how
its reliability safeguards behave. Suitable for a static host (Render / GitHub
Pages) or opening directly in a browser.

    python build_site.py     ->  writes site/index.html
"""
from __future__ import annotations

import csv
import html
import json
import os

from src.pipeline import run_pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
SITE = os.path.join(HERE, "site")

REPO_URL = "https://github.com/P-Primo/lead-enrichment-pipeline"

STATUS_LABELS = {
    "contacted": ("Contacted", "st-good"),
    "skipped": ("Skipped", "st-muted"),
    "duplicate": ("Duplicate", "st-warn"),
    "dead_lettered": ("Dead-lettered", "st-crit"),
    "paused_api_limit": ("Paused", "st-serious"),
    "queued": ("Queued", "st-serious"),
    "new": ("New", "st-muted"),
}


def esc(value) -> str:
    return html.escape(str(value))


CSS = """
:root{
  --plane:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#898781; --grid:#e7e6e0; --line:#c3c2b7; --series1:#2a78d6;
  --border:rgba(11,11,11,0.10);
  --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --crit:#d03b3b;
}
@media (prefers-color-scheme:dark){
  :root{
    --plane:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7;
    --muted:#898781; --grid:#2c2c2a; --line:#383835; --series1:#3987e5;
    --border:rgba(255,255,255,0.12);
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.55}
.wrap{max-width:900px;margin:0 auto;padding:44px 20px 72px}

/* hero */
.tag{display:inline-block;font-size:.72rem;font-weight:600;letter-spacing:.05em;
  text-transform:uppercase;color:var(--series1);border:1px solid var(--border);
  border-radius:999px;padding:4px 12px;margin-bottom:16px}
h1{font-size:2rem;margin:0 0 10px;letter-spacing:-0.02em;line-height:1.15}
.lede{color:var(--ink2);margin:0;max-width:66ch;font-size:1.02rem}
.runline{color:var(--muted);font-size:.86rem;margin:12px 0 0}
.btn{display:inline-block;margin-top:18px;font-size:.86rem;font-weight:600;color:#fff;
  background:var(--series1);padding:9px 18px;border-radius:8px;text-decoration:none}

/* section scaffolding */
section{margin-top:40px}
.h2{font-size:1.25rem;margin:0 0 4px;letter-spacing:-0.01em}
.sec-intro{color:var(--ink2);font-size:.92rem;margin:0 0 18px;max-width:70ch}

/* tiles */
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px}
.tile .v{font-size:1.9rem;font-weight:650;letter-spacing:-0.02em}
.tile .l{color:var(--ink2);font-size:.82rem;margin-top:2px;line-height:1.35}
.tile .accent{height:3px;width:32px;border-radius:2px;background:var(--series1);margin-bottom:11px}

/* pipeline flow (stepper) */
.flow{position:relative}
.step{position:relative;display:grid;grid-template-columns:30px 1fr;gap:16px;padding-bottom:14px}
.step:not(:last-child)::before{content:"";position:absolute;left:14px;top:30px;bottom:-2px;width:2px;background:var(--line)}
.node{width:30px;height:30px;border-radius:50%;background:var(--series1);color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:.82rem;font-weight:700;z-index:1}
.step-body{background:var(--surface);border:1px solid var(--border);border-radius:11px;padding:13px 16px}
.step-top{display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.step-name{font-weight:650;font-size:.98rem}
.step-count{font-variant-numeric:tabular-nums;font-weight:700;font-size:1.05rem;white-space:nowrap}
.step-count small{color:var(--muted);font-weight:500;font-size:.72rem}
.step-desc{color:var(--ink2);font-size:.87rem;margin:3px 0 9px}
.step-bar{height:8px;background:var(--grid);border-radius:4px;overflow:hidden}
.step-bar > span{display:block;height:100%;background:var(--series1);border-radius:4px;min-width:3px}
.step-meta{display:flex;justify-content:space-between;align-items:center;margin-top:9px;gap:10px;flex-wrap:wrap}
.tags{display:flex;gap:6px;flex-wrap:wrap}
.tag-sm{font-size:.68rem;color:var(--ink2);background:var(--grid);border-radius:5px;padding:2px 7px}
.drop{font-size:.74rem;color:var(--crit);font-weight:600}
.drop.none{color:var(--good)}

/* reliability feature cards */
.features{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
.feat{background:var(--surface);border:1px solid var(--border);border-radius:11px;padding:15px 17px}
.feat h3{font-size:.92rem;margin:0 0 5px}
.feat p{font-size:.83rem;color:var(--ink2);margin:0}
.feat .num{color:var(--series1);font-weight:700}

/* tables */
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:6px 18px 10px}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.86rem}
th{text-align:left;text-transform:uppercase;letter-spacing:.04em;font-size:.68rem;
  color:var(--muted);font-weight:600;padding:12px 10px 8px;border-bottom:1px solid var(--line)}
td{padding:9px 10px;border-bottom:1px solid var(--grid);color:var(--ink2);vertical-align:top}
tr:last-child td{border-bottom:none}
td.n{font-variant-numeric:tabular-nums;text-align:right;color:var(--ink)}
td.strong{color:var(--ink);font-weight:600}
.pill{display:inline-block;font-size:.7rem;font-weight:600;padding:2px 9px;border-radius:999px;white-space:nowrap;color:#fff}
.pill.st-good{background:var(--good)} .pill.st-warn{background:var(--warn);color:#3a2a00}
.pill.st-crit{background:var(--crit)} .pill.st-serious{background:var(--serious);color:#2e1400}
.pill.st-muted{background:var(--line);color:var(--ink)}
.muted-note{color:var(--muted);font-size:.8rem;margin:8px 2px 0}

footer{color:var(--muted);font-size:.82rem;margin-top:44px;padding-top:18px;border-top:1px solid var(--border);text-align:center}
footer a{color:var(--series1);text-decoration:none}
@media(max-width:600px){ h1{font-size:1.6rem} .tiles{grid-template-columns:repeat(2,1fr)} }
"""


def _tile(value, label):
    return (f'<div class="tile"><div class="accent"></div>'
            f'<div class="v">{value}</div><div class="l">{label}</div></div>')


def _tiles(report):
    s = report["summary"]
    return "".join([
        _tile(s["input_records"], "Companies received"),
        _tile(s["contacted"], "Contacted"),
        _tile(f'{s["ingest_to_contact_rate_pct"]}%', "Received → contacted"),
        _tile(s["total_retries"], "Transient failures auto-recovered"),
        _tile(s["dead_lettered"], "Dead-lettered (nothing lost)"),
        _tile(f'${s["simulated_spend_usd"]}', "Simulated API spend"),
    ])


def _stepper(report):
    f = report["funnel"]
    base = report["summary"]["input_records"] or 1
    stages = [
        ("1", "Ingest &amp; validate", "Load the raw company list and reject malformed rows.",
         f["ingested"], base - f["ingested"], "malformed rows → dead-letter",
         ["input validation"]),
        ("2", "Dedupe", "Skip companies already seen in a previous run.",
         f["deduped"], f["ingested"] - f["deduped"], "duplicates skipped",
         ["dedup registry"]),
        ("3", "Enrich <small>(paid)</small>", "Find each company's decision-maker — name, title, and email.",
         f["enriched"], f["deduped"] - f["enriched"], "no contact found / failed → dead-letter",
         ["quota gate", "retry + backoff", "dead-letter"]),
        ("4", "Verify email <small>(paid)</small>", "Confirm each email address is deliverable.",
         f["verified"], f["enriched"] - f["verified"], "unverifiable emails skipped",
         ["quota gate", "retry + backoff"]),
        ("5", "Score &amp; qualify", "Score each contact by role fit; keep only strong matches.",
         f["scored"], f["verified"] - f["scored"], "low role-fit score skipped",
         ["title scoring"]),
        ("6", "Queue", "Order by score and cap the number of contacts per company.",
         f["queued"], f["scored"] - f["queued"], "over per-company cap",
         ["per-company cap"]),
        ("7", "Outreach <small>(paid)</small>", "Send cold outreach, respecting the daily send limit.",
         f["contacted"], f["queued"] - f["contacted"], "deferred to next run (daily cap)",
         ["quota gate", "rate limiter"]),
    ]
    out = ['<div class="flow">']
    for num, name, desc, count, drop, reason, tags in stages:
        width = count / base * 100
        tag_html = "".join(f'<span class="tag-sm">{t}</span>' for t in tags)
        if drop > 0:
            drop_html = f'<span class="drop">−{drop} {reason}</span>'
        else:
            drop_html = '<span class="drop none">nothing dropped</span>'
        out.append(
            f'<div class="step"><div class="node">{num}</div>'
            f'<div class="step-body">'
            f'<div class="step-top"><span class="step-name">{name}</span>'
            f'<span class="step-count">{count} <small>remaining</small></span></div>'
            f'<div class="step-desc">{desc}</div>'
            f'<div class="step-bar"><span style="width:{width:.1f}%"></span></div>'
            f'<div class="step-meta"><div class="tags">{tag_html}</div>{drop_html}</div>'
            f'</div></div>'
        )
    out.append("</div>")
    return "".join(out)


def _features(report):
    s = report["summary"]
    fsb = report["final_status_breakdown"]
    deferred = fsb.get("queued", 0)
    duplicates = fsb.get("duplicate", 0)
    cards = [
        ("Quota gate",
         f'Credits are checked before <em>every</em> paid API call. The run spent only '
         f'<span class="num">${s["simulated_spend_usd"]}</span> and stops cleanly instead of overspending if credits run low.'),
        ("Retry with backoff",
         f'Transient failures (timeouts, rate limits) are retried with exponential backoff — '
         f'<span class="num">{s["total_retries"]}</span> recovered this run. Permanent errors are never retried.'),
        ("Dead-letter queue",
         f'Every failed record is captured with a reason — <span class="num">{s["dead_lettered"]}</span> '
         f'this run — so failures are triaged, never silently dropped.'),
        ("Dedup registry",
         f'Idempotent by design: the same company is never processed or contacted twice. '
         f'<span class="num">{duplicates}</span> duplicate(s) caught this run.'),
        ("Rate limiter",
         f'Respects a daily send cap; overflow is deferred to the next run rather than dropped — '
         f'<span class="num">{deferred}</span> deferred this run.'),
        ("Config-driven",
         'Credit limits, retry counts, the daily cap, and scoring thresholds all live in one config '
         'file — nothing is hard-coded in the logic.'),
    ]
    out = ['<div class="features">']
    for title, body in cards:
        out.append(f'<div class="feat"><h3>{title}</h3><p>{body}</p></div>')
    out.append("</div>")
    return "".join(out)


def _sample_table(leads, limit=15):
    picked = [l for l in leads if l.get("contact_name")][:limit]
    rows = ""
    for l in picked:
        label, cls = STATUS_LABELS.get(l.get("status", ""), (l.get("status", ""), "st-muted"))
        rows += (f'<tr><td class="strong">{esc(l["company"])}</td>'
                 f'<td>{esc(l["contact_name"])}</td>'
                 f'<td>{esc(l["title"])}</td>'
                 f'<td class="n">{esc(l["score"])}</td>'
                 f'<td><span class="pill {cls}">{esc(label)}</span></td></tr>')
    return rows, len(picked)


def _deadletters(dls, limit=12):
    rows = ""
    for d in dls[:limit]:
        rows += (f'<tr><td class="strong">{esc(d["lead_id"])}</td><td>{esc(d["stage"])}</td>'
                 f'<td>{esc(d["reason"])}</td><td>{esc(d.get("detail",""))}</td></tr>')
    return rows


def build_html(report, dls, leads):
    s = report["summary"]
    sample_rows, sample_n = _sample_table(leads)

    p = []
    p.append('<!doctype html><html lang="en"><head><meta charset="utf-8">')
    p.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    p.append("<title>Lead Enrichment &amp; Outreach Pipeline — Live Demo</title>")
    p.append("<style>" + CSS + "</style></head><body><div class=\"wrap\">")

    # hero
    p.append(
        '<header><span class="tag">Portfolio project · live synthetic demo</span>'
        "<h1>Lead Enrichment &amp; Outreach Pipeline</h1>"
        '<p class="lede">A resilient automation pipeline that turns a raw list of companies into '
        "verified, scored, ready-to-contact leads — then safely hands the qualified ones to cold "
        "outreach. It is built so that <strong>no record is silently lost and no API budget is "
        "overspent</strong>, even when third-party services fail or run out of credit.</p>"
        f'<p class="runline">Everything below is a live, reproducible run on <strong>{s["input_records"]} '
        "synthetic companies</strong> — no real data or paid services involved.</p>"
        f'<a class="btn" href="{REPO_URL}">View the code on GitHub →</a></header>'
    )

    # at a glance
    p.append(
        '<section><div class="h2">At a glance</div>'
        '<p class="sec-intro">The headline numbers from this run.</p>'
        f'<div class="tiles">{_tiles(report)}</div></section>'
    )

    # the flow
    p.append(
        '<section><div class="h2">How it works &mdash; follow one batch through the pipeline</div>'
        f'<p class="sec-intro">The batch of {s["input_records"]} companies passes through seven stages. '
        "Each stage removes what doesn’t qualify, and the bar shrinks with it — but every removal is "
        "accounted for (skipped, deferred, or sent to the dead-letter queue), never dropped without a trace.</p>"
        + _stepper(report) + "</section>"
    )

    # reliability
    p.append(
        '<section><div class="h2">Built for reliability</div>'
        "<p class=\"sec-intro\">The safeguards that let this run unattended against paid, flaky, "
        "rate-limited third-party APIs — each shown with what it actually did this run.</p>"
        + _features(report) + "</section>"
    )

    # sample leads
    p.append(
        '<section><div class="h2">Sample of enriched leads</div>'
        f'<p class="sec-intro">A slice of the contacts the pipeline found, with the role-fit score it '
        "assigned and what happened to each. “Contacted” were sent; “Queued” were deferred by "
        "the daily cap; “Skipped” didn’t meet the email or score bar.</p>"
        f'<div class="card"><div class="scroll"><table><thead><tr>'
        "<th>Company</th><th>Contact</th><th>Title</th><th class=\"n\">Score</th><th>Status</th>"
        f"</tr></thead><tbody>{sample_rows}</tbody></table></div></div>"
        f'<p class="muted-note">Showing {sample_n} of the enriched contacts from this run.</p></section>'
    )

    # dead-letter
    p.append(
        '<section><div class="h2">Dead-letter queue</div>'
        "<p class=\"sec-intro\">When a record can’t be processed, it lands here with the stage and "
        "reason — so nothing fails silently and every failure can be retried or investigated.</p>"
        f'<div class="card"><div class="scroll"><table><thead><tr>'
        "<th>Lead</th><th>Stage</th><th>Reason</th><th>Detail</th>"
        f"</tr></thead><tbody>{_deadletters(dls)}</tbody></table></div></div>"
        f'<p class="muted-note">{s["dead_lettered"]} record(s) captured this run.</p></section>'
    )

    p.append(
        f'<footer>Generated by <code>build_site.py</code> from a live pipeline run · '
        f'synthetic data, no third-party services · '
        f'<a href="{REPO_URL}">source on GitHub</a></footer>'
    )
    p.append("</div></body></html>")
    return "".join(p)


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

    page = build_html(report, dls, leads)
    os.makedirs(SITE, exist_ok=True)
    out_path = os.path.join(SITE, "index.html")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"Wrote {out_path} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
