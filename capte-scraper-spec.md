# CAPTE Financial Fact Sheet Scraper — Spec for Claude Code

## Goal
Scrape tuition (total program cost) and program length (months) for every accredited DPT program
from CAPTE's public directory and each program's mandatory Financial Fact Sheet. Output a clean
CSV ready to import into the HealthCareer database.

---

## Background: Why This Works

CAPTE (Commission on Accreditation in Physical Therapy Education) **mandates** that every accredited
DPT and PTA program publish a standardized Financial Fact Sheet on their website, accessible within
one click of their program homepage, updated annually by October 15. This means:

- Data format is standardized (same fields, same labels across all programs)
- No login required
- ~100% coverage is achievable
- Legally clean: factual data, publicly mandated, no authentication bypassed

---

## Data Sources

### Source 1 — CAPTE Program Directory (program list + homepage URLs)
```
https://www.capteonline.org/find-pt-programs/
```
This is the authoritative list of all accredited programs. Each entry includes:
- Program name
- Institution name
- State
- Degree type (DPT / PTA)
- Program status (accredited / on probation / developing)
- Link to program's accreditation page (which links to their website)

### Source 2 — Each Program's Financial Fact Sheet
Located on each program's own university website, linked from their accreditation page.
The fact sheet is a standardized PDF or HTML page. Key fields to extract:
- **Total program cost** (tuition + fees, sometimes broken out by resident/non-resident)
- **Program length** in months or semesters (convert all to months)
- **First professional year cost** (secondary target if total not listed)
- Last updated date (for staleness tracking)

---

## Output Schema

```csv
program_id,institution_name,program_name,state,degree_type,accreditation_status,
program_url,fact_sheet_url,tuition_resident,tuition_nonresident,tuition_total,
program_length_months,tuition_source_label,last_updated,scrape_date,scrape_status,scrape_notes
```

| Field | Type | Notes |
|---|---|---|
| program_id | string | Slug: `institution-state-degreetype` e.g. `usc-ca-dpt` |
| institution_name | string | Canonical name from CAPTE |
| program_name | string | Full program name |
| state | string | 2-letter code |
| degree_type | enum | `DPT` or `PTA` |
| accreditation_status | enum | `accredited`, `probation`, `developing` |
| program_url | url | Program homepage |
| fact_sheet_url | url | Direct URL to Financial Fact Sheet |
| tuition_resident | integer | In-state annual or total (cents, no decimals) |
| tuition_nonresident | integer | Out-of-state if available, else null |
| tuition_total | integer | **Primary field.** Total program cost if listed, else null |
| program_length_months | integer | Converted to months. 3 semesters = 18mo, 3 years = 36mo |
| tuition_source_label | string | Exact label scraped e.g. "Total Program Cost" |
| last_updated | date | From fact sheet if present, else null |
| scrape_date | datetime | ISO 8601, UTC |
| scrape_status | enum | `success`, `fact_sheet_not_found`, `parse_failed`, `timeout`, `blocked` |
| scrape_notes | string | Free text. E.g. "PDF required manual parse", "resident only listed" |

---

## Architecture

```
run_scraper.py              ← CLI entrypoint with flags
├── capte_directory.py      ← Step 1: scrape program list from CAPTE
├── fact_sheet_finder.py    ← Step 2: find fact sheet URL on each program page
├── fact_sheet_parser.py    ← Step 3: extract tuition + length from fact sheet
├── db.py                   ← SQLite state store for retryability
├── output.py               ← Write final CSV
└── config.py               ← Rate limits, headers, paths
```

---

## Step-by-Step Implementation

### Step 1 — Scrape CAPTE Directory

**File:** `capte_directory.py`

Use `requests` + `BeautifulSoup`. The CAPTE find-programs page uses a filterable table.
Check if it loads via static HTML or requires JS (use `curl` first to verify).

If static HTML:
```python
import requests
from bs4 import BeautifulSoup

CAPTE_URL = "https://www.capteonline.org/find-pt-programs/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HealthCareerResearch/1.0; +https://healthcareer.com/about)"
}

resp = requests.get(CAPTE_URL, headers=HEADERS, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")
# Parse program table rows → list of dicts
```

If JS-rendered (likely): use `playwright` in headless mode:
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(CAPTE_URL)
    page.wait_for_selector("table.programs")  # adjust selector
    html = page.content()
    # parse with BeautifulSoup
```

**Output:** List of dicts saved to SQLite `programs` table.

**Validation:** Assert count is between 280–350 (known range ~299 DPT programs).
If count is outside range, raise an error and stop — something is wrong with the parse.

---

### Step 2 — Find Financial Fact Sheet URL

**File:** `fact_sheet_finder.py`

For each program, visit their program homepage and find the fact sheet link.

```python
FACT_SHEET_PATTERNS = [
    "financial fact sheet",
    "financial information",
    "fact sheet",
    "program costs",
    "tuition and fees",
    "cost of attendance",
]

def find_fact_sheet_url(program_url: str) -> str | None:
    resp = requests.get(program_url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    
    for link in soup.find_all("a", href=True):
        link_text = link.get_text(strip=True).lower()
        href = link["href"]
        if any(pattern in link_text for pattern in FACT_SHEET_PATTERNS):
            return urljoin(program_url, href)
    
    # Secondary: check navigation menus and footer
    # Secondary: search for PDF links containing "fact" or "financial"
    for link in soup.find_all("a", href=True):
        href = link["href"].lower()
        if "fact" in href or "financial" in href or "tuition" in href:
            return urljoin(program_url, link["href"])
    
    return None  # triggers scrape_status = "fact_sheet_not_found"
```

**Flag programs where fact sheet not found** — these need manual review, not silent failure.

---

### Step 3 — Parse Financial Fact Sheet

**File:** `fact_sheet_parser.py`

Fact sheets come in two formats:

#### 3a — HTML fact sheet
```python
import re

TUITION_PATTERNS = [
    r"total program cost[:\s]+\$?([\d,]+)",
    r"total tuition[:\s]+\$?([\d,]+)",
    r"program tuition[:\s]+\$?([\d,]+)",
    r"estimated total cost[:\s]+\$?([\d,]+)",
    r"total cost of program[:\s]+\$?([\d,]+)",
]

LENGTH_PATTERNS = [
    r"program length[:\s]+([\d]+)\s*months?",
    r"duration[:\s]+([\d]+)\s*months?",
    r"([\d]+)[- ]month program",
    r"([\d]+)\s*semesters?",   # → multiply by 6
    r"([\d]+)\s*years?",        # → multiply by 12
]

def parse_html_fact_sheet(html: str) -> dict:
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ").lower()
    
    tuition = None
    tuition_label = None
    for pattern in TUITION_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            tuition = int(match.group(1).replace(",", ""))
            tuition_label = pattern  # log which pattern matched
            break
    
    length_months = None
    for pattern in LENGTH_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = int(match.group(1))
            if "semester" in pattern:
                val = val * 6
            elif "year" in pattern:
                val = val * 12
            length_months = val
            break
    
    return {"tuition_total": tuition, "program_length_months": length_months,
            "tuition_source_label": tuition_label}
```

#### 3b — PDF fact sheet
```python
import pdfplumber

def parse_pdf_fact_sheet(pdf_url: str) -> dict:
    resp = requests.get(pdf_url, headers=HEADERS, timeout=20)
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    return parse_html_fact_sheet(text)  # reuse same regex logic on extracted text
```

**Validation after parsing each record:**
```python
def validate_record(record: dict) -> list[str]:
    warnings = []
    t = record.get("tuition_total")
    l = record.get("program_length_months")
    
    if t is not None:
        if t < 20_000:
            warnings.append(f"Tuition suspiciously low: ${t}")
        if t > 200_000:
            warnings.append(f"Tuition suspiciously high: ${t}")
    
    if l is not None:
        if l < 24:
            warnings.append(f"Length suspiciously short: {l} months")
        if l > 48:
            warnings.append(f"Length suspiciously long: {l} months")
    
    return warnings  # logged to scrape_notes, record still saved
```

Known good ranges: DPT tuition $30k–$150k total, length 30–36 months typically.

---

## Retryability — SQLite State Store

**File:** `db.py`

This is the most important reliability feature. Every program's state is persisted so the
scraper can be killed and resumed at any point without re-scraping completed records.

```python
import sqlite3
from datetime import datetime

DB_PATH = "scrape_state.db"

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS programs (
            program_id TEXT PRIMARY KEY,
            institution_name TEXT,
            program_name TEXT,
            state TEXT,
            degree_type TEXT,
            accreditation_status TEXT,
            program_url TEXT,
            fact_sheet_url TEXT,
            tuition_resident INTEGER,
            tuition_nonresident INTEGER,
            tuition_total INTEGER,
            program_length_months INTEGER,
            tuition_source_label TEXT,
            last_updated TEXT,
            scrape_date TEXT,
            scrape_status TEXT,
            scrape_notes TEXT
        )
    """)
    con.commit()
    return con

def upsert_program(con, record: dict):
    cols = ", ".join(record.keys())
    placeholders = ", ".join("?" * len(record))
    updates = ", ".join(f"{k}=excluded.{k}" for k in record if k != "program_id")
    con.execute(
        f"INSERT INTO programs ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT(program_id) DO UPDATE SET {updates}",
        list(record.values())
    )
    con.commit()

def get_pending(con, statuses=("pending", "timeout", "parse_failed")) -> list:
    """Return programs not yet successfully scraped — for retry runs."""
    placeholders = ",".join("?" * len(statuses))
    return con.execute(
        f"SELECT * FROM programs WHERE scrape_status IN ({placeholders})",
        statuses
    ).fetchall()
```

**Retry logic:**
- `success` → never re-scraped unless `--force` flag passed
- `fact_sheet_not_found` → skip by default, retry with `--retry-notfound`
- `parse_failed` → always retry on next run (regex may have been fixed)
- `timeout` → always retry on next run
- `blocked` → skip, log for manual review

---

## CLI Interface

**File:** `run_scraper.py`

```bash
# Full run from scratch
python run_scraper.py

# Resume interrupted run (skips successes)
python run_scraper.py --resume

# Retry only failed parses
python run_scraper.py --resume --retry-failed

# Force re-scrape specific program
python run_scraper.py --force-id "usc-ca-dpt"

# Only scrape DPT (skip PTA)
python run_scraper.py --degree DPT

# Export CSV when done
python run_scraper.py --export-csv output/capte_programs.csv

# Dry run — fetch directory only, no fact sheet requests
python run_scraper.py --dry-run
```

---

## Rate Limiting & Politeness

```python
# config.py
import time, random

REQUEST_DELAY_MIN = 2.0   # seconds between requests
REQUEST_DELAY_MAX = 5.0   # randomized to avoid pattern detection
TIMEOUT = 15              # seconds per request
MAX_RETRIES = 3           # per URL before marking as failed
RETRY_BACKOFF = [5, 15, 60]  # seconds between retries

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HealthCareerResearch/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/pdf",
}

def polite_sleep():
    time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))
```

**Also:**
- Check `robots.txt` on each domain before first request to that domain (cache per domain)
- Log every HTTP status code — 429 means back off 60s, 403 means mark as `blocked`
- Never hammer the same domain twice in a row — interleave requests across institutions

---

## Output

**File:** `output.py`

```python
import csv, sqlite3

def export_csv(db_path: str, out_path: str):
    con = sqlite3.connect(db_path)
    rows = con.execute("SELECT * FROM programs WHERE scrape_status = 'success'").fetchall()
    cols = [d[0] for d in con.execute("SELECT * FROM programs LIMIT 0").description]
    
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows([dict(zip(cols, r)) for r in rows])
    
    print(f"Exported {len(rows)} programs to {out_path}")

def print_summary(db_path: str):
    con = sqlite3.connect(db_path)
    for status, count in con.execute(
        "SELECT scrape_status, COUNT(*) FROM programs GROUP BY scrape_status"
    ).fetchall():
        print(f"  {status}: {count}")
```

---

## Completion Criteria

The scraper is done when:

| Metric | Target |
|---|---|
| Programs in DB | 280–320 (DPT) |
| `scrape_status = success` | ≥ 85% |
| `tuition_total` populated | ≥ 80% of successes |
| `program_length_months` populated | ≥ 75% of successes |
| `fact_sheet_not_found` | < 10% (remainder = manual review queue) |
| `parse_failed` after 3 retries | < 5% |

**Manual review queue:** Export all non-success records to `manual_review.csv`.
These are the ~15–30 programs where the scraper couldn't find or parse the fact sheet.
A human can find the data in 2–3 minutes each.

---

## Python Dependencies

```
requests
beautifulsoup4
playwright          # only if CAPTE directory is JS-rendered
pdfplumber          # PDF fact sheet parsing
lxml                # faster BS4 parser
```

Install:
```bash
pip install requests beautifulsoup4 pdfplumber lxml
pip install playwright && playwright install chromium
```

---

## Suggested Run Order for Claude Code

1. Write `config.py` and `db.py` first — foundation everything else depends on
2. Write and test `capte_directory.py` — validate program count before proceeding
3. Write `fact_sheet_finder.py` — test on 10 programs manually before full run
4. Write `fact_sheet_parser.py` — test regex patterns against 5 sample fact sheets
5. Write `run_scraper.py` CLI last — wires everything together
6. Write `output.py` — export CSV

Test each module independently before wiring. The worst outcome is a scraper
that silently gets wrong data — the validation ranges in Step 3 exist to catch this.
