"""Build docs/data/history.json — a 5-day rollup of key metrics from per-day snapshots.

Scans docs/data/YYYY-MM-DD.json files (date-stamped per-day scrapes), takes the
most recent 5, and produces a single history.json that the dashboard reads
client-side to render sparklines and the "what changed" table.

This script is intentionally dependency-free (stdlib only) so it can run in any
GHA Python environment without extra installs.

Run:
    python scraper/build_history.py
        [--data-dir docs/data]
        [--out docs/data/history.json]
        [--max-days 5]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")
RESERVED = {"latest.json", "history.json", "analysis.json"}


def load_snapshot(path: Path) -> dict | None:
    """Read one per-day JSON snapshot. Returns None on parse error."""
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"  WARN: could not read {path.name}: {e}", file=sys.stderr)
        return None


def summarize(date: str, snap: dict) -> dict:
    """Reduce a full scrape snapshot to the daily summary the dashboard plots."""
    chain = snap.get("chain") or []
    spot = snap.get("spot")
    max_pain = snap.get("max_pain")

    # Top put / call wall = strike with largest put_oi / call_oi
    put_wall = max(
        (r for r in chain if r.get("put_oi")),
        key=lambda r: r.get("put_oi", 0),
        default=None,
    )
    call_wall = max(
        (r for r in chain if r.get("call_oi")),
        key=lambda r: r.get("call_oi", 0),
        default=None,
    )

    # GEX sign — sum net_gex over strikes within ±20% of spot, fallback to all
    gex_heatmap = snap.get("gex_heatmap") or []
    if spot:
        windowed = [
            g for g in gex_heatmap
            if g.get("strike") and spot * 0.8 <= g["strike"] <= spot * 1.2
        ]
    else:
        windowed = gex_heatmap
    total_gex = sum((g.get("net_gex") or 0) for g in windowed)
    gex_sign = "positive" if total_gex >= 0 else "negative"

    # Gamma flip: cumulative net GEX crossing zero (low→high)
    flip = None
    if windowed:
        sorted_gex = sorted(windowed, key=lambda g: g["strike"])
        cum = 0.0
        for g in sorted_gex:
            prev = cum
            cum += g.get("net_gex") or 0
            if (prev <= 0 < cum) or (prev >= 0 > cum):
                flip = g["strike"]
                break

    return {
        "date": date,
        "spot": spot,
        "max_pain": max_pain,
        "pc_oi_ratio": snap.get("pc_oi_ratio"),
        "atm_iv": snap.get("iv_atm"),
        "total_call_oi": snap.get("total_call_oi"),
        "total_put_oi": snap.get("total_put_oi"),
        "total_call_vol": snap.get("total_call_vol"),
        "total_put_vol": snap.get("total_put_vol"),
        "put_wall": put_wall["strike"] if put_wall else None,
        "put_wall_oi": put_wall.get("put_oi") if put_wall else None,
        "call_wall": call_wall["strike"] if call_wall else None,
        "call_wall_oi": call_wall.get("call_oi") if call_wall else None,
        "gex_sign": gex_sign,
        "gex_total_window": round(total_gex, 4),
        "gex_flip_strike": flip,
        "scraped_at": snap.get("scraped_at"),
        "symbol": snap.get("symbol"),
    }


def deltas(days: list[dict]) -> dict:
    """Cross-day deltas: first→last spot, max-pain drift, IV change, wall migrations."""
    if len(days) < 2:
        return {}
    first, last = days[0], days[-1]

    def diff(key):
        a, b = first.get(key), last.get(key)
        return round(b - a, 4) if a is not None and b is not None else None

    return {
        "spot_change": diff("spot"),
        "max_pain_drift": diff("max_pain"),
        "iv_change_pp": diff("atm_iv"),
        "pc_oi_change": diff("pc_oi_ratio"),
        "put_wall_migration": [d.get("put_wall") for d in days],
        "call_wall_migration": [d.get("call_wall") for d in days],
        "max_pain_path": [d.get("max_pain") for d in days],
        "spot_path": [d.get("spot") for d in days],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default="docs/data", help="Directory of per-day JSON snapshots")
    ap.add_argument("--out", default="docs/data/history.json", help="Output history file")
    ap.add_argument("--max-days", type=int, default=5, help="Keep at most N most recent days")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    out = Path(args.out)

    if not data_dir.is_dir():
        print(f"ERROR: data dir not found: {data_dir}", file=sys.stderr)
        sys.exit(1)

    # Collect date-stamped files only.
    candidates = []
    for p in data_dir.iterdir():
        if p.name in RESERVED:
            continue
        m = DATE_RE.match(p.name)
        if not m:
            continue
        candidates.append((m.group(1), p))

    if not candidates:
        print("  No date-stamped snapshots found — writing empty history.")
        out.write_text(json.dumps({"days": [], "deltas": {}}, indent=2), encoding="utf-8")
        return

    # Sort by date, keep most recent N
    candidates.sort(key=lambda x: x[0])
    candidates = candidates[-args.max_days:]

    days = []
    for date, path in candidates:
        snap = load_snapshot(path)
        if not snap:
            continue
        days.append(summarize(date, snap))

    payload = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "window_days": len(days),
        "days": days,
        "deltas": deltas(days),
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"  Wrote {out} ({len(days)} day{'s' if len(days) != 1 else ''})")


if __name__ == "__main__":
    main()
