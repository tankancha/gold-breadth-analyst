# CLAUDE.md — gold-breadth-analyst

Operational notes for any Claude session working on this repo. Read before changing anything.

## What this repo is

A daily COMEX gold options breadth report, published as a **self-hosted static dashboard** on GitHub Pages.

**Live URL: <https://tankancha.github.io/gold-breadth-analyst/>**

Architecture:

```
GitHub Actions (06:50 BKK weekdays)              Claude Routine (07:00 BKK weekdays)
.github/workflows/scrape.yml                      trig_01Ci8KoPvSWrSDNQZnG41CnH
  ├─ scraper/run.py  → data/latest.json             ├─ git pull
  │   └─ Playwright → Barchart                      ├─ read docs/data/latest.json + history.json
  ├─ mirror to docs/data/YYYY-MM-DD.json            ├─ write docs/data/analysis.json
  ├─ scraper/build_history.py → history.json        │   (today_summary, 5-day thesis,
  ├─ prune to 5 most-recent dated snapshots         │    what_changed, prediction, day_trade_cta)
  └─ commit + push  ──────────────────────────►     └─ git commit + push
                                                       (GH Pages auto-redeploys)

User opens https://tankancha.github.io/gold-breadth-analyst/
  → docs/index.html fetches latest.json + history.json + analysis.json
  → Chart.js renders 4 charts + 5-day sparklines + narrative live in the browser
```

**No Notion.** The old Notion publication path was retired — the cloud routine now writes a JSON file, not a Notion page. The Notion parent page (`33d51c3f-9aab-8052-a54b-dc74939b48e2`) is orphaned and safe to delete manually.

## Gotchas (the non-obvious stuff)

1. **The producer is GitHub Actions, not the local PC.** `local/push.py` and `local/push.bat` exist only as an emergency manual fallback. The Windows Task Scheduler entry "Gold Breadth Local Scraper" must stay **disabled** — if it fires it will race the GHA run and produce duplicate commits.

2. **The canonical scraper is `scraper/scraper.py` (committed).** A copy at `local/skill/gold-market-breadth/scripts/scraper.py` is gitignored (everything under `local/` is). If anyone re-runs `local/setup.py` it re-extracts the skill bundle and **overwrites that local copy with an unpatched version**. Never edit the gitignored copy; always edit `scraper/scraper.py`.

3. **Spot price comes from put-call parity, not the Barchart DOM.** Barchart's `[data-field='lastPrice']` selector matches a stale/wrong element today (returned $3,752 when real spot was $4,575). The OI-based PCR-crossing fallback is also unreliable — heavy legacy OI at old price levels can fool it. Use `_estimate_spot()`, which medians `strike + call_last - put_last` across ATM strikes. Sanity gate in `_build_output()`: if header.spot disagrees with chain-implied spot by >5%, trust the chain.

4. **Barchart XHR format: split `Call` / `Put` arrays.** As of 2026, the options endpoint returns `{"data": {"Call": [...], "Put": [...]}}` rather than a single per-strike row list. `_merge_split_chain()` merges them by strike. If the chain extraction breaks again, the GHA workflow uploads `scraper/xhr_debug.json` as an artifact (`scrape-debug`) for inspection.

5. **Two copies of `latest.json` exist on purpose.** `data/latest.json` (repo root) is the raw scraper output — preserved for backward compatibility with any tooling still pointing there. `docs/data/latest.json` is the canonical version the website reads. The GHA workflow copies the former to the latter; they always match.

6. **Per-day snapshots live under `docs/data/YYYY-MM-DD.json` and are pruned to the most recent 5.** The prune runs in `.github/workflows/scrape.yml` before commit. `scraper/build_history.py` reads what remains and writes `docs/data/history.json` for the dashboard's 5-day sparklines + history table. Don't manually add files under `docs/data/` without a date-stamped name — anything matching `[0-9]*.json` will be pruned.

7. **The dashboard is a static SPA — no server, no build step.** `docs/index.html` + `docs/assets/dashboard.js` + `docs/assets/style.css` are served raw by GitHub Pages. The page fetches `./data/*.json` with cache-busting query strings (`?v=Date.now()`) so the Pages CDN never serves stale data. To preview locally: `python -m http.server 8000` inside `docs/`, then open `http://localhost:8000/`.

8. **Routine prompt lives in the Claude.ai UI, not the API.** The remote-trigger update API refuses to write `session_request.initial_message` (returns `Extra inputs are not permitted` on update, even though create accepts it). To change the prompt, edit it at <https://claude.ai/routines> → Gold Breadth Daily. Don't try to fight the API.

9. **Repo is intentionally public.** The cloud agent has no GitHub OAuth token in scope, so a private repo returns 404. GitHub Pages on a public repo is also always public (`robots.txt` blocks search engines but the URL is still reachable). Nothing sensitive lives here — the data is free public market data.

10. **playwright-stealth must be `>=2.x`** — the scraper uses the new `Stealth` class API (`from playwright_stealth.stealth import Stealth`), not the legacy `stealth_async()` function. Pinned to `2.0.3` in `scraper/requirements.txt`.

11. **Don't add a Notion call back into the routine.** The Notion MCP connector (`641c2372-6a53-459e-82ca-5feaeb4a6b7f`) is still configured in your Claude.ai workspace but the routine no longer uses it. If you re-introduce Notion publication, also delete the JSON write — the dashboard already covers that role.

12. **Dashboard visual theme follows the Investory design system**, not an ad-hoc palette. Source: `C:\Users\Admin\OneDrive\Claude Code\Investory\DESIGN.md`. The aesthetic is "Devin-style blue-green gradient atmosphere + Stripe-influenced typography & shadows" — brand blue `#1A6FFF` accent on dark `#070D1C` background with a radial-gradient blue glow halo, Geist (via cdnfonts CDN) for prose, JetBrains Mono (Google Fonts) for every financial number with `font-variant-numeric: tabular-nums`. Bullish `#00C896` / bearish `#FF4D6A` are the trading semantic colors. **Puts render bearish red, calls render brand blue** (consistent across all 3 OI/volume/delta charts). When adding new visual elements: lift token names from `docs/assets/style.css` (e.g. `var(--brand-blue)`, `var(--bullish)`, `var(--shadow-card)`) rather than introducing new hex codes. The old short aliases (`--gold`, `--put`, `--call`, `--text`) still exist for back-compat with `dashboard.js` inline strings — keep them mapped to the new values if you re-paint, don't delete them.

## Key identifiers

| Thing | Value |
|---|---|
| Dashboard URL | <https://tankancha.github.io/gold-breadth-analyst/> |
| GitHub repo | `tankancha/gold-breadth-analyst` (public) |
| Routine name | `Gold Breadth Daily` |
| Trigger ID | `trig_01Ci8KoPvSWrSDNQZnG41CnH` |
| Cron (UTC) | `0 0 * * 1-5` (= 07:00 Bangkok weekdays) |
| GHA cron (UTC) | `50 23 * * 0-4` (= 06:50 Bangkok weekdays) |
| Notion parent page | `33d51c3f-9aab-8052-a54b-dc74939b48e2` ("Gold Breadth") — **orphaned, safe to delete** |
| Notion connector UUID | `641c2372-6a53-459e-82ca-5feaeb4a6b7f` — **unused, can stay configured** |

## Common tasks

**Test the scrape end-to-end without waiting for cron:**
```
gh workflow run "Daily Gold Breadth Scrape" --repo tankancha/gold-breadth-analyst --ref main
gh run watch <run_id> --repo tankancha/gold-breadth-analyst
```

**Test the cloud routine end-to-end (uses whatever JSON is currently committed):**
Use the `RemoteTrigger` tool with `action: "run"` and `trigger_id: trig_01Ci8KoPvSWrSDNQZnG41CnH`.

**Inspect today's chain locally:**
```
git pull
python -c "import json; d=json.load(open('docs/data/latest.json')); print('spot=', d['spot'], '| symbol=', d['symbol'], '| chain=', len(d['chain']))"
```

**Preview the dashboard locally before pushing:**
```
cd docs
python -m http.server 8000
# Open http://localhost:8000/
```

**Rebuild history JSON manually (after adding/removing snapshots):**
```
python scraper/build_history.py
```

**If GHA fails:**
Download the `scrape-debug` artifact from the failed run — it contains `debug_screenshot.png`, `debug_page.html`, and `xhr_debug.json` (largest XHR response captured).

## What NOT to do

- Don't edit `local/skill/gold-market-breadth/scripts/scraper.py` — it's gitignored and gets overwritten by setup.py.
- Don't re-enable the Windows Task Scheduler entry while GHA is also running.
- Don't try to update the routine prompt via API — edit it in the Claude.ai UI.
- Don't make the repo private — GH Pages would stop serving (without a paid plan) and the cloud agent would 404 on `git pull`.
- Don't trust `header.spot` from Barchart blindly; always cross-check against the put-call-parity chain estimate.
- Don't drop files into `docs/data/` with a `YYYY-MM-DD.json` name unless they really are date-keyed snapshots — the prune step will eat anything older than the 5 most recent.
- Don't re-add Notion publication back into the routine without removing the JSON write. Pick one output target.
