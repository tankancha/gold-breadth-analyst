# Cowork Scheduling Guide — Gold Market Breadth

## Overview

This guide covers running the Gold Market Breadth report on a schedule
in Claude Cowork, so fresh reports are generated automatically during
COMEX gold trading hours without manual intervention.

---

## Architecture for Scheduled Runs

```
Cowork Scheduler
     │
     │  every 15 min (market hours)
     ▼
POST http://localhost:5050/api/refresh    ← trigger new scrape
     │
     │  after scrape completes (~45-90s)
     ▼
GET  http://localhost:5050/api/gold-options  ← fetch data payload
     │
     ▼
Save report / send notification / update dashboard
```

The server must be running before Cowork can trigger refreshes.
Start it once and leave it running:
```bash
python scripts/start_server.py &
```

---

## Cowork Task Definitions

### Task 1: Ensure server is running (run once at startup)

```
Name: gold-options-server-start
Type: shell
Command: python /path/to/gold-market-breadth/scripts/start_server.py
Run: once at workflow start
```

### Task 2: Scheduled data refresh (market hours only)

```
Name: gold-options-refresh
Type: http
Method: POST
URL: http://localhost:5050/api/refresh
Body: {"expiry": "auto"}
Schedule: */15 * * * 1-5   (every 15 min, Mon-Fri)
Condition: only when market_open == true (check /api/status first)
```

### Task 3: Generate and save report

```
Name: gold-options-save-report
Type: shell
Command: python /path/to/gold-market-breadth/scripts/run_report.py --out ./reports/$(date +%Y-%m-%d)
Schedule: 0 9,12,15,17 * * 1-5   (4x daily at key market times CT)
```

---

## Full Cowork Workflow Script

Save as `cowork_gold_workflow.py` and register with Cowork:

```python
"""
cowork_gold_workflow.py
Gold Market Breadth — Cowork scheduled workflow
"""

import requests
import time
from datetime import datetime, timezone
from pathlib import Path
import zoneinfo
import subprocess
import json

API_BASE    = "http://localhost:5050"
REPORT_DIR  = Path("./reports")
SKILL_DIR   = Path("/path/to/gold-market-breadth")

CT = zoneinfo.ZoneInfo("America/Chicago")

def market_is_open() -> bool:
    """COMEX gold market hours check."""
    now = datetime.now(timezone.utc).astimezone(CT)
    wd, hour = now.isoweekday(), now.hour
    if wd == 5 and hour >= 16: return False  # Fri after 4PM CT
    if wd == 6:                 return False  # Saturday
    if wd == 7 and hour < 17:   return False  # Sunday before 5PM CT
    return True

def server_is_alive() -> bool:
    try:
        r = requests.get(f"{API_BASE}/api/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False

def trigger_refresh(expiry: str = None) -> dict:
    body = {"expiry": expiry} if expiry else {}
    r = requests.post(f"{API_BASE}/api/refresh",
                      json={"sync": True, **body},
                      timeout=120)
    return r.json()

def fetch_data() -> dict:
    r = requests.get(f"{API_BASE}/api/gold-options", timeout=30)
    return r.json()

def save_report(data: dict, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    # Save JSON
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    (out_dir / f"gold_data_{ts}.json").write_text(json.dumps(data, indent=2))
    # Generate HTML via run_report.py
    subprocess.run([
        "python", str(SKILL_DIR / "scripts" / "run_report.py"),
        "--out", str(out_dir)
    ], check=True)

def run_scheduled_job():
    """Main entry point called by Cowork scheduler."""
    print(f"[{datetime.now(CT).strftime('%Y-%m-%d %H:%M CT')}] Gold Market Breadth job starting")

    if not market_is_open():
        print("Market closed — skipping scrape")
        return {"status": "skipped", "reason": "market_closed"}

    if not server_is_alive():
        print("Server not running — starting...")
        subprocess.Popen([
            "python", str(SKILL_DIR / "scripts" / "start_server.py")
        ])
        time.sleep(5)  # give server time to boot

    print("Triggering data refresh...")
    result = trigger_refresh()
    print(f"Refresh result: chain_length={result.get('chain_length', 0)}")

    data = fetch_data()
    out_dir = REPORT_DIR / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    save_report(data, out_dir)

    print(f"Report saved to {out_dir}")
    return {
        "status": "ok",
        "chain_length": len(data.get("chain", [])),
        "max_pain": data.get("max_pain"),
        "spot": data.get("spot"),
        "report_dir": str(out_dir),
    }

if __name__ == "__main__":
    result = run_scheduled_job()
    print(result)
```

---

## Recommended Schedule

| Time (CT) | Action | Reason |
|---|---|---|
| 17:00 Sun | Start server | Globex open |
| Every 15 min | POST /api/refresh | Keep data fresh |
| 08:20 Mon-Fri | Full report save | Pre-open snapshot |
| 09:30 Mon-Fri | Full report save | NY open |
| 12:00 Mon-Fri | Full report save | Midday snapshot |
| 15:55 Mon-Fri | Full report save | Pre-close snapshot |
| 16:05 Fri | Shutdown or standby | Weekend closure |

---

## Checking Schedule Health

```bash
# Server status
curl http://localhost:5050/api/status | python -m json.tool

# Last 10 scrape results
curl "http://localhost:5050/api/history?n=10" | python -m json.tool

# Force a manual refresh
curl -X POST http://localhost:5050/api/refresh \
     -H "Content-Type: application/json" \
     -d '{"sync": true}'
```

---

## Notifications (Optional)

Add to `run_scheduled_job()` after saving the report:

```python
# Send to Slack
import requests as req
req.post(
    os.environ["SLACK_WEBHOOK_URL"],
    json={
        "text": (
            f"*Gold Options Report* — {datetime.now(CT).strftime('%H:%M CT')}\n"
            f"Spot: ${data.get('spot', '—')} | "
            f"Max Pain: ${data.get('max_pain', '—')} | "
            f"P/C OI: {data.get('pc_oi_ratio', '—')} | "
            f"IV ATM: {data.get('iv_atm', '—')}%\n"
            f"Chain: {len(data.get('chain', []))} strikes | "
            f"Method: {data.get('extraction_method', '—')}"
        )
    }
)
```

---

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `GOLD_SERVER_PORT` | API server port | 5050 |
| `GOLD_REPORT_DIR` | Where to save reports | `./reports` |
| `GOLD_SKILL_DIR` | Path to skill folder | auto-detected |
| `SLACK_WEBHOOK_URL` | Slack notification | not set |
| `GOLD_EXPIRY` | Force specific expiry | auto (front-month) |
