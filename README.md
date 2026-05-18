# gold-breadth-analyst

Cloud-agent skill that publishes the daily Gold Options Flow & Volatility Report (COMEX GC) to Notion.

Used by the **Gold Breadth Daily** routine on Claude.ai (runs weekdays at 7:00 AM Asia/Bangkok).

## Architecture: Hybrid (GitHub Actions + Claude routine)

The cloud agent's `WebFetch` is blocked by Barchart, Yahoo Finance, and other retail finance sites (HTTP 403, Cloudflare bot detection on Anthropic's IP range). Direct API access for COMEX gold options requires either a paid feed (Polygon ~$29/mo) or a stateful gateway (IBKR). To avoid both, the report runs as a hybrid — but the *producer* is now **GitHub Actions**, not the user's PC:

```
┌─────────────────────────────────────┐    ┌────────────────────────────────────┐
│ GITHUB ACTIONS  (.github/workflows) │    │ CLOUD ROUTINE (claude.ai)          │
│ 06:50 Bangkok, weekdays             │    │ 07:00 Bangkok, weekdays            │
├─────────────────────────────────────┤    ├────────────────────────────────────┤
│ 1. scraper/run.py (Playwright)      │    │ 1. git pull this repo              │
│    → Barchart.com                   │ →  │ 2. Read data/latest.json           │
│ 2. Write data/latest.json           │    │ 3. Compute zones, GEX summary      │
│ 3. git commit + git push            │    │ 4. Write 4-paragraph analysis      │
└─────────────────────────────────────┘    │ 5. Publish Notion sub-page         │
                                            └────────────────────────────────────┘
```

Producer code lives at `scraper/` in this repo and runs on the `ubuntu-latest` GHA runner. If Cloudflare blocks the GHA egress, set repo secret `SCRAPE_PROXY_URL` to a residential-proxy endpoint — `scraper/scraper.py` will route Playwright through it automatically.

The legacy local-PC path (`local/push.py` + Windows Task Scheduler) is retained but deprecated. See `local/TASK_SCHEDULER_SETUP.md` for emergency manual operation.

## Skill location

`.claude/skills/gold-breadth-analyst/SKILL.md`

## Data file

`data/latest.json` — written by the local scraper. Schema matches `cached_data.json` from the upstream scraper (spot, chain, max_pain, gex_heatmap, etc.). The cloud agent reads this file and treats it as the day's source of truth.

## Output

A Notion sub-page under the parent **Gold Breadth** page. No local files written by the cloud side.
