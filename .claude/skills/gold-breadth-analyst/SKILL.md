---
name: gold-breadth-analyst
description: Cloud-agent skill that generates the daily Gold Options Flow & Volatility Report for COMEX gold (GC) and publishes it to Notion. Reads pre-scraped data from data/latest.json in this repo. Triggers on requests for gold options market breadth, OI profile, gamma exposure, vol surface, max pain, or daily gold report.
compatibility: Cloud Claude Code agent (no Python, no local server). Hybrid architecture — a separate local scraper feeds data/latest.json.
---

# Gold Breadth Analyst (Hybrid Cloud Skill)

Cloud-side of the hybrid Gold Breadth report. A local scraper writes `data/latest.json` to this repo on a schedule; this skill reads that file, computes options metrics, and publishes a Notion sub-page.

## Why hybrid

Cloud agent `WebFetch` is blocked by Barchart, Yahoo Finance, and every other retail finance site (Cloudflare bot detection on Anthropic's IP range, returns HTTP 403). Direct API access for COMEX gold options requires either a paid feed (Polygon.io ~$29/mo) or a stateful gateway (IBKR). The hybrid avoids both: a tiny always-on scraper produces the JSON, the cloud agent does everything else.

## Output

A Notion sub-page under the parent **Gold Breadth** (`33d51c3f-9aab-8052-a54b-dc74939b48e2`). Title: `Gold Breadth — DD MMM YYYY` (today in Asia/Bangkok).

## Style

Professional, concise, expert-level — written for an options trader's morning scan. Lead every claim with a specific number (strike, OI, IV%, GEX). No disclaimers or boilerplate.

Narrate between every tool-call batch. Before any tool call, emit at least one sentence of plain text to keep the stream alive.

---

## Pass A — Read pre-scraped data

→ text: "Reading today's gold options chain from data/latest.json..."

→ `Read data/latest.json`

The file is the cached_data.json schema produced by the upstream `gold-market-breadth` scraper. Key fields:

```json
{
  "scraped_at": "2026-05-04T00:50:00+07:00",
  "symbol": "GCM26",
  "expiry": {"symbol": "GCM26", "label": "Jun '26", "dte": 56, "iv": 23.65},
  "spot": 4774.6,
  "future_chg": 76.2,
  "volume": 11461,
  "iv_atm": 23.65,
  "vol_settle": 23.65,
  "intraday_call": 8103,
  "intraday_put": 3358,
  "total_call_oi": 166948,
  "total_put_oi": 91513,
  "pc_oi_ratio": 0.548,
  "max_pain": 5170,
  "chain": [{"strike": 4500, "call_oi": 1234, "put_oi": 5678, "iv": 28.4, ...}, ...],
  "gex_heatmap": [{"strike": 4800, "call_gex": 8.6, "put_gex": -0.9, "net_gex": 7.7}, ...]
}
```

**Staleness check:** if `scraped_at` is more than 6 hours old, add a callout to the report noting the data age. If the file is missing, more than 24 hours stale, or has `chain` shorter than 5 entries, do NOT publish — return `"DATA UNAVAILABLE — local scraper has not pushed fresh data. Run skipped."`

---

## Computations

The upstream scraper already computes `max_pain` and `gex_heatmap`. Use those directly. You still need to compute or extract:

**Support / Resistance zones**
- Support: top 3 strikes by `put_oi` descending in the chain
- Resistance: top 3 strikes by `call_oi` descending in the chain

**1σ daily move**
```
1σ = spot × (iv_atm/100) / √252
```

**Net GEX summary** (for the GEX paragraph)
- Sum `net_gex` across all strikes within ±$200 of spot — sign tells dealer posture
- Identify the gamma flip strike (where cumulative net_gex crosses zero)

If the scraper output is missing `max_pain` or `gex_heatmap`, recompute from the chain inline (formulas in `references/computation-formulas.md`).

---

## Pass B — Analysis & Publish

→ text: "Writing market analysis..."

Produce the following sections (full template in `references/notion-template.md`):

- **Market Analysis** — 4 paragraphs: OI Structure, Put Wall, GEX, Vol Surface. Reference specific strikes and OI numbers.
- **Day Trade Call-to-Action** — Bias, Entry zone, Key Pivot, Stop Logic, Target 1, Target 2, Risk Level
- **Zone narratives** — Support and Resistance, 2-3 sentences each
- **Executive Summary Matrix** — 8-10 rows from deep support to breakout zone

→ text: "Creating Notion sub-page..."

1. `notion-search` confirms parent **Gold Breadth** (`33d51c3f-9aab-8052-a54b-dc74939b48e2`)
2. `notion-create-pages` — empty page, title only:
   - Title: `Gold Breadth — DD MMM YYYY` (today in Asia/Bangkok)
   - Icon: 🥇
   - Parent: `33d51c3f-9aab-8052-a54b-dc74939b48e2`

→ text: "Adding report content..."

3. `notion-update-page` — append the body. Chunk into smaller calls if needed.

→ text: "Done. URL: ..."

Return the Notion page URL.

---

## Constraints

- Do NOT call WebFetch for market data. Cloud egress is blocked at Barchart/Yahoo/etc. — that's why this hybrid exists.
- Do NOT write any local files, PDFs, or attachments. Notion sub-page is the sole deliverable.
- All dates/times in Asia/Bangkok (UTC+7).
- Match the tone of prior sub-pages under "Gold Breadth" — concise, quantitative, no fluff.
