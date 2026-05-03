# Computation Formulas (fallback if scraper output is missing fields)

The upstream scraper normally provides `max_pain` and `gex_heatmap` pre-computed. If they're missing from `data/latest.json`, recompute inline using these formulas.

## Max Pain

For each candidate strike S within ±$400 of spot:
```
pain(S) = Σ [call_oi[x] × max(0, x - S)]  +  Σ [put_oi[x] × max(0, S - x)]
         (sum over every strike x in the chain)
```
The strike with the **minimum** pain is Max Pain. Show the top 8 candidates with their pain values when working it out.

## GEX (10 strikes nearest ATM)

```
net_gex[s] = (call_oi[s] - put_oi[s]) × (iv[s] / 100)² × spot × 0.01
```
- Positive net_gex → dealer **long gamma** (price stabilizer; dampens moves)
- Negative net_gex → dealer **short gamma** (price amplifier; accelerates moves)

Show values to 1 decimal place in the heatmap.

## Net GEX summary (for the analysis paragraph)

- Sum `net_gex` across strikes within ±$200 of spot — sign tells the local dealer posture
- The **gamma flip strike** is where the cumulative `net_gex` crosses zero scanning from low to high strike. Below it, dealers are typically short gamma; above it, long gamma.

## 1σ daily move

```
1σ_daily = spot × (iv_atm / 100) / √252
```

## Support / Resistance zones

- Support: top 3 strikes by `put_oi` descending (the put walls)
- Resistance: top 3 strikes by `call_oi` descending (the call walls)
