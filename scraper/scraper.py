"""
scraper.py  —  COMEX Gold Options Scraper
==========================================
Fetches per-strike Put/Call OI, intraday volume, IV, Vol Settle,
and aggregate header metrics for the front-month GC options chain.

Extraction strategy waterfall (stops at first success):
  1. XHR intercept  — catches Barchart's own JSON API calls in-flight
  2. DOM table       — parses the rendered Side-by-Side HTML table
  3. __NEXT_DATA__   — Next.js embedded page state JSON
  4. React fiber     — walks the React component tree for state data

Anti-detection:
  - playwright-stealth patches navigator.webdriver + 20 other signals
  - Realistic viewport, locale, timezone, and User-Agent
  - Random sub-second delays between interactions
  - Optional cookie injection from a saved session file

Usage (standalone):
    python scraper.py [expiry]          # e.g. python scraper.py jun-26
    python scraper.py --debug           # headful mode + verbose logging
    python scraper.py --save-cookies    # after manual login, save session

Usage (via server.py):
    from scraper import fetch_gold_options
    data = await fetch_gold_options()
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Page,
    Response,
    TimeoutError as PWTimeout,
)
from playwright_stealth.stealth import Stealth

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
log = logging.getLogger(__name__)

def _configure_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()],
    )

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
HEADLESS         = True
DEBUG            = False
NAV_TIMEOUT_MS   = 90_000
WAIT_TIMEOUT_MS  = 30_000
COOKIES_FILE     = Path("barchart_cookies.json")
DEBUG_SCREENSHOT = Path("debug_screenshot.png")
DEBUG_HTML       = Path("debug_page.html")

GC_OPTIONS_URL   = "https://www.barchart.com/futures/quotes/GC*0/options"
GC_VOL_URL       = "https://www.barchart.com/futures/quotes/GC*0/volatility-greeks"

# Barchart XHR endpoint substrings to intercept
XHR_PATTERNS = [
    "getFuturesOptionsQuotes",
    "getFuturesOptions",
    "getOptionsQuotes",
    "optionChain",
    "/options/",
    "proxies/core-api",
]

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

STEALTH = Stealth(
    navigator_webdriver=True,
    chrome_runtime=False,
    navigator_languages=True,
    navigator_user_agent=True,
    navigator_vendor=True,
    webgl_vendor=True,
    hairline=True,
)


# ═════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

async def fetch_gold_options(
    expiry_override: Optional[str] = None,
    headless: bool = HEADLESS,
    debug: bool = DEBUG,
) -> dict:
    """
    Scrape the front-month COMEX gold options chain from Barchart.com.
    Returns structured dict consumed by the Flask server and HTML report.
    """
    _configure_logging(debug)
    log.info("━" * 55)
    log.info("  COMEX Gold Options Scraper — Playwright")
    log.info("━" * 55)

    async with async_playwright() as pw:
        launch_kwargs = {
            "headless": headless,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--window-size=1440,900",
            ],
        }
        proxy_url = os.environ.get("SCRAPE_PROXY_URL")
        if proxy_url:
            launch_kwargs["proxy"] = {"server": proxy_url}
            log.info(f"  Using proxy: {proxy_url.split('@')[-1]}")
        browser = await pw.chromium.launch(**launch_kwargs)

        context = await _build_context(browser)
        page = await context.new_page()
        await STEALTH.apply_stealth_async(page)

        # ── XHR intercept ─────────────────────────────────────────────
        xhr_bucket: dict[str, str] = {}
        page.on("response", lambda r: asyncio.create_task(_capture_xhr(r, xhr_bucket)))

        # ── Navigate ─────────────────────────────────────────────────
        log.info(f"→ {GC_OPTIONS_URL}")
        loaded = await _navigate(page, GC_OPTIONS_URL)
        if not loaded:
            log.error("Navigation failed")
            await _save_debug(page)
            await browser.close()
            return _empty_result()

        log.info(f"  Title: {await page.title()}")
        await _human_pause(1.5, 3.0)

        # ── Select expiry ─────────────────────────────────────────────
        expiry_info = await _select_expiry(page, expiry_override)
        log.info(f"  Expiry: {expiry_info['label']} ({expiry_info['dte']} DTE)")

        await _human_pause(2.0, 4.0)

        # ── Trigger full chain load ───────────────────────────────────
        await _scroll_table_into_view(page)
        await _click_show_all(page)
        await _human_pause(1.5, 2.5)

        # ── Extract chain — waterfall ─────────────────────────────────
        chain, method = await _extract_chain_waterfall(page, xhr_bucket)
        log.info(f"  Chain: {len(chain)} strikes via [{method}]")

        # ── Enrich with IV if missing ─────────────────────────────────
        if chain and not any(r.get("iv") for r in chain):
            iv_map = await _fetch_iv_from_greeks_tab(context)
            if iv_map:
                for r in chain:
                    if r["strike"] in iv_map:
                        r["iv"] = iv_map[r["strike"]]
                log.info(f"  IV enriched: {len(iv_map)} strikes")

        # ── Header metrics ────────────────────────────────────────────
        header = await _extract_header(page, expiry_info)

        await page.screenshot(path=str(DEBUG_SCREENSHOT))
        log.info(f"  Screenshot → {DEBUG_SCREENSHOT}")

        await browser.close()

    result = _build_output(header, expiry_info, chain, method)
    _log_summary(result)
    return result


# ═════════════════════════════════════════════════════════════════════════════
# BROWSER / CONTEXT
# ═════════════════════════════════════════════════════════════════════════════

async def _build_context(browser) -> BrowserContext:
    context = await browser.new_context(
        user_agent=UA,
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        timezone_id="America/Chicago",
        java_script_enabled=True,
        ignore_https_errors=False,
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Dest":  "document",
            "Sec-Fetch-Mode":  "navigate",
            "Sec-Fetch-Site":  "none",
            "Sec-Fetch-User":  "?1",
        },
    )
    if COOKIES_FILE.exists():
        try:
            cookies = json.loads(COOKIES_FILE.read_text())
            await context.add_cookies(cookies)
            log.info(f"  Loaded {len(cookies)} saved cookies")
        except Exception as e:
            log.warning(f"  Cookie load failed: {e}")
    return context


async def _navigate(page: Page, url: str) -> bool:
    for wait_mode in ("networkidle", "domcontentloaded"):
        try:
            resp = await page.goto(url, wait_until=wait_mode, timeout=NAV_TIMEOUT_MS)
            if resp and resp.status < 400:
                return True
            log.warning(f"  HTTP {resp.status if resp else '?'} ({wait_mode})")
        except PWTimeout:
            log.warning(f"  Timeout ({wait_mode}) — retrying")
            await page.wait_for_timeout(5000)
        except Exception as e:
            log.error(f"  Nav error ({wait_mode}): {e}")
    return False


async def _save_debug(page: Page):
    try:
        await page.screenshot(path=str(DEBUG_SCREENSHOT), full_page=True)
        DEBUG_HTML.write_text(await page.content(), encoding="utf-8")
        log.info(f"  Debug saved: {DEBUG_SCREENSHOT}, {DEBUG_HTML}")
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════════════════════
# XHR INTERCEPT  —  Strategy 1
# ═════════════════════════════════════════════════════════════════════════════

async def _capture_xhr(response: Response, bucket: dict):
    url = response.url
    if not any(p in url for p in XHR_PATTERNS):
        return
    if "json" not in response.headers.get("content-type", ""):
        return
    try:
        body = await response.body()
        text = body.decode("utf-8", errors="replace")
        if len(text) > 100 and ("[" in text or "{" in text):
            bucket[url] = text
            log.debug(f"  XHR: {url[:80]}")
    except Exception:
        pass


def _parse_xhr_chain(bucket: dict) -> list[dict]:
    """Try new Barchart format (data.Call + data.Put split lists) first,
    fall back to legacy format (single list with both call+put fields per row)."""
    # --- New format (post-2026 Barchart): {"data": {"Call": [...], "Put": [...]}}
    best_url = ""
    best_total = 0
    best_split = None
    for url, text in bucket.items():
        try:
            obj = json.loads(text)
            d = obj.get("data") if isinstance(obj, dict) else None
            if isinstance(d, dict) and isinstance(d.get("Call"), list) and isinstance(d.get("Put"), list):
                total = len(d["Call"]) + len(d["Put"])
                if total > best_total:
                    best_total = total
                    best_split = (d["Call"], d["Put"])
                    best_url = url
        except Exception:
            continue
    if best_split:
        log.info(f"  XHR chain ({len(best_split[0])} calls, {len(best_split[1])} puts): {best_url[:70]}")
        return _merge_split_chain(*best_split)

    # --- Legacy format fallback
    chain = []
    best_len = 0
    best_url = ""
    for url, text in bucket.items():
        try:
            obj = json.loads(text)
            rows = _find_options_array(obj)
            if rows and len(rows) > best_len:
                best_len = len(rows)
                best_url = url
                chain = rows
        except Exception:
            continue
    if chain:
        log.info(f"  XHR chain (legacy format, {best_len} rows): {best_url[:70]}")
    return [_normalize_xhr_row(r) for r in chain if _is_strike_row(r)]


def _merge_split_chain(calls: list, puts: list) -> list[dict]:
    """Merge separate Call and Put lists into per-strike rows."""
    by_strike: dict[int, dict] = {}

    def _ingest(rows: list, side: str) -> None:
        oi_key = f"{side}_oi"
        vol_key = f"{side}_vol"
        last_key = f"{side}_last"
        for r in rows:
            raw = r.get("raw") or {}
            strike = raw.get("strike") or _coerce_number(r.get("strike"))
            if not strike:
                continue
            try:
                strike_i = int(float(strike))
            except (ValueError, TypeError):
                continue
            if not (1000 < strike_i < 12000):
                continue
            row = by_strike.setdefault(strike_i, {"strike": strike_i})
            oi = raw.get("openInterest") if "openInterest" in raw else _coerce_number(r.get("openInterest"))
            vol = raw.get("volume") if "volume" in raw else _coerce_number(r.get("volume"))
            last = raw.get("lastPrice") if "lastPrice" in raw else _coerce_number(r.get("lastPrice"))
            row[oi_key] = int(oi) if oi else 0
            row[vol_key] = int(vol) if vol else 0
            if last:
                row[last_key] = float(last)

    _ingest(calls, "call")
    _ingest(puts, "put")

    # Fill missing fields and IV (not in this endpoint — leave None for header-level fallback)
    out = []
    for strike in sorted(by_strike.keys()):
        row = by_strike[strike]
        row.setdefault("call_oi", 0)
        row.setdefault("put_oi", 0)
        row.setdefault("call_vol", 0)
        row.setdefault("put_vol", 0)
        row.setdefault("call_iv", None)
        row.setdefault("put_iv", None)
        row.setdefault("iv", None)
        out.append(row)
    return out


def _coerce_number(v):
    """Parse '1,325.00C' or '10' or 'N/A' into a float, or None."""
    if v is None:
        return None
    s = str(v).replace(",", "").rstrip("CPcp").strip()
    if not s or s.upper() in ("N/A", "NA", "-", "UNCH"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _find_options_array(obj, depth: int = 0) -> Optional[list]:
    if depth > 6:
        return None
    if isinstance(obj, list) and len(obj) >= 3:
        if obj and isinstance(obj[0], dict):
            keys = set(obj[0].keys())
            if keys & {"strikePrice", "strike", "callOpenInterest",
                       "putOpenInterest", "callOI", "putOI"}:
                return obj
    if isinstance(obj, dict):
        for k in ("data", "results", "options", "chain", "rows", "quotes"):
            if k in obj:
                r = _find_options_array(obj[k], depth + 1)
                if r:
                    return r
        for v in obj.values():
            r = _find_options_array(v, depth + 1)
            if r:
                return r
    return None


def _is_strike_row(row: dict) -> bool:
    s = row.get("strikePrice") or row.get("strike") or 0
    try:
        return 1000 < float(str(s).replace(",", "")) < 12000
    except (ValueError, TypeError):
        return False


def _normalize_xhr_row(row: dict) -> dict:
    def _f(*keys):
        for k in keys:
            v = row.get(k)
            if v is not None:
                try:
                    return float(str(v).replace(",", "").replace("%", ""))
                except (ValueError, TypeError):
                    pass
        return None

    def _i(*keys):
        v = _f(*keys)
        return int(v) if v is not None else 0

    strike = _f("strikePrice", "strike", "strike_price")
    return {
        "strike":    int(strike) if strike else 0,
        "call_oi":   _i("callOpenInterest", "callOI", "call_oi"),
        "call_vol":  _i("callVolume", "callVol"),
        "call_last": _f("callLastPrice", "callLast"),
        "call_iv":   _f("callImpliedVolatility", "callIV"),
        "put_oi":    _i("putOpenInterest", "putOI", "put_oi"),
        "put_vol":   _i("putVolume", "putVol"),
        "put_last":  _f("putLastPrice", "putLast"),
        "put_iv":    _f("putImpliedVolatility", "putIV"),
        "iv":        _f("impliedVolatility", "iv", "midIV"),
    }


# ═════════════════════════════════════════════════════════════════════════════
# DOM TABLE  —  Strategy 2
# ═════════════════════════════════════════════════════════════════════════════

async def _extract_dom_table(page: Page) -> list[dict]:
    """
    Extract from rendered HTML table using batch JS evaluation.
    Handles both Side-by-Side and Stacked view layouts.
    """
    chain_map: dict[int, dict] = {}
    await _wait_for_table(page)

    rows_data = await page.evaluate("""() => {
        // Find largest table (the options chain)
        const tables = Array.from(document.querySelectorAll('table'));
        const bestTable = tables.reduce((best, t) =>
            t.querySelectorAll('tbody tr').length > (best?.querySelectorAll('tbody tr').length ?? 0) ? t : best
        , null);
        if (!bestTable) return [];

        return Array.from(bestTable.querySelectorAll('tbody tr')).map(row => {
            const cells = Array.from(row.querySelectorAll('td, th'));
            return {
                texts: cells.map(c => (c.getAttribute('data-value') || c.innerText || '').trim()),
                rowAttrs: Object.fromEntries(
                    Array.from(row.attributes)
                        .filter(a => a.name.startsWith('data-'))
                        .map(a => [a.name, a.value])
                ),
                classes: row.className
            };
        });
    }""")

    log.debug(f"  DOM rows: {len(rows_data)}")

    for row in rows_data:
        texts    = [t.replace(",", "").strip() for t in row.get("texts", [])]
        ra       = row.get("rowAttrs", {})
        classes  = row.get("classes", "")

        if len(texts) < 3:
            continue

        # ── Fast path: data-* attributes on the row ────────────────
        if "data-strike" in ra:
            strike = _pf(ra["data-strike"])
            if not strike or not (1000 < strike < 12000):
                continue
            strike = int(strike)
            side   = ra.get("data-type", ra.get("data-option-type", "")).lower()
            oi     = int(_pf(ra.get("data-openinterest", ra.get("data-oi", "0"))) or 0)
            vol    = int(_pf(ra.get("data-volume", "0")) or 0)
            last   = _pf(ra.get("data-last"))
            iv     = _pf(ra.get("data-iv", ra.get("data-impliedvolatility")))

            if strike not in chain_map:
                chain_map[strike] = _empty_strike(strike)
            if "put" in side:
                chain_map[strike].update(put_oi=oi, put_vol=vol, put_last=last)
            else:
                chain_map[strike].update(call_oi=oi, call_vol=vol, call_last=last)
            if iv:
                chain_map[strike]["iv"] = iv
            continue

        # ── Find strike column ─────────────────────────────────────
        strike_idx = None
        for i, t in enumerate(texts):
            v = _pf(t)
            if v and 1000 < v < 12000 and "." not in t[:6]:
                strike_idx = i
                break
        if strike_idx is None:
            continue

        strike = int(_pf(texts[strike_idx]))
        left   = texts[:strike_idx]
        right  = texts[strike_idx + 1:]

        if strike not in chain_map:
            chain_map[strike] = _empty_strike(strike)

        # Detect put/call row (stacked view)
        is_put  = any(t.lower() in ("p", "put") for t in texts)
        is_call = any(t.lower() in ("c", "call") for t in texts)
        # Also check class name
        if "put" in classes.lower():
            is_put = True
        elif "call" in classes.lower():
            is_call = True

        if is_put:
            # Stacked put: left side = [open,high,low,last,chg,vol,oi,prem]
            chain_map[strike]["put_oi"]   = int(_pf(left[-2]) or 0) if len(left) >= 2 else 0
            chain_map[strike]["put_vol"]  = int(_pf(left[-3]) or 0) if len(left) >= 3 else 0
            chain_map[strike]["put_last"] = _pf(left[-5]) if len(left) >= 5 else None
        elif is_call:
            chain_map[strike]["call_oi"]   = int(_pf(left[-2]) or 0) if len(left) >= 2 else 0
            chain_map[strike]["call_vol"]  = int(_pf(left[-3]) or 0) if len(left) >= 3 else 0
            chain_map[strike]["call_last"] = _pf(left[-5]) if len(left) >= 5 else None
        else:
            # Side-by-side: [call_last, call_vol, call_oi, call_prem | STRIKE | put_prem, put_oi, put_vol, put_last]
            if len(left) >= 2:
                chain_map[strike]["call_oi"]   = int(_pf(left[-2]) or 0)
                chain_map[strike]["call_vol"]  = int(_pf(left[-3]) or 0) if len(left) >= 3 else 0
                chain_map[strike]["call_last"] = _pf(left[-4]) if len(left) >= 4 else None
            if len(right) >= 2:
                chain_map[strike]["put_oi"]    = int(_pf(right[1]) or 0)
                chain_map[strike]["put_vol"]   = int(_pf(right[2]) or 0) if len(right) >= 3 else 0
                chain_map[strike]["put_last"]  = _pf(right[3]) if len(right) >= 4 else None

    return list(chain_map.values())


# ═════════════════════════════════════════════════════════════════════════════
# __NEXT_DATA__  —  Strategy 3
# ═════════════════════════════════════════════════════════════════════════════

async def _extract_next_data(page: Page) -> list[dict]:
    try:
        raw = await page.evaluate(
            "() => document.getElementById('__NEXT_DATA__')?.textContent"
        )
        if not raw:
            return []
        rows = _find_options_array(json.loads(raw))
        if rows:
            log.info(f"  __NEXT_DATA__: {len(rows)} rows")
            return [_normalize_xhr_row(r) for r in rows if _is_strike_row(r)]
    except Exception as e:
        log.debug(f"  __NEXT_DATA__ failed: {e}")
    return []


# ═════════════════════════════════════════════════════════════════════════════
# REACT FIBER WALK  —  Strategy 4
# ═════════════════════════════════════════════════════════════════════════════

async def _extract_react_fiber(page: Page) -> list[dict]:
    try:
        raw = await page.evaluate("""() => {
            function isOptionsArray(arr) {
                if (!Array.isArray(arr) || arr.length < 5) return false;
                const k = Object.keys(arr[0] || {});
                return k.some(x => ['strikePrice','callOpenInterest','putOI',
                                    'callOI','putOpenInterest'].includes(x));
            }
            function search(obj, depth) {
                if (depth > 8 || !obj || typeof obj !== 'object') return null;
                if (isOptionsArray(obj)) return obj;
                if (isOptionsArray(obj.data)) return obj.data;
                if (isOptionsArray(obj.results)) return obj.results;
                if (isOptionsArray(obj.options)) return obj.options;
                // Redux / Zustand stores
                for (const key of ['__REDUX_STORE__','__STORE__','pageStore']) {
                    if (window[key]) {
                        try {
                            const s = window[key].getState?.() || window[key];
                            const found = search(s, depth + 1);
                            if (found) return found;
                        } catch(e) {}
                    }
                }
                if (depth < 3) {
                    for (const v of Object.values(obj)) {
                        const found = search(v, depth + 1);
                        if (found) return found;
                    }
                }
                return null;
            }

            // Walk React fiber
            const root = document.querySelector('#root,[data-reactroot],main');
            if (!root) return null;
            const fk = Object.keys(root).find(k =>
                k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance'));
            if (!fk) return search(window, 0) ? JSON.stringify(search(window, 0)) : null;

            let node = root[fk];
            let seen = 0;
            while (node && seen < 600) {
                seen++;
                let ms = node.memoizedState;
                while (ms) {
                    const v = ms.memoizedState ?? ms.queue?.lastRenderedState;
                    if (v) {
                        const found = search(v, 0);
                        if (found) return JSON.stringify(found);
                    }
                    ms = ms.next;
                }
                node = node.child || node.sibling || node.return?.sibling;
            }
            // Last resort: window globals
            const found = search(window, 0);
            return found ? JSON.stringify(found) : null;
        }""")

        if raw:
            obj = json.loads(raw)
            rows = obj if isinstance(obj, list) else _find_options_array(obj)
            if rows:
                log.info(f"  React fiber: {len(rows)} rows")
                return [_normalize_xhr_row(r) for r in rows if _is_strike_row(r)]
    except Exception as e:
        log.debug(f"  React fiber failed: {e}")
    return []


# ═════════════════════════════════════════════════════════════════════════════
# WATERFALL
# ═════════════════════════════════════════════════════════════════════════════

async def _extract_chain_waterfall(
    page: Page, xhr_bucket: dict
) -> tuple[list[dict], str]:
    for strategy, fn, name in [
        (lambda: _parse_xhr_chain(xhr_bucket),  None,                   "xhr-intercept"),
        (None,                                   _extract_dom_table,     "dom-table"),
        (None,                                   _extract_next_data,     "next-data"),
        (None,                                   _extract_react_fiber,   "react-fiber"),
    ]:
        log.info(f"  [{name}]...")
        chain = strategy() if strategy else await fn(page)
        if _chain_ok(chain):
            return _sort_chain(chain), name
    log.warning("  All strategies empty — see debug_screenshot.png")
    return [], "none"


def _chain_ok(chain: list) -> bool:
    valid = [r for r in chain if (r.get("call_oi", 0) + r.get("put_oi", 0)) > 0]
    return len(valid) >= 3


def _sort_chain(chain: list) -> list[dict]:
    return sorted(chain, key=lambda r: r.get("strike", 0))


# ═════════════════════════════════════════════════════════════════════════════
# IV ENRICHMENT
# ═════════════════════════════════════════════════════════════════════════════

async def _fetch_iv_from_greeks_tab(context: BrowserContext) -> dict[int, float]:
    iv_map: dict[int, float] = {}
    page2 = await context.new_page()
    await STEALTH.apply_stealth_async(page2)

    xhr_iv: dict[str, str] = {}
    page2.on("response", lambda r: asyncio.create_task(_capture_xhr(r, xhr_iv)))

    try:
        log.info(f"  → IV tab: {GC_VOL_URL}")
        if not await _navigate(page2, GC_VOL_URL):
            return iv_map
        await page2.wait_for_timeout(3000)

        # From XHR
        chain_iv = _parse_xhr_chain(xhr_iv)
        for r in chain_iv:
            s = r.get("strike")
            iv = r.get("iv") or r.get("call_iv") or r.get("put_iv")
            if s and iv:
                iv_map[int(s)] = float(iv)

        # Fallback: DOM table
        if not iv_map:
            rows = await page2.evaluate("""() => {
                return Array.from(document.querySelectorAll('table tbody tr')).map(r =>
                    Array.from(r.querySelectorAll('td')).map(c =>
                        (c.getAttribute('data-value') || c.innerText || '').trim()
                    )
                );
            }""")
            for texts in rows:
                texts = [t.replace(",", "") for t in texts]
                strike = iv_val = None
                for t in texts:
                    v = _pf(t)
                    if v and 1000 < v < 12000:
                        strike = int(v)
                    elif v and 5 < v < 200 and "%" in t:
                        iv_val = v
                if strike and iv_val:
                    iv_map[strike] = iv_val
    except Exception as e:
        log.warning(f"  IV tab error: {e}")
    finally:
        await page2.close()

    log.info(f"  IV map: {len(iv_map)} strikes")
    return iv_map


# ═════════════════════════════════════════════════════════════════════════════
# EXPIRY SELECTION
# ═════════════════════════════════════════════════════════════════════════════

async def _select_expiry(page: Page, override: Optional[str]) -> dict:
    expiry = {"symbol": "", "label": "Unknown", "dte": None, "iv": None}
    try:
        sel_el = await page.query_selector(
            "select[name='expirationDate'], select.expiration-select, "
            "select[data-testid='expirationSelect'], select.bc-select"
        )
        if sel_el:
            opts = await sel_el.query_selector_all("option")
            if opts:
                target = opts[0]
                if override:
                    for opt in opts:
                        val = (await opt.get_attribute("value") or "").lower()
                        txt = (await opt.inner_text()).lower()
                        if override.lower() in val or override.lower() in txt:
                            target = opt
                            break
                val = await target.get_attribute("value") or ""
                txt = (await target.inner_text()).strip()
                await sel_el.select_option(value=val)
                expiry.update(symbol=val, label=txt)
                await page.wait_for_timeout(2000)
        else:
            tabs = await page.query_selector_all(
                "li.expiry-tab, button[data-expiry], .bc-tab-list li, "
                "[data-testid='expiryTab'], .options-expiry-tab"
            )
            if tabs:
                target = tabs[0]
                if override:
                    for t in tabs:
                        if override.lower() in (await t.inner_text()).lower():
                            target = t
                            break
                await target.click()
                expiry["label"] = (await target.inner_text()).strip()
                await page.wait_for_timeout(2000)

        body = await page.inner_text("body")
        for pat in [r"(\d+)\s*Days?\s*to\s*[Ee]xpiration", r"(\d+)\s*DTE"]:
            m = re.search(pat, body)
            if m:
                expiry["dte"] = int(m.group(1))
                break
        m = re.search(r"Implied\s+Volatility[:\s]+([0-9.]+)\s*%", body, re.I)
        if m:
            expiry["iv"] = float(m.group(1))
        if not expiry["dte"]:
            expiry["dte"] = _estimate_dte_from_label(expiry["label"])
    except Exception as e:
        log.warning(f"  Expiry selection: {e}")
    return expiry


def _estimate_dte_from_label(label: str) -> Optional[int]:
    months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
              "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
    m = re.search(
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*'?(\d{2,4})",
        label, re.I
    )
    if not m:
        return None
    try:
        import datetime as dt
        mon = months[m.group(1).lower()[:3]]
        yr  = int(m.group(2))
        if yr < 100:
            yr += 2000
        exp = dt.date(yr, mon, 25)
        return max(1, (exp - dt.date.today()).days)
    except Exception:
        return None


# ═════════════════════════════════════════════════════════════════════════════
# HEADER METRICS
# ═════════════════════════════════════════════════════════════════════════════

async def _extract_header(page: Page, expiry: dict) -> dict:
    h = {
        "contract": "GCM26", "spot": None, "future_chg": None, "volume": None,
        "total_call_oi": None, "total_put_oi": None, "pc_oi_ratio": None,
        "iv_atm": expiry.get("iv"), "vol_settle": None, "vol_chg": None,
        "intraday_call": None, "intraday_put": None,
    }
    try:
        for sel in ["[data-field='lastPrice']", ".last-price", ".bc-futures-price",
                    "[data-testid='lastPrice']", ".price-last"]:
            el = await page.query_selector(sel)
            if el:
                h["spot"] = _pf(await el.inner_text())
                if h["spot"]:
                    break

        body = await page.inner_text("body")
        pats = {
            "total_call_oi": r"Call Open Interest Total[:\s]+([0-9,]+)",
            "total_put_oi":  r"Put Open Interest Total[:\s]+([0-9,]+)",
            "pc_oi_ratio":   r"Put/Call Open Interest Ratio[:\s]+([0-9.]+)",
            "iv_atm":        r"Implied Volatility[:\s]+([0-9.]+)%",
            "vol_settle":    r"Vol(?:atility)?\s+Settle[:\s]+([0-9.]+)",
            "vol_chg":       r"Vol(?:atility)?\s+Chg[:\s]+([+-]?[0-9.]+)",
            "future_chg":    r"Future\s+Chg[:\s]+([+-]?[0-9.]+)",
            "intraday_call": r"Call[:\s]+([0-9,]+)\s",
            "intraday_put":  r"Put[:\s]+([0-9,]+)\s",
        }
        for k, pat in pats.items():
            if h.get(k) is not None:
                continue
            m = re.search(pat, body, re.I)
            if m:
                h[k] = _pf(m.group(1))

        url = page.url
        m = re.search(r"/(GC[A-Z]\d{2})/", url, re.I)
        if m:
            h["contract"] = m.group(1).upper()
    except Exception as e:
        log.warning(f"  Header extraction: {e}")
    return h


# ═════════════════════════════════════════════════════════════════════════════
# UI HELPERS
# ═════════════════════════════════════════════════════════════════════════════

async def _wait_for_table(page: Page, timeout: int = WAIT_TIMEOUT_MS):
    sels = ["table.bc-table tbody tr", "table.options-table tbody tr",
            "[data-testid='optionsTable'] tr", "table tbody tr td"]
    per = timeout // len(sels)
    for sel in sels:
        try:
            await page.wait_for_selector(sel, timeout=per)
            await page.wait_for_timeout(1500)
            return
        except PWTimeout:
            continue
    log.warning("  Table wait timeout")


async def _click_show_all(page: Page):
    candidates = ["button:has-text('Show All')", "a:has-text('Show All')",
                  "[data-testid='showAllStrikes']"]
    for sel in candidates:
        try:
            el = await page.query_selector(sel)
            if el:
                await el.click()
                log.info("  Clicked 'Show All'")
                await page.wait_for_timeout(2000)
                return
        except Exception:
            continue


async def _scroll_table_into_view(page: Page):
    try:
        await page.evaluate(
            "() => document.querySelector('table')?.scrollIntoView({behavior:'smooth'})"
        )
        await page.mouse.wheel(0, 600)
        await page.wait_for_timeout(800)
        await page.mouse.wheel(0, -200)
    except Exception:
        pass


async def _human_pause(lo: float = 0.5, hi: float = 1.5):
    await asyncio.sleep(random.uniform(lo, hi))


# ═════════════════════════════════════════════════════════════════════════════
# OUTPUT BUILDER + ANALYTICS
# ═════════════════════════════════════════════════════════════════════════════

def _build_output(header: dict, expiry: dict, chain: list, method: str) -> dict:
    chain = [r for r in chain if 1000 < r.get("strike", 0) < 12000]

    # Merge call_iv / put_iv → iv
    for r in chain:
        if not r.get("iv"):
            r["iv"] = r.get("call_iv") or r.get("put_iv")

    total_call_oi  = int(header.get("total_call_oi")  or sum(r.get("call_oi",  0) for r in chain))
    total_put_oi   = int(header.get("total_put_oi")   or sum(r.get("put_oi",   0) for r in chain))
    total_call_vol = sum(r.get("call_vol", 0) for r in chain)
    total_put_vol  = sum(r.get("put_vol",  0) for r in chain)
    pc_oi = header.get("pc_oi_ratio") or (
        round(total_put_oi / total_call_oi, 3) if total_call_oi else None
    )

    spot = header.get("spot") or _estimate_spot(chain)

    return {
        "scraped_at":        datetime.now(timezone.utc).isoformat(),
        "symbol":            header.get("contract", "GCM26"),
        "expiry":            expiry,
        "spot":              spot,
        "future_chg":        header.get("future_chg"),
        "volume":            header.get("volume"),
        "iv_atm":            expiry.get("iv") or header.get("iv_atm"),
        "vol_settle":        header.get("vol_settle"),
        "vol_chg":           header.get("vol_chg"),
        "intraday_call":     header.get("intraday_call"),
        "intraday_put":      header.get("intraday_put"),
        "total_call_oi":     total_call_oi,
        "total_put_oi":      total_put_oi,
        "total_call_vol":    total_call_vol,
        "total_put_vol":     total_put_vol,
        "pc_oi_ratio":       pc_oi,
        "max_pain":          _compute_max_pain(chain),
        "gex_heatmap":       _compute_gex(chain, spot),
        "chain":             chain,
        "is_live":           len(chain) >= 3,
        "data_source":       "barchart.com/playwright",
        "extraction_method": method,
    }


def _compute_max_pain(chain: list) -> Optional[int]:
    if not chain:
        return None
    oi_map = {r["strike"]: r for r in chain}
    strikes = sorted(oi_map.keys())
    min_pain = float("inf")
    mp = strikes[len(strikes)//2]
    for s in strikes:
        pain = sum(
            oi_map[x]["call_oi"] * max(0, x - s) +
            oi_map[x]["put_oi"]  * max(0, s - x)
            for x in strikes
        )
        if pain < min_pain:
            min_pain = pain
            mp = s
    return mp


def _compute_gex(chain: list, spot: Optional[float]) -> list[dict]:
    """Gamma Exposure per strike in $M. Negative = dealer long gamma (support)."""
    if not spot:
        return []
    results = []
    for r in chain:
        s = r["strike"]
        iv = (r.get("iv") or 25) / 100
        T  = 0.25  # approximate
        try:
            d1    = (math.log(spot / s) + 0.5 * iv**2 * T) / (iv * math.sqrt(T))
            gamma = math.exp(-0.5 * d1**2) / (math.sqrt(2*math.pi) * spot * iv * math.sqrt(T))
        except (ValueError, ZeroDivisionError):
            gamma = 0
        scale   = spot**2 * 0.01 * 100 / 1e6
        call_gex = r.get("call_oi", 0) * gamma * scale
        put_gex  = -r.get("put_oi", 0) * gamma * scale
        results.append({
            "strike":   s,
            "call_gex": round(call_gex, 2),
            "put_gex":  round(put_gex, 2),
            "net_gex":  round(call_gex + put_gex, 2),
        })
    return results


def _estimate_spot(chain: list) -> Optional[float]:
    if not chain:
        return None
    s = sorted(chain, key=lambda r: r["strike"])
    for i in range(len(s)-1):
        a, b = s[i], s[i+1]
        if a["call_oi"] and a["put_oi"] and b["call_oi"] and b["put_oi"]:
            if (a["put_oi"]/a["call_oi"]) >= 1.0 >= (b["put_oi"]/b["call_oi"]):
                return (a["strike"] + b["strike"]) / 2
    return s[len(s)//2]["strike"]


def _empty_strike(strike: int) -> dict:
    return {"strike":strike, "call_oi":0, "call_vol":0, "call_last":None,
            "call_iv":None, "put_oi":0, "put_vol":0, "put_last":None,
            "put_iv":None, "iv":None}


def _empty_result() -> dict:
    return {"is_live":False, "chain":[], "symbol":"GCM26",
            "expiry":{"label":"Unknown","dte":None,"iv":None},
            "extraction_method":"failed",
            "scraped_at":datetime.now(timezone.utc).isoformat()}


# ═════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═════════════════════════════════════════════════════════════════════════════

def _pf(s) -> Optional[float]:
    if s is None:
        return None
    try:
        return float(str(s).replace(",","").replace("%","").strip())
    except (ValueError, TypeError):
        return None


def _log_summary(data: dict):
    chain = data.get("chain", [])
    log.info("━"*55)
    log.info(f"  Symbol:   {data.get('symbol')}  |  Method: {data.get('extraction_method')}")
    log.info(f"  Expiry:   {data['expiry']['label']} ({data['expiry']['dte']} DTE)")
    log.info(f"  Spot:     {data.get('spot')}  |  Max Pain: ${data.get('max_pain')}")
    log.info(f"  Call OI:  {data.get('total_call_oi',0):,}  |  Put OI: {data.get('total_put_oi',0):,}")
    log.info(f"  P/C OI:   {data.get('pc_oi_ratio')}  |  IV ATM: {data.get('iv_atm')}%")
    log.info(f"  Chain:    {len(chain)} strikes  |  Live: {data.get('is_live')}")
    log.info("━"*55)


# ═════════════════════════════════════════════════════════════════════════════
# COOKIE SAVER  (run once for persistent login)
# ═════════════════════════════════════════════════════════════════════════════

async def save_session_cookies():
    """Open visible browser, log in manually, save session cookies."""
    print("Opening browser — log into barchart.com then press Enter here.")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx     = await browser.new_context(user_agent=UA)
        page    = await ctx.new_page()
        await page.goto("https://www.barchart.com/login")
        input(">>> Press Enter after logging in ...")
        cookies = await ctx.cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
        print(f"Saved {len(cookies)} cookies → {COOKIES_FILE}")
        await browser.close()


# ═════════════════════════════════════════════════════════════════════════════
# STANDALONE ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--save-cookies" in args:
        asyncio.run(save_session_cookies())
        sys.exit(0)

    headless = "--debug" not in args
    debug    = "--debug" in args
    expiry   = next((a for a in args if not a.startswith("--")), None)

    data  = asyncio.run(fetch_gold_options(
        expiry_override=expiry, headless=headless, debug=debug
    ))
    chain = data.get("chain", [])

    if chain:
        gex = {g["strike"]: g["net_gex"] for g in data.get("gex_heatmap", [])}
        print(f"\n{'Strike':>8}  {'CallOI':>10}  {'PutOI':>10}  {'CVol':>8}  {'PVol':>8}  {'IV':>7}  {'GEX$M':>7}")
        print("─"*72)
        for r in chain:
            iv_s  = f"{r['iv']:.1f}%" if r.get("iv") else "   —"
            gx_s  = f"{gex.get(r['strike'],0):+.1f}" if r["strike"] in gex else "  —"
            print(f"  {r['strike']:>6}  {r['call_oi']:>10,}  {r['put_oi']:>10,}  "
                  f"{r['call_vol']:>8,}  {r['put_vol']:>8,}  {iv_s}  {gx_s}")

    out = Path("gold_options_data.json")
    out.write_text(json.dumps(data, indent=2))
    print(f"\nSaved → {out}  ({len(chain)} strikes, method={data.get('extraction_method')})")
