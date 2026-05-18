# CLAUDE.md — gold-breadth-analyst

Operational notes for any Claude session working on this repo. Read before changing anything.

## What this repo is

A daily COMEX gold options breadth report. The Claude routine **Gold Breadth Daily** runs at 07:00 Asia/Bangkok on weekdays, reads `data/latest.json` from this repo, computes zones / max pain / GEX / 1σ band, and publishes a Notion sub-page under the "Gold Breadth" parent page.

Architecture:

```
GitHub Actions (06:50 BKK weekdays)              Claude Routine (07:00 BKK weekdays)
.github/workflows/scrape.yml                      trig_01Ci8KoPvSWrSDNQZnG41CnH
  └─ scraper/run.py                                 └─ git pull this repo
     └─ Playwright → Barchart                          └─ read data/latest.json
        └─ commit data/latest.json   ─────────────────► compute + publish to Notion
```

## Gotchas (the non-obvious stuff)

1. **The producer is GitHub Actions, not the local PC.** `local/push.py` and `local/push.bat` exist only as an emergency manual fallback. The Windows Task Scheduler entry "Gold Breadth Local Scraper" must stay **disabled** — if it fires it will race the GHA run and produce duplicate commits.

2. **The canonical scraper is `scraper/scraper.py` (committed).** A copy at `local/skill/gold-market-breadth/scripts/scraper.py` is gitignored (everything under `local/` is). If anyone re-runs `local/setup.py` it re-extracts the skill bundle and **overwrites that local copy with an unpatched version**. Never edit the gitignored copy; always edit `scraper/scraper.py`.

3. **Spot price comes from put-call parity, not the Barchart DOM.** Barchart's `[data-field='lastPrice']` selector matches a stale/wrong element today (returned $3,752 when real spot was $4,575). The OI-based PCR-crossing fallback is also unreliable — heavy legacy OI at old price levels can fool it. Use `_estimate_spot()`, which medians `strike + call_last - put_last` across ATM strikes. Sanity gate in `_build_output()`: if header.spot disagrees with chain-implied spot by >5%, trust the chain.

4. **Barchart XHR format: split `Call` / `Put` arrays.** As of 2026, the options endpoint returns `{"data": {"Call": [...], "Put": [...]}}` rather than a single per-strike row list. `_merge_split_chain()` merges them by strike. If the chain extraction breaks again, the GHA workflow uploads `scraper/xhr_debug.json` as an artifact (`scrape-debug`) for inspection.

5. **Routine prompt lives in the Claude.ai UI, not the API.** The remote-trigger update API refuses to write `session_request.initial_message` (returns `Extra inputs are not permitted` on update, even though create accepts it). To change the prompt, edit it at <https://claude.ai/routines> → Gold Breadth Daily. Don't try to fight the API.

6. **Repo is intentionally public.** The cloud agent has no GitHub OAuth token in scope, so a private repo returns 404. Nothing sensitive lives here — the data is free public market data and the skill is just Markdown formatting instructions. If you ever need secrets, use repo Settings → Secrets and Variables → Actions (encrypted regardless of repo visibility) and reference by name in the workflow.

7. **playwright-stealth must be `>=2.x`** — the scraper uses the new `Stealth` class API (`from playwright_stealth.stealth import Stealth`), not the legacy `stealth_async()` function. Pinned to `2.0.3` in `scraper/requirements.txt`.

## Key identifiers

| Thing | Value |
|---|---|
| GitHub repo | `tankancha/gold-breadth-analyst` (public) |
| Routine name | `Gold Breadth Daily` |
| Trigger ID | `trig_01Ci8KoPvSWrSDNQZnG41CnH` |
| Cron (UTC) | `0 0 * * 1-5` (= 07:00 Bangkok weekdays) |
| GHA cron (UTC) | `50 23 * * 0-4` (= 06:50 Bangkok weekdays) |
| Notion parent page | `33d51c3f-9aab-8052-a54b-dc74939b48e2` ("Gold Breadth") |
| Notion connector UUID | `641c2372-6a53-459e-82ca-5feaeb4a6b7f` |

## Common tasks

**Test the scrape end-to-end without waiting for cron:**
```
gh workflow run "Daily Gold Breadth Scrape" --repo tankancha/gold-breadth-analyst --ref main
gh run watch <run_id> --repo tankancha/gold-breadth-analyst
```

**Test the cloud routine end-to-end (uses whatever data/latest.json is currently committed):**
Use the `RemoteTrigger` tool with `action: "run"` and `trigger_id: trig_01Ci8KoPvSWrSDNQZnG41CnH`.

**Inspect today's chain locally:**
```
git pull
python -c "import json; d=json.load(open('data/latest.json')); print('spot=', d['spot'], '| symbol=', d['symbol'], '| chain=', len(d['chain']))"
```

**If GHA fails:**
Download the `scrape-debug` artifact from the failed run — it contains `debug_screenshot.png`, `debug_page.html`, and `xhr_debug.json` (largest XHR response captured).

## What NOT to do

- Don't edit `local/skill/gold-market-breadth/scripts/scraper.py` — it's gitignored and gets overwritten by setup.py.
- Don't re-enable the Windows Task Scheduler entry while GHA is also running.
- Don't try to update the routine prompt via API — edit it in the Claude.ai UI.
- Don't make the repo private without first wiring up GitHub OAuth on the routine (it will silently 404 on `git pull`).
- Don't trust `header.spot` from Barchart blindly; always cross-check against the put-call-parity chain estimate.
