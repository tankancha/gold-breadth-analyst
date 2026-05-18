"""
GitHub Actions entry point.

Runs the gold options scrape and writes the result to:
  - data/latest.json          (canonical file the cloud Notion routine reads)
  - data/YYYY-MM-DD.json      (Bangkok-dated archive)

No git operations here — the workflow handles `git add/commit/push` after
this script exits 0.

Exit codes:
  0 — success, data written
  1 — scrape failed (no commit will be made; cloud routine will see stale data
       and skip per its staleness rule)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent           # repo/scraper
REPO = HERE.parent                                # repo root
DATA_DIR = REPO / "data"

sys.path.insert(0, str(HERE))
from scraper import fetch_gold_options, _parse_xhr_chain  # type: ignore
import scraper as _scr                                    # type: ignore

BANGKOK = timezone(timedelta(hours=7))


def log(msg: str) -> None:
    print(f"[{datetime.now(BANGKOK).isoformat(timespec='seconds')}] {msg}", flush=True)


def _install_xhr_dump(dump_path: Path) -> None:
    """Patch _parse_xhr_chain so a failed extraction dumps the biggest XHR."""
    original = _scr._parse_xhr_chain

    def patched(bucket):
        result = original(bucket)
        if not result and bucket:
            try:
                largest = max(bucket.items(), key=lambda kv: len(kv[1]))
                dump_path.write_text(largest[1], encoding="utf-8")
                log(f"  XHR dump saved: {dump_path} (URL: {largest[0][:80]})")
            except Exception as exc:
                log(f"  XHR dump failed: {exc}")
        return result

    _scr._parse_xhr_chain = patched


async def _main() -> int:
    log(f"=== run.py start  cwd={Path.cwd()}  repo={REPO} ===")
    DATA_DIR.mkdir(exist_ok=True)

    # Run scraper from inside scraper/ so its side-effect files
    # (debug_screenshot.png, etc.) land here, not at repo root.
    os.chdir(HERE)
    _install_xhr_dump(HERE / "xhr_debug.json")

    try:
        data = await fetch_gold_options(headless=True, debug=False)
    except Exception as exc:
        log(f"FAIL: scrape raised {type(exc).__name__}: {exc}")
        return 1

    chain_n = len(data.get("chain", []))
    method = data.get("extraction_method", "?")
    log(f"  Extracted {chain_n} strikes via [{method}]  "
        f"symbol={data.get('symbol')}  spot={data.get('spot')}")

    if chain_n < 5:
        log(f"FAIL: chain has only {chain_n} strikes — refusing to write")
        return 1

    today_bkk = datetime.now(BANGKOK).strftime("%Y-%m-%d")
    payload = json.dumps(data, indent=2, default=str)

    (DATA_DIR / "latest.json").write_text(payload, encoding="utf-8")
    (DATA_DIR / f"{today_bkk}.json").write_text(payload, encoding="utf-8")
    log(f"  Wrote data/latest.json and data/{today_bkk}.json")
    log("=== run.py done ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
