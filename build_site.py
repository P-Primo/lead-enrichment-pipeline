"""Generate a self-contained static dashboard (site/index.html) from a live run.

Runs the pipeline on the synthetic dataset, reads its real artifacts, and
templates them into a single dependency-free HTML page that explains — in plain
language — how a batch of brands is discovered on Instagram, flows through the
pipeline, syncs to a CRM funnel via webhooks, and how the reliability safeguards
behave. Suitable for a static host (Render / GitHub Pages) or opening directly in
a browser.

    python build_site.py     ->  writes site/index.html
"""
from __future__ import annotations

import csv
import html
import json
import os

from src import crm, sourcing
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

# Plain-English explanations shown on hover over each mechanism chip.
MECH_TIPS = {
    "partnership-signal detection":
        "Instagram posts are scanned for paid-partnership signals — the official "
        "'Paid partnership' label, #ad/#publi tags, tagged brand accounts, and story "
        "link stickers — to surface brands actively working with creators.",
    "input validation":
        "Every incoming row must have a company name and a well-formed domain. "
        "Malformed rows are rejected up front and sent to the dead-letter queue.",
    "dedup registry":
        "A registry of already-seen brands (keyed by domain) makes the pipeline "
        "idempotent — the same brand is never processed or contacted twice, even "
        "across runs.",
    "quota gate":
        "Before every paid API call, the provider's remaining credit is checked. If "
        "it's out, the record is paused cleanly instead of making a partial or "
        "over-budget call.",
    "retry + backoff":
        "Transient failures (timeouts, 5xx, rate limits) are retried with exponential "
        "backoff. Permanent errors like 'no data' are never retried.",
    "dead-letter":
        "Any record that errors is written to a dead-letter queue with its stage and "
        "reason, so it can be retried or investigated — never silently lost.",
    "title scoring":
        "Each contact's job title is scored by decision-making authority — founders, VPs, "
        "heads-of, and directors rank highest; interns, assistants, and support roles score "
        "zero. Only titles above the threshold advance.",
    "per-company cap":
        "Limits how many contacts are queued per brand, so outreach isn't "
        "over-concentrated on a single company.",
    "rate limiter":
        "A per-run send cap. Once it's hit, the remaining qualified leads are deferred "
        "to the next run instead of being blasted out all at once.",
    "CRM webhook":
        "On entering this stage, a webhook fires to advance the lead in the CRM funnel "
        "automatically — the CRM stays a live mirror of the pipeline with no manual entry.",
}

# Role-fit scoring tiers (mirrors the pipeline's title-scoring rule).
SCORE_TIERS = [
    ("3", "st-good", "Senior decision-maker / budget owner",
     "Founder / CEO · VP of Marketing · Chief Marketing Officer · Head of Growth · Director"),
    ("2", "st-series", "Manager or team lead — owns the function",
     "Marketing Manager · Brand Manager · Growth Team Lead"),
    ("1", "st-warn", "Individual contributor in the team",
     "Marketing Analyst · Growth Coordinator · Communications Specialist"),
    ("0", "st-muted", "No buying authority — skipped",
     "Marketing Intern · Sales Assistant · Support Agent · Office Receptionist"),
]

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

.tag{display:inline-block;font-size:.72rem;font-weight:600;letter-spacing:.05em;
  text-transform:uppercase;color:var(--series1);border:1px solid var(--border);
  border-radius:999px;padding:4px 12px;margin-bottom:16px}
h1{font-size:2rem;margin:0 0 10px;letter-spacing:-0.02em;line-height:1.15}
.lede{color:var(--ink2);margin:0;max-width:66ch;font-size:1.02rem}
.runline{color:var(--muted);font-size:.86rem;margin:12px 0 0}
.btn{display:inline-block;margin-top:18px;font-size:.86rem;font-weight:600;color:#fff;
  background:var(--series1);padding:9px 18px;border-radius:8px;text-decoration:none}

section{margin-top:40px}
.h2{font-size:1.25rem;margin:0 0 4px;letter-spacing:-0.01em}
.sec-intro{color:var(--ink2);font-size:.92rem;margin:0 0 18px;max-width:72ch}

.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px}
.tile .v{font-size:1.9rem;font-weight:650;letter-spacing:-0.02em}
.tile .l{color:var(--ink2);font-size:.82rem;margin-top:2px;line-height:1.35}
.tile .accent{height:3px;width:32px;border-radius:2px;background:var(--series1);margin-bottom:11px}

.flow{position:relative}
.step{position:relative;display:grid;grid-template-columns:30px 1fr;gap:16px;padding-bottom:14px}
.step:not(:last-child)::before{content:"";position:absolute;left:14px;top:30px;bottom:-2px;width:2px;background:var(--line)}
.node{width:30px;height:30px;border-radius:50%;background:var(--series1);color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:.82rem;font-weight:700;z-index:1}
.node.src{background:var(--good)}
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
.drop{font-size:.74rem;color:var(--crit);font-weight:600}
.drop.none{color:var(--good)}
.srcbits{display:flex;flex-wrap:wrap;gap:6px 14px;margin:2px 0 9px;font-size:.78rem;color:var(--ink2)}
.srcbits b{color:var(--ink);font-variant-numeric:tabular-nums}

/* hover-tooltip chips */
.chip{position:relative;display:inline-block;font-size:.68rem;color:var(--ink2);
  background:var(--grid);border-radius:5px;padding:2px 7px;cursor:help}
.chip .tip{position:absolute;left:0;bottom:calc(100% + 8px);width:250px;max-width:72vw;
  background:var(--ink);color:var(--plane);padding:9px 11px;border-radius:8px;font-size:.74rem;
  line-height:1.45;font-weight:400;text-transform:none;letter-spacing:0;
  box-shadow:0 8px 24px rgba(0,0,0,.28);opacity:0;visibility:hidden;transform:translateY(4px);
  transition:opacity .12s,transform .12s;z-index:20}
.chip:hover .tip,.chip:focus .tip{opacity:1;visibility:visible;transform:translateY(0)}

.features{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
.feat{background:var(--surface);border:1px solid var(--border);border-radius:11px;padding:15px 17px}
.feat h3{font-size:.92rem;margin:0 0 5px}
.feat p{font-size:.83rem;color:var(--ink2);margin:0}
.feat .num{color:var(--series1);font-weight:700}

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
.pill.st-muted{background:var(--line);color:var(--ink)} .pill.st-series{background:var(--series1)}
.muted-note{color:var(--muted);font-size:.8rem;margin:8px 2px 0}
pre{background:var(--grid);border:1px solid var(--border);border-radius:9px;padding:13px 15px;
  overflow-x:auto;font-size:.78rem;line-height:1.55;color:var(--ink);margin:0;
  font-family:ui-monospace,"SF Mono","Cascadia Code",Consolas,monospace}

footer{color:var(--muted);font-size:.82rem;margin-top:44px;padding-top:18px;border-top:1px solid var(--border);text-align:center}
footer a{color:var(--series1);text-decoration:none}
@media(max-width:600px){ h1{font-size:1.6rem} .tiles{grid-template-columns:repeat(2,1fr)} }
"""


def esc(value) -> str:
    return html.escape(str(value))


def _chip(label):
    tip = MECH_TIPS.get(label, "")
    tip_html = f'<span class="tip">{esc(tip)}</span>' if tip else ""
    return f'<span class="chip" tabindex="0">{esc(label)}{tip_html}</span>'


def _tile(value, label):
    return (f'<div class="tile"><div class="accent"></div>'
            f'<div class="v">{value}</div><div class="l">{label}</div></div>')


def _tiles(report, crm_events):
    s = report["summary"]
    return "".join([
        _tile(s["input_records"], "Brands sourced (Instagram)"),
        _tile(s["contacted"], "Contacted"),
        _tile(f'{s["ingest_to_contact_rate_pct"]}%', "Sourced → contacted"),
        _tile(crm_events, "CRM updates auto-synced"),
        _tile(s["total_retries"], "Transient failures recovered"),
        _tile(s["dead_lettered"], "Dead-lettered (nothing lost)"),
    ])


def _source_step(src):
    bits = " ".join(
        f'<span><b>{n}</b> {esc(name)}</span>' for name, n in src["breakdown"]
    )
    chip = _chip("partnership-signal detection")
    return (
        '<div class="step"><div class="node src">1</div>'
        '<div class="step-body">'
        '<div class="step-top"><span class="step-name">Source from Instagram</span>'
        f'<span class="step-count">{src["unique_brands"]} <small>brands</small></span></div>'
        '<div class="step-desc">Scan creators’ posts for paid-partnership signals and extract the brands behind them.</div>'
        f'<div class="srcbits">{bits}</div>'
        '<div class="step-bar"><span style="width:100%"></span></div>'
        f'<div class="step-meta"><div class="tags">{chip}</div>'
        f'<span class="drop none">{src["posts_scanned"]:,} posts → {src["partnership_signals"]} signals → {src["unique_brands"]} brands</span></div>'
        '</div></div>'
    )


def _stepper(report, src):
    f = report["funnel"]
    base = report["summary"]["input_records"] or 1
    stages = [
        ("2", "Ingest &amp; validate", "Load the sourced brands and reject malformed rows.",
         f["ingested"], base - f["ingested"], "malformed rows → dead-letter",
         ["input validation"]),
        ("3", "Dedupe", "Skip brands already seen in a previous run.",
         f["deduped"], f["ingested"] - f["deduped"], "duplicates skipped",
         ["dedup registry"]),
        ("4", "Enrich <small>(paid)</small>", "Find each brand’s decision-maker — name, title, and email.",
         f["enriched"], f["deduped"] - f["enriched"], "no contact found / failed → dead-letter",
         ["quota gate", "retry + backoff", "dead-letter"]),
        ("5", "Verify email <small>(paid)</small>", "Confirm each email address is deliverable.",
         f["verified"], f["enriched"] - f["verified"], "unverifiable emails skipped",
         ["quota gate", "retry + backoff"]),
        ("6", "Score &amp; qualify", "Score each contact by decision-making seniority; keep only strong matches.",
         f["scored"], f["verified"] - f["scored"], "low-seniority roles skipped",
         ["title scoring"]),
        ("7", "Queue", "Order by score and cap the number of contacts per brand.",
         f["queued"], f["scored"] - f["queued"], "over per-company cap",
         ["per-company cap"]),
        ("8", "Outreach <small>(paid)</small>", "Send cold outreach, respecting the daily send limit.",
         f["contacted"], f["queued"] - f["contacted"], "deferred to next run (daily cap)",
         ["quota gate", "rate limiter"]),
    ]
    out = ['<div class="flow">', _source_step(src)]
    for num, name, desc, count, drop, reason, tags in stages:
        width = count / base * 100
        chips = "".join(_chip(t) for t in tags) + _chip("CRM webhook")
        drop_html = (f'<span class="drop">−{drop} {reason}</span>' if drop > 0
                     else '<span class="drop none">nothing dropped</span>')
        out.append(
            f'<div class="step"><div class="node">{num}</div>'
            f'<div class="step-body">'
            f'<div class="step-top"><span class="step-name">{name}</span>'
            f'<span class="step-count">{count} <small>remaining</small></span></div>'
            f'<div class="step-desc">{desc}</div>'
            f'<div class="step-bar"><span style="width:{width:.1f}%"></span></div>'
            f'<div class="step-meta"><div class="tags">{chips}</div>{drop_html}</div>'
            f'</div></div>'
        )
    out.append("</div>")
    return "".join(out)


def _crm_section(report, config, leads):
    events = crm.event_count(report)
    webhook_url = config.get("crm", {}).get("webhook_url", "https://crm.example.com/webhooks")
    rows = ""
    for pipe_stage, crm_stage, event in crm.CRM_FUNNEL:
        rows += (f'<tr><td class="strong">{esc(pipe_stage)}</td>'
                 f'<td>{esc(crm_stage)}</td><td><code>{esc(event)}</code></td></tr>')

    example = next((l for l in leads if l.get("status") == "contacted" and l.get("score")), None)
    if example:
        payload = crm.build_event(example["lead_id"], example["company"],
                                  "verified", "scored", "Qualified",
                                  "lead.qualified", score=example["score"])
    else:
        payload = crm.build_event("L058", "Jade Robotics", "verified", "scored",
                                  "Qualified", "lead.qualified", score=3)
    payload_txt = f"POST {webhook_url}\n" + json.dumps(payload, indent=2)

    return (
        '<section><div class="h2">CRM sync &mdash; webhook-driven</div>'
        '<p class="sec-intro">Every time a lead advances a stage, a webhook fires and moves it '
        "along the CRM funnel automatically. The CRM becomes a live mirror of the pipeline with "
        f"zero manual data entry — <strong>{events:,} updates</strong> were synced this run.</p>"
        '<div class="card"><div class="scroll"><table><thead><tr>'
        "<th>Pipeline stage</th><th>CRM funnel stage</th><th>Webhook event</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></div></div>"
        '<p class="muted-note">Example payload emitted when a lead is qualified:</p>'
        f'<pre>{esc(payload_txt)}</pre></section>'
    )


def _scoring_section():
    rows = ""
    for score, cls, signal, examples in SCORE_TIERS:
        rows += (f'<tr><td><span class="pill {cls}">{score}</span></td>'
                 f'<td class="strong">{signal}</td><td>{examples}</td></tr>')
    return (
        '<section><div class="h2">How leads are scored (decision-making authority)</div>'
        '<p class="sec-intro">At the qualify stage, each contact’s job title is scored 0–3 by how much '
        "decision-making authority it holds over the buying decision. Only scores of 1 or higher advance, and "
        "higher scores are contacted first.</p>"
        '<div class="card"><div class="scroll"><table><thead><tr>'
        '<th>Score</th><th>What it signals</th><th>Example titles</th>'
        f"</tr></thead><tbody>{rows}</tbody></table></div></div></section>"
    )


def _features(report):
    s = report["summary"]
    fsb = report["final_status_breakdown"]
    cards = [
        ("Quota gate",
         f'Credits are checked before <em>every</em> paid API call. The run spent only '
         f'<span class="num">${s["simulated_spend_usd"]}</span> and pauses cleanly instead of overspending if credits run low.'),
        ("Retry with backoff",
         f'Transient failures are retried with exponential backoff — '
         f'<span class="num">{s["total_retries"]}</span> recovered this run. Permanent errors are never retried.'),
        ("Dead-letter queue",
         f'Every failed record is captured with a reason — <span class="num">{s["dead_lettered"]}</span> '
         f'this run — so failures are triaged, never silently dropped.'),
        ("Dedup registry",
         f'Idempotent by design: the same brand is never processed or contacted twice. '
         f'<span class="num">{fsb.get("duplicate", 0)}</span> duplicate(s) caught this run.'),
        ("Rate limiter",
         f'Respects a daily send cap; overflow is deferred to the next run rather than dropped — '
         f'<span class="num">{fsb.get("queued", 0)}</span> deferred this run.'),
        ("Config-driven",
         'Credit limits, retry counts, the daily cap, scoring thresholds, and the CRM webhook URL '
         'all live in one config file — nothing is hard-coded in the logic.'),
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


def build_html(report, dls, leads, config):
    s = report["summary"]
    src = sourcing.discover(s["input_records"])
    crm_events = crm.event_count(report)
    sample_rows, sample_n = _sample_table(leads)

    p = []
    p.append('<!doctype html><html lang="en"><head><meta charset="utf-8">')
    p.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    p.append("<title>Lead Enrichment &amp; Outreach Pipeline — Live Demo</title>")
    p.append("<style>" + CSS + "</style></head><body><div class=\"wrap\">")

    p.append(
        '<header><span class="tag">Portfolio project · live synthetic demo</span>'
        "<h1>Lead Enrichment &amp; Outreach Pipeline</h1>"
        '<p class="lede">A resilient automation pipeline that <strong>discovers brands from creators’ '
        "paid-partnership posts on Instagram</strong>, turns them into verified, scored, ready-to-contact "
        "leads, and safely hands the qualified ones to cold outreach — syncing every step to a CRM "
        "funnel by webhook. Built so that <strong>no record is silently lost and no API budget is "
        "overspent</strong>, even when third-party services fail.</p>"
        f'<p class="runline">Everything below is a live, reproducible run: <strong>{src["posts_scanned"]:,} '
        f'simulated Instagram posts → {s["input_records"]} brands</strong>. No real data or paid services.</p>'
        f'<a class="btn" href="{REPO_URL}">View the code on GitHub →</a></header>'
    )

    p.append(
        '<section><div class="h2">At a glance</div>'
        '<p class="sec-intro">The headline numbers from this run.</p>'
        f'<div class="tiles">{_tiles(report, crm_events)}</div></section>'
    )

    p.append(
        '<section><div class="h2">How it works &mdash; follow one batch through the pipeline</div>'
        f'<p class="sec-intro">A batch of {s["input_records"]} brands — sourced from Instagram — passes '
        "through the stages below. Each stage removes what doesn’t qualify (the bar shrinks with it), but "
        "every removal is accounted for: skipped, deferred, or sent to the dead-letter queue, never dropped "
        "without a trace. <em>Hover any chip to see how that safeguard works.</em></p>"
        + _stepper(report, src) + "</section>"
    )

    p.append(_crm_section(report, config, leads))
    p.append(_scoring_section())

    p.append(
        '<section><div class="h2">Built for reliability</div>'
        "<p class=\"sec-intro\">The safeguards that let this run unattended against paid, flaky, "
        "rate-limited third-party APIs — each shown with what it actually did this run.</p>"
        + _features(report) + "</section>"
    )

    p.append(
        '<section><div class="h2">Sample of enriched leads</div>'
        '<p class="sec-intro">A slice of the contacts the pipeline found, with the seniority score it '
        "assigned and what happened to each. “Contacted” were sent; “Queued” were deferred by "
        "the daily cap; “Skipped” didn’t meet the email or score bar.</p>"
        f'<div class="card"><div class="scroll"><table><thead><tr>'
        "<th>Company</th><th>Contact</th><th>Title</th><th class=\"n\">Score</th><th>Status</th>"
        f"</tr></thead><tbody>{sample_rows}</tbody></table></div></div>"
        f'<p class="muted-note">Showing {sample_n} of the enriched contacts from this run.</p></section>'
    )

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

    page = build_html(report, dls, leads, config)
    os.makedirs(SITE, exist_ok=True)
    out_path = os.path.join(SITE, "index.html")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"Wrote {out_path} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
