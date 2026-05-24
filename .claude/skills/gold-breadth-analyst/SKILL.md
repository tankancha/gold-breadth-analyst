---
name: gold-breadth-analyst
description: Cloud-agent skill that generates the daily Gold Options Flow & Volatility narrative for COMEX gold (GC) and commits it as JSON to the self-hosted GitHub Pages dashboard. Reads pre-scraped data from docs/data/*.json. Triggers on requests for gold options market breadth, OI profile, gamma exposure, vol surface, max pain, or daily gold report.
compatibility: Cloud Claude Code agent (no Python, no local server). Hybrid architecture — a GitHub Actions scraper feeds docs/data/*.json; this skill writes docs/data/analysis.json which the static dashboard reads in the browser.
---

# Gold Breadth Analyst (Cloud Skill — JSON publisher)

Cloud-side of the Gold Breadth pipeline. A GitHub Actions workflow scrapes Barchart at 06:50 BKK weekdays and commits per-day JSON snapshots under `docs/data/`. This skill runs at 07:00 BKK, reads the last 5 sessions, writes a single `docs/data/analysis.json` with the AI narrative and day-trade CTA, and pushes. The static dashboard at <https://tankancha.github.io/gold-breadth-analyst/> fetches that JSON client-side and renders the visual report.

**Notion is no longer used.** The historical Notion parent page can be deleted manually any time.

## Why hybrid

Cloud agent `WebFetch` is blocked by Barchart, Yahoo Finance, and every other retail finance site (Cloudflare bot detection on Anthropic's IP range, returns HTTP 403). Direct API access for COMEX gold options requires either a paid feed (Polygon.io ~$29/mo) or a stateful gateway (IBKR). The hybrid avoids both: GitHub Actions runs the Playwright scraper, this cloud skill does narrative analysis.

## Output

A single file: `docs/data/analysis.json`. Schema: see `references/analysis-schema.md`. After writing it, commit and push to `main`. GitHub Pages auto-redeploys; user refreshes the dashboard and sees today's analysis.

## Style

Professional, concise, expert-level — written for an options trader's morning scan. Lead every claim with a specific number (strike, OI, IV%, GEX). No disclaimers, no boilerplate, no emoji.

Narrate between every tool-call batch. Before any tool call, emit at least one sentence of plain text to keep the stream alive.

---

## Pass A — Read scraped data

→ text: "Pulling today's gold options snapshot and 5-day history…"

→ Read `docs/data/latest.json` (today's full chain — same schema as the legacy `data/latest.json`).

→ Read `docs/data/history.json` (5-day rollup — sparkline-ready daily summaries + cross-day deltas).

The `latest.json` schema:

```json
{
  "scraped_at": "2026-05-24T00:50:00+07:00",
  "symbol": "GCM26",
  "expiry": {"symbol": "GCM26", "label": "Jun '26", "dte": 56, "iv": 23.65},
  "spot": 4774.6,
  "future_chg": 76.2,
  "iv_atm": 23.65,
  "total_call_oi": 166948,
  "total_put_oi": 91513,
  "total_call_vol": 11264,
  "total_put_vol": 5112,
  "pc_oi_ratio": 0.548,
  "max_pain": 5170,
  "chain": [{"strike": 4500, "call_oi": 1234, "put_oi": 5678, "call_vol": ..., "put_vol": ..., "call_last": ..., "put_last": ...}, ...],
  "gex_heatmap": [{"strike": 4800, "call_gex": 8.6, "put_gex": -0.9, "net_gex": 7.7}, ...]
}
```

The `history.json` schema:

```json
{
  "generated_at": "...",
  "window_days": 5,
  "days": [
    {"date": "2026-05-20", "spot": 4575.3, "max_pain": 4650, "pc_oi_ratio": 1.33,
     "atm_iv": 18.4, "put_wall": 4500, "call_wall": 4800, "gex_sign": "negative", ...},
    ...
  ],
  "deltas": {
    "spot_change": +42.1,
    "max_pain_drift": +50,
    "iv_change_pp": -1.2,
    "put_wall_migration": [4500, 4500, 4500, 4450, 4500],
    "call_wall_migration": [4800, 4800, 4800, 4750, 4800],
    ...
  }
}
```

**Staleness check:** if `scraped_at` is more than 24 hours old, OR `chain` has fewer than 5 rows, OR `spot` is null, do NOT publish — return: `"DATA UNAVAILABLE — scraper has not produced fresh data. Run skipped."` (No commit, no push.)

---

## Computations

The scraper already provides `max_pain`, `gex_heatmap`, `total_call_oi`, etc. Use them directly. Helpers for things you derive locally:

- **Support / Resistance zones:** top 3 strikes by `put_oi` and `call_oi` descending from the chain (use the dashboard's window — strikes within ±25% of spot).
- **1σ daily move:** `spot × (iv_atm / 100) / √252`.
- **Net GEX summary:** sum `net_gex` across strikes within ±$200 of spot — the sign is local dealer posture. The gamma flip strike is where cumulative `net_gex` crosses zero scanning low→high.
- **5-day deltas:** already in `history.json.deltas`. Use them verbatim; do not re-derive.

Full formulas: `references/computation-formulas.md`. Schema for the output JSON: `references/analysis-schema.md`.

---

## Pass B — Write analysis JSON, commit, push

→ text: "Writing today's analysis to docs/data/analysis.json…"

Generate the JSON exactly per `references/analysis-schema.md`. Required top-level keys: `generated_at`, `today_summary`, `five_day_thesis`, `what_changed` (array), `prediction`, `day_trade_cta` (object).

**Five-day thesis is the new center of gravity.** Spend more words on what changed vs 5 days ago than on today's snapshot alone — the user can see today's numbers right above on the dashboard. Reference specific cross-day deltas: max-pain drift, wall migrations, GEX sign flips, IV compression / expansion.

→ Write the file: `Write docs/data/analysis.json` (overwrite whatever was there yesterday — only one analysis file exists at a time).

→ text: "Committing and pushing to GitHub Pages…"

→ Run, in order (use the appropriate shell tool):
```
git add docs/data/analysis.json
git commit -m "analysis: $(TZ=Asia/Bangkok date +%F)"
git pull --rebase origin main || true
git push origin main
```

The `git pull --rebase` guards against a race with the GHA scraper if it ran late. The push triggers GitHub Pages to redeploy (~30 seconds).

→ text: "Done. Dashboard URL: https://tankancha.github.io/gold-breadth-analyst/"

Return the dashboard URL.

---

## Constraints

- Do NOT call `WebFetch` for market data. Cloud egress is blocked at Barchart/Yahoo/etc.
- Do NOT call any Notion MCP tools. Notion is no longer the publication target — the Notion connector and the legacy "Gold Breadth" parent page are deprecated.
- Do NOT write any local files outside `docs/data/analysis.json`.
- All dates/times in Asia/Bangkok (UTC+7) for user-facing strings; ISO 8601 with `+07:00` in JSON.
- Keep `today_summary` ≤ 4 sentences, `five_day_thesis` ≤ 5, `what_changed` ≤ 6 bullets. The dashboard renders verbatim — over-long prose breaks the layout.
- If commit fails (e.g., nothing changed because re-run), exit cleanly without retry — that's just a no-op day.
