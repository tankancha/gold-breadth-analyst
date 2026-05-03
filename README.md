# gold-breadth-analyst

Cloud-agent skill that publishes the daily Gold Options Flow & Volatility Report (COMEX GC) to Notion.

Used by the **Gold Breadth Daily** routine on Claude.ai (runs weekdays at 7:00 AM Asia/Bangkok).

## Architecture: Hybrid

The cloud agent's `WebFetch` is blocked by Barchart, Yahoo Finance, and other retail finance sites (HTTP 403, Cloudflare bot detection on Anthropic's IP range). Direct API access for COMEX gold options requires either a paid feed (Polygon ~$29/mo) or a stateful gateway (IBKR). To avoid both, the report runs as a hybrid:

```
┌─────────────────────────────────────┐    ┌────────────────────────────────────┐
│ LOCAL SCRAPER (PC or VPS)           │    │ CLOUD ROUTINE (claude.ai)          │
│ ~6:50 AM Bangkok, weekdays          │    │ 7:00 AM Bangkok, weekdays          │
├─────────────────────────────────────┤    ├────────────────────────────────────┤
│ 1. Run gold-market-breadth scraper  │    │ 1. git pull this repo              │
│    (Playwright → Barchart.com)      │ →  │ 2. Read data/latest.json           │
│ 2. Write data/latest.json           │    │ 3. Compute zones, GEX summary      │
│ 3. git commit + git push            │    │ 4. Write 4-paragraph analysis      │
└─────────────────────────────────────┘    │ 5. Publish Notion sub-page         │
                                            └────────────────────────────────────┘
```

Local scraper code lives in the user's existing `gold-market-breadth.skill` (Playwright + Flask). The wrapper script that runs the scraper and pushes to this repo is in their project folder, not committed here.

## Skill location

`.claude/skills/gold-breadth-analyst/SKILL.md`

## Data file

`data/latest.json` — written by the local scraper. Schema matches `cached_data.json` from the upstream scraper (spot, chain, max_pain, gex_heatmap, etc.). The cloud agent reads this file and treats it as the day's source of truth.

## Output

A Notion sub-page under the parent **Gold Breadth** page. No local files written by the cloud side.
