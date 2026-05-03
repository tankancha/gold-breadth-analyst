# API Reference — Gold Market Breadth Server

Base URL: `http://localhost:5050`

---

## GET /api/gold-options

Full options data payload. Scrapes if cache is stale or empty.

**Query parameters**

| Param | Values | Description |
|---|---|---|
| `force` | `0` / `1` | Force immediate re-scrape before responding |
| `expiry` | e.g. `jun-26` | Override front-month expiry selection |
| `compact` | `0` / `1` | Omit `gex_heatmap` array to reduce payload size |

**Response (200)**
```json
{
  "symbol":          "GCM26",
  "spot":            4702.0,
  "future_chg":      -111.4,
  "volume":          186430,
  "iv_atm":          33.68,
  "vol_settle":      42.24,
  "vol_chg":         -0.02,
  "intraday_call":   928,
  "intraday_put":    719,
  "total_call_oi":   178313,
  "total_put_oi":    143996,
  "total_call_vol":  2776,
  "total_put_vol":   3967,
  "pc_oi_ratio":     0.81,
  "max_pain":        4650,
  "expiry": {
    "label": "Jun '26",
    "dte":   83,
    "iv":    33.68
  },
  "gex_heatmap": [
    {"strike": 4700, "call_gex": 4.2, "put_gex": -1.8, "net_gex": 2.4}
  ],
  "chain": [
    {
      "strike":    4500,
      "call_oi":   4200,
      "call_vol":  320,
      "call_last": 285.4,
      "call_iv":   null,
      "put_oi":    9800,
      "put_vol":   710,
      "put_last":  12.2,
      "put_iv":    null,
      "iv":        39.5
    }
  ],
  "is_live":           true,
  "data_source":       "barchart.com/playwright",
  "extraction_method": "xhr-intercept",
  "scraped_at":        "2026-04-04T10:15:00Z",
  "_meta": {
    "cache_age_sec":  42,
    "cache_ttl_sec":  900,
    "is_stale":       false,
    "is_scraping":    false,
    "market_open":    true,
    "chain_length":   25,
    "last_error":     null,
    "server_time":    "2026-04-04T10:15:42Z"
  }
}
```

**Response (503)** — no data available
```json
{
  "error":   "No data available",
  "detail":  "Scrape in progress — retry in 30s",
  "is_live": false
}
```

---

## GET /api/chain

Compact endpoint — chain array only. Omits GEX heatmap.

**Response**
```json
{
  "symbol":     "GCM26",
  "spot":       4702.0,
  "max_pain":   4650,
  "expiry":     {"label": "Jun '26", "dte": 83, "iv": 33.68},
  "scraped_at": "2026-04-04T10:15:00Z",
  "chain":      [...]
}
```

---

## GET /api/gex

GEX heatmap only — Gamma Exposure per strike in $M.

- **Positive net_gex** = dealers net short gamma → resistance / sell into rallies
- **Negative net_gex** = dealers net long gamma → support / buy dips

**Response**
```json
{
  "symbol":     "GCM26",
  "spot":       4702.0,
  "scraped_at": "2026-04-04T10:15:00Z",
  "gex": [
    {"strike": 4500, "call_gex": 1.2, "put_gex": -3.4, "net_gex": -2.2},
    {"strike": 4700, "call_gex": 4.2, "put_gex": -1.8, "net_gex": 2.4},
    {"strike": 4800, "call_gex": 8.9, "put_gex": -0.6, "net_gex": 8.3}
  ]
}
```

---

## GET /api/status

Server health, cache state, and scrape diagnostics.

**Response**
```json
{
  "status":            "ok",
  "has_data":          true,
  "cache_age_sec":     842,
  "cache_ttl_sec":     900,
  "is_stale":          false,
  "chain_length":      25,
  "chain_ok":          true,
  "is_scraping":       false,
  "market_open":       true,
  "last_error":        null,
  "scraped_at":        "2026-04-04T10:15:00Z",
  "extraction_method": "xhr-intercept",
  "server_time":       "2026-04-04T10:29:02Z",
  "version":           "2.0"
}
```

---

## GET /api/history

Last N scrape outcomes. Useful for diagnosing intermittent failures.

**Query parameters**

| Param | Default | Description |
|---|---|---|
| `n` | 50 | Number of entries to return |

**Response**
```json
{
  "count": 3,
  "entries": [
    {
      "ts":        "2026-04-04T10:15:00Z",
      "outcome":   "ok",
      "chain_len": 25,
      "elapsed_s": 48.2,
      "method":    "xhr-intercept",
      "error":     ""
    },
    {
      "ts":        "2026-04-04T09:59:00Z",
      "outcome":   "empty_chain",
      "chain_len": 0,
      "elapsed_s": 32.1,
      "method":    "dom-table",
      "error":     ""
    },
    {
      "ts":        "2026-04-04T09:44:00Z",
      "outcome":   "error",
      "chain_len": 0,
      "elapsed_s": 90.5,
      "method":    "",
      "error":     "TimeoutError: Navigation timeout"
    }
  ]
}
```

Outcome values:
- `ok` — successful scrape with valid chain
- `empty_chain` — scrape ran but fewer than 5 strikes returned
- `error` — exception during scrape

---

## POST /api/refresh

Trigger a re-scrape. Returns immediately by default.

**Request body (JSON, optional)**
```json
{
  "expiry": "jun-26",
  "sync":   false
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `expiry` | string | null | Force specific expiry |
| `sync` | boolean | false | If true, block until scrape completes |

**Response (async)**
```json
{
  "status":  "triggered",
  "message": "Scrape started — poll /api/status for progress"
}
```

**Response (sync=true)**
```json
{
  "status":       "done",
  "success":      true,
  "chain_length": 25
}
```

---

## GET /api/health

Minimal liveness probe. Returns `200 ok` as plain text.

Used by process monitors and Cowork health checks.

---

## Response Headers

All JSON endpoints include:

| Header | Example | Description |
|---|---|---|
| `X-Data-Source` | `barchart.com/playwright` | Data origin |
| `X-Chain-Length` | `25` | Number of strikes in response |
| `Cache-Control` | `max-age=843, must-revalidate` | Client cache TTL |

---

## Error Codes

| HTTP Code | Meaning |
|---|---|
| 200 | OK |
| 503 | No data available — server starting up or all scrapes failed |
| 404 | Endpoint not found — see `endpoints` array in response body |
| 500 | Unhandled server error — check `server.log` |
