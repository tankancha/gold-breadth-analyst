# Notion Page Template

Use this exact structure (Notion-flavored Markdown) for `notion-update-page`.

```
## 📊 GC [SYMBOL] [LABEL] Options Breadth Summary — [Mon DD, YYYY]

> **Data note:** [1-2 sentences: data source freshness from `scraped_at`, spot, max pain, key call/put walls]

---
## Market Snapshot
<table header-row="true">
<tr><td>Metric</td><td>Value</td><td>Signal</td></tr>
<tr><td>GC Spot</td><td>**$[SPOT]**</td><td>[day change $ / %]</td></tr>
<tr><td>Futures Change</td><td>**$[CHG]**</td><td>[bullish/bearish context]</td></tr>
<tr><td>ATM IV</td><td>**[IV]%**</td><td>[vs baseline]</td></tr>
<tr><td>Vol Settle</td><td>**[VS]%**</td><td>[direction vs prior]</td></tr>
<tr><td>Volume</td><td>**[V] contracts**</td><td>[intraday split]</td></tr>
<tr><td>P/C OI Ratio</td><td>**[PC]**</td><td>[interpretation]</td></tr>
<tr><td>Max Pain</td><td>**$[MP]**</td><td>[DTE] DTE — [gravity note]</td></tr>
<tr><td>Total Call OI</td><td>**[COI]**</td><td>Dominant at $[K] ([N])</td></tr>
<tr><td>Total Put OI</td><td>**[POI]**</td><td>Dominant at $[K] ([N])</td></tr>
<tr><td>1σ Daily Move</td><td>**±$[1S]/oz**</td><td>[sizing implication]</td></tr>
</table>

---
## OI Structure & Vol Surface
<table header-row="true">
<tr><td>Strike</td><td>Call OI</td><td>Put OI</td><td>IV (%)</td><td>Observation</td></tr>
[one row per strike from deepest put to deepest call; bold dominant call wall and put wall rows]
</table>

---
## Key OI Zones

### 🟢 Support — [mechanism name]
**Strikes: $[S1] – $[S2]**
[narrative — 2-3 sentences]

**Action:** [entry | stop | target | sizing]

---
### 🔴 Resistance — [mechanism name]
**Strikes: $[R1] – $[R2]**
[narrative — 2-3 sentences]

**Critical Trigger:** [level + condition]

---
## Market Analysis
[Paragraph 1 — OI Structure]

[Paragraph 2 — Put Wall]

[Paragraph 3 — GEX]

[Paragraph 4 — Vol Surface]

---
## Day Trade Call to Action
<table header-row="true">
<tr><td>Signal</td><td>Level</td><td>Notes</td></tr>
<tr><td>**Bias**</td><td>**[BIAS]**</td><td>[justification]</td></tr>
<tr><td>**Entry Zone**</td><td>**$[E1]–$[E2]**</td><td>[mechanism + confirmation]</td></tr>
<tr><td>**Key Pivot**</td><td>**$[PIVOT]**</td><td>[significance]</td></tr>
<tr><td>**Stop Logic**</td><td>**$[STOP]**</td><td>[cascade target]</td></tr>
<tr><td>**Target 1**</td><td>$[T1]</td><td>[level type]</td></tr>
<tr><td>**Target 2**</td><td>$[T2]</td><td>[extended target]</td></tr>
<tr><td>**Risk Level**</td><td>**[RISK]**</td><td>[IV context + sizing %]</td></tr>
</table>

---
## Executive Summary Matrix
<table header-row="true">
<tr><td>Strike Range</td><td>Observation</td><td>Vol Baseline</td><td>Market Impact</td></tr>
[8-10 rows: deep support → put wall → put support → gamma neutral → max pain → primary res → major call wall → call decay → breakout zone]
</table>

---
## GEX Heatmap (10 Strikes Nearest ATM)
<table header-row="true">
<tr><td>Strike</td><td>Call GEX</td><td>Put GEX</td><td>Net GEX</td><td>Dealer Posture</td></tr>
[one row per strike; values to 1 decimal; LONG GAMMA / SHORT GAMMA labels]
</table>

---
*Generated: [Bangkok date+time] | Data scraped: [scraped_at from JSON] | AI: Claude | Contract: [SYMBOL] [LABEL] | DTE: [DTE] | Max Pain: $[MP] | Call Wall: $[CW] | Put Wall: $[PW]*
```

## Market Impact Labels (Executive Matrix column)

`DEEP SUPPORT` · `PUT WALL` · `PUT SUPPORT` · `GAMMA NEUTRAL` · `MAX PAIN ZONE` · `PRIMARY RES` · `MAJOR CALL WALL` · `CALL DECAY` · `SECONDARY RES` · `BREAKOUT ZONE`

## Style Reference (excerpt from a prior report)

> "GCK26 Sunday overnight futures are printing near $4,787 — down $31 from Friday's $4,818 close — as the market digests weekend geopolitical developments. The critical structural data point: Sunday's overnight low of $4,752.70 probed the max-pain zone ($4,750) and held, validating the GEX support floor that has been building all week. The dominant call-wall cluster at $4,800 (22,150 calls) and $4,850 (25,980 calls — peak OI in the chain) remains firmly in place. With 16 DTE now entering Monday, max pain gravitational pull toward $4,750 has strengthened by one day."

Match this density, specificity, and tone.
