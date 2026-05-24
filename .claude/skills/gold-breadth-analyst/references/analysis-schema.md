# `docs/data/analysis.json` schema

This is the file the routine writes. The dashboard (`docs/index.html`) fetches it client-side and renders the narrative + day-trade CTA sections. All fields are optional — missing keys just hide their section.

```json
{
  "generated_at": "2026-05-24T07:05:30+07:00",
  "symbol": "GCM26",
  "spot_at_analysis": 4612.8,
  "today_summary": "GCM26 settled $4,612 (+1.79%) Friday after a tariff-driven selloff week. Put-heavy chain (P/C OI 1.33) with strongest GAX floor at $4,500 (4,800 contracts). Max pain $4,650 sits +$37 above settle, exerting gentle upward pull into the final week.",
  "five_day_thesis": "Over the last 5 sessions max pain has drifted from $4,580 to $4,650 (+$70) while spot held the $4,500 put wall on three consecutive tests. GEX flipped from positive to negative on 2026-05-21, signaling regime change from stabilizing to vol-amplifying dealer posture. ATM IV compressed from 19.8% to 18.4% (-1.4pp), making spread sellers favored.",
  "what_changed": [
    "Put wall at $4,500 unchanged 4 of 5 days — strongest GAX floor in current cycle",
    "GEX flipped from positive to negative on 2026-05-21 — vol regime shift",
    "Call wall migrated $4,750 → $4,800 (+$50) — supply zone moved higher",
    "ATM IV compressed 19.8% → 18.4% — premium decay favors spread sellers"
  ],
  "prediction": "Bias cautiously bullish above $4,580. Path of least resistance is mean-reversion toward max pain $4,650, then a test of the $4,700 call concentration. Below $4,500 the negative GEX cascade reactivates — high realized vol regime.",
  "day_trade_cta": {
    "bias": "Cautious Bull",
    "bias_note": "Drift toward max pain $4,650 from settle $4,612. Bias flips bearish below $4,580.",
    "entry_zone": "$4,575–$4,620",
    "entry_note": "Initiate longs on gap-down into the GAX floor / max-pain corridor with volume confirmation.",
    "pivot": "$4,650",
    "pivot_note": "Sustained trade above → target $4,700 then $4,800. Sustained trade below → path opens to $4,550 then $4,500 GAX test.",
    "stop": "$4,550",
    "stop_note": "−1.4% from entry midpoint. Below this the negative GEX cascade activates.",
    "targets": ["$4,700", "$4,800"],
    "target_note": "T1 high call OI, take 50% off. T2 major call wall, exit remaining.",
    "risk_label": "HIGH VOL REGIME",
    "risk_note": "GVZ 19.2 + negative GEX → expect 1.5–2.5% daily range. Reduce size 30–50%."
  }
}
```

## Field rules

- `generated_at` — ISO 8601 with `+07:00` (Asia/Bangkok). Required.
- `today_summary` — 2–4 sentences. Lead with a number.
- `five_day_thesis` — 3–5 sentences focused on *what's different vs 5 days ago*. Reference specific deltas from `docs/data/history.json`.
- `what_changed` — array of single-sentence bullets, ≤ 6 items, each one starts with a noun (the thing that moved).
- `prediction` — 2–3 sentences. State directional bias and the level that invalidates it.
- `day_trade_cta` — object with the fields above. All strings; `targets` is a string array. Numbers should be pre-formatted with `$` and commas so the dashboard can render them as-is.

## Style

Concise. Quantitative. Every claim leads with a specific number (strike, OI count, IV%, GEX magnitude). No disclaimers. No emoji except where unavoidable for clarity. The dashboard renders this verbatim — what you write is what the user sees.
