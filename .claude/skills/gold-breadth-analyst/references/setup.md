# Setup Guide — Gold Market Breadth

## System Requirements

- Python 3.9 or later
- Internet access to barchart.com
- ~300 MB disk (Chromium browser)

---

## Installation

### 1. Install Python packages

```bash
pip install playwright playwright-stealth flask flask-cors requests beautifulsoup4
```

If you get a "system packages" error on Linux:
```bash
pip install playwright playwright-stealth flask flask-cors requests beautifulsoup4 \
    --break-system-packages
```

### 2. Install Chromium browser

```bash
python -m playwright install chromium
```

This downloads ~180 MB and only needs to be done once.

### 3. Verify

```bash
python -c "import playwright, playwright_stealth, flask, flask_cors; print('All OK')"
```

---

## First Run

```bash
# One-shot: scrape + generate report
python scripts/run_report.py

# Or start the live server + open report in browser
python scripts/start_server.py &
open assets/gold_options_report.html
```

---

## Anti-Bot: Save Session Cookies (Recommended)

Barchart.com occasionally serves CAPTCHA to headless browsers. The most reliable solution is to save a logged-in session cookie once:

```bash
python scripts/scraper.py --save-cookies
```

This opens a **visible** Chromium window. Log into barchart.com, then press Enter in the terminal. The session is saved to `barchart_cookies.json` and used automatically on future scrapes.

Session cookies last approximately 30 days before needing renewal.

---

## Virtual Environment (Optional but Recommended)

```bash
python -m venv .venv
source .venv/bin/activate      # macOS / Linux
.venv\Scripts\activate         # Windows

pip install -r requirements.txt
python -m playwright install chromium
```

---

## Requirements File

```
playwright>=1.43.0
playwright-stealth>=1.0.6
flask>=3.0.3
flask-cors>=4.0.1
requests>=2.31.0
beautifulsoup4>=4.12.3
pyyaml>=6.0
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'playwright'`**
```bash
pip install playwright --break-system-packages
```

**`ModuleNotFoundError: No module named 'zoneinfo'`** (Python < 3.9)
```bash
pip install backports.zoneinfo
```
Then edit `scripts/server.py` line with `import zoneinfo` to:
```python
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo
```

**Chromium not found**
```bash
python -m playwright install chromium
```

**Port 5050 already in use**
```bash
python scripts/start_server.py --port 8080
```
Also update `API_BASE` in `assets/gold_options_report.html`:
```js
const API_BASE = 'http://localhost:8080';
```
