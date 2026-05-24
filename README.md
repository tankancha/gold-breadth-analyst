# gold-breadth-analyst

Daily COMEX gold options breadth report published as a **self-hosted static dashboard**.

**Live: <https://tankancha.github.io/gold-breadth-analyst/>**

## Architecture: GitHub Actions + Claude routine + GitHub Pages

```
┌─────────────────────────────────────┐    ┌────────────────────────────────────┐
│ GITHUB ACTIONS  (.github/workflows) │    │ CLOUD ROUTINE (claude.ai)          │
│ 06:50 Bangkok, weekdays             │    │ 07:00 Bangkok, weekdays            │
├─────────────────────────────────────┤    ├────────────────────────────────────┤
│ 1. scraper/run.py (Playwright)      │    │ 1. git pull                        │
│    → Barchart.com                   │ →  │ 2. Read docs/data/latest.json +    │
│ 2. Mirror to docs/data/YYYY-MM-DD   │       history.json                     │
│ 3. scraper/build_history.py         │    │ 3. Write docs/data/analysis.json   │
│    → docs/data/history.json         │    │    (AI narrative + day-trade CTA)  │
│ 4. Prune to 5 most-recent snapshots │    │ 4. git commit + push               │
│ 5. git commit + push                │    └────────────────────────────────────┘
└─────────────────────────────────────┘
         ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ GITHUB PAGES — docs/ folder served as a static site                        │
│ User opens https://tankancha.github.io/gold-breadth-analyst/               │
│   docs/index.html fetches latest.json + history.json + analysis.json       │
│   Chart.js renders 4 charts + 5-day sparklines + narrative in the browser  │
└────────────────────────────────────────────────────────────────────────────┘
```

Why this shape: the cloud agent's `WebFetch` is blocked by Barchart, Yahoo Finance, and other retail finance sites (HTTP 403, Cloudflare bot detection on Anthropic's IP range). Running Playwright in GitHub Actions sidesteps the block without paying for a market-data feed or running a local PC. The Claude routine focuses on what it's actually good at — writing the narrative — and pushes the result as JSON.

If Cloudflare ever blocks the GHA egress too, set repo secret `SCRAPE_PROXY_URL` to a residential-proxy endpoint — `scraper/scraper.py` routes Playwright through it automatically.

## Files at a glance

| Path | Purpose |
|---|---|
| `scraper/run.py` | GHA entry point — runs the Playwright scrape |
| `scraper/scraper.py` | Barchart scraper + spot-price sanity gate |
| `scraper/build_history.py` | Compiles last-5-days rollup into `docs/data/history.json` |
| `.github/workflows/scrape.yml` | Daily cron: scrape → mirror → history → prune → push |
| `docs/index.html` | Dashboard shell |
| `docs/assets/dashboard.js` | Chart.js wiring + JSON fetch |
| `docs/assets/style.css` | Dark theme styles |
| `docs/data/latest.json` | Today's snapshot (canonical for the website) |
| `docs/data/YYYY-MM-DD.json` | Per-day snapshots, last 5 retained |
| `docs/data/history.json` | 5-day rollup |
| `docs/data/analysis.json` | AI narrative (routine writes) |
| `.claude/skills/gold-breadth-analyst/` | Cloud skill: routine instructions |
| `CLAUDE.md` | Operational gotchas |

## Retention

`docs/data/YYYY-MM-DD.json` is pruned to the 5 most-recent dated snapshots each scrape. Steady-state size: ~1.5 MB of data plus the static site shell.

The legacy local-PC path (`local/push.py` + Windows Task Scheduler) is retained as an emergency manual fallback but is deprecated. See `local/TASK_SCHEDULER_SETUP.md`.

## Notion (deprecated)

Earlier versions of this skill published to a Notion sub-page. That path is retired — the dashboard replaces it. The Notion parent page (`33d51c3f-9aab-8052-a54b-dc74939b48e2`) is orphaned and safe to delete manually.
