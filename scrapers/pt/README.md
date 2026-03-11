# PT URL Discovery Agent

Finds the Financial Fact Sheet URL for each DPT program using Google Search (Serper API).

This is **Stage 1** of a two-stage pipeline:
- **Stage 1 (this):** Find the right URLs
- **Stage 2 (separate):** Visit those URLs and extract tuition + program length data

---

## Setup

### 1. Get a free Serper API key
Go to https://serper.dev → Sign up → Copy your API key
Free tier: **2,500 searches** (no credit card needed)
Your pipeline needs ~900 searches for PT (300 schools × 3 query attempts max)

### 2. Install dependencies
```bash
pip install -r requirements.txt
```
Or if using Claude Code:
```bash
pip install requests pandas python-dotenv --break-system-packages
```

### 3. Create your .env file
```
SERPER_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
```

### 4. Prepare your input CSV
Export your PT programs to `input_programs.csv` in this directory.

**Required columns:**
| Column | Description |
|--------|-------------|
| `program_id` | Unique ID (from your DB) |
| `school_name` | Full school name (e.g. "University of Southern California") |
| `city` | City |
| `state` | State abbreviation |

**Optional but helpful:**
| Column | Description |
|--------|-------------|
| `program_url` | Program's main website — improves search targeting |

---

## Running the Pipeline

### Step 1 — Load programs
```bash
python 01_load_programs.py
```
Reads `input_programs.csv`, creates `output/pt_programs.csv`.
Safe to re-run — never overwrites existing data.

### Step 2 — Discover URLs
```bash
python 02_discover_urls.py
```
Runs Google searches for each pending program.
**Resumable** — if interrupted, re-run and it picks up where it left off.

Options:
```bash
python 02_discover_urls.py --limit 10           # test on first 10 rows
python 02_discover_urls.py --retry-notfound     # retry previously not-found rows
python 02_discover_urls.py --force              # re-run everything
```

### Step 3 — Export for manual review
```bash
python 03_export_review.py
```
Prints a summary and writes `output/pt_review.csv` with rows needing human attention.

### Step 4 — Apply manual fixes (after review)
Fill in `manual_url` column in `pt_review.csv`, set `url_status = manual_override`.
Then run:
```bash
python 04_apply_manual.py
```

### Step 5 — Validate URLs with Claude Haiku
```bash
python 05_validate_urls.py
python 05_validate_urls.py --limit 10   # test first
python 05_validate_urls.py --force      # re-validate all
```
Fetches each `fact_sheet_url`, asks Claude Haiku to confirm it's the correct DPT page,
and extracts available data fields. Adds `validation_status` + data columns to the CSV.

### Step 6 — Re-discover rejected URLs with Claude Sonnet
```bash
python 06_rediscover_rejected.py
python 06_rediscover_rejected.py --limit 20   # recommended for first run
python 06_rediscover_rejected.py --force      # retry not_found rows
```
For rows where `validation_status=rejected`, uses Claude Sonnet with web search + navigation
to find the correct page. Uses a two-step `site:edu` search strategy to avoid landing on
the wrong school's pages. After finding a new URL, resets `validation_status` so Step 5
re-validates it on the next run.

Then re-run Step 5 to validate the newly discovered URLs:
```bash
python 05_validate_urls.py
```

---

## Output Files

| File | Description |
|------|-------------|
| `output/pt_programs.csv` | Master file — never delete this |
| `output/pt_review.csv` | Rows needing manual review |

### Master CSV columns
| Column | Description |
|--------|-------------|
| `program_id` | Your DB ID |
| `school_name` | School name |
| `city`, `state` | Location |
| `program_url` | Main program website (input) |
| `fact_sheet_url` | **Discovered fact sheet URL** |
| `fact_sheet_url_2` | Backup URL (second-best result) |
| `url_confidence` | `high` / `medium` / `low` / `manual` |
| `url_status` | See below |
| `search_query_used` | Which query found it |
| `search_attempts` | How many queries were tried |
| `scrape_notes` | Warnings / errors |
| `estimated_year` | Year extracted from URL (e.g. `2024`) |
| `validation_status` | `valid` / `rejected` / `fetch_failed` / `llm_error` |
| `rejection_reason` | Why the URL was rejected |
| `rediscovery_status` | `found` / `not_found` (set by Step 6) |
| `tuition_per_year` | Extracted tuition (dollars) |
| `total_program_cost` | Extracted total cost (dollars) |
| `fees_per_year` | Extracted fees (dollars) |
| `graduation_rate_pct` | Extracted graduation rate (%) |
| `board_pass_rate_pct` | Extracted NPTE first-time pass rate (%) |
| `employment_rate_pct` | Extracted employment rate (%) |
| `data_year` | Year the extracted data refers to |

### URL Status values
| Status | Meaning | Action |
|--------|---------|--------|
| `pending` | Not yet searched | Auto-processed next run |
| `url_found` | Found with high/medium confidence | ✓ Ready for Stage 2 |
| `url_found_low_confidence` | Found but uncertain | Manual review recommended |
| `url_not_found` | All queries returned nothing useful | Manual review needed |
| `search_exhausted` | Hit 3-attempt max | Manual review needed |
| `manual_override` | Human-verified URL | ✓ Ready for Stage 2 |
| `error` | Network/API error | Auto-retried next run |
| `blocked` | 403 on target site | Manual review |

---

## Search Query Cascade

For each school, queries are tried in order until a **high-confidence** result is found:

1. `{school_name} DPT financial fact sheet`
2. `{school_name} physical therapy financial fact sheet`
3. `{school_name} DPT program costs tuition fees`

**Confidence scoring** is based on:
- PDF files get a big boost (fact sheets are often PDFs)
- "fact-sheet" or "factsheet" in the URL = highest signal
- Keywords in title: "financial fact sheet", "program costs", "cost of attendance"
- School name appearing in the result domain
- Exclusion of aggregator sites (US News, LinkedIn, Indeed, etc.)

---

## Cost Estimate

| Scenario | Searches | Serper Cost |
|----------|----------|-------------|
| 300 schools, all find on query 1 | 300 | Free (within 2,500) |
| 300 schools, avg 2 queries each | 600 | Free |
| 300 schools, all 3 queries | 900 | Free |
| Full retry run after manual review | +200 | Free |
| **Total worst case** | **~1,100** | **$0** |

---

## Handoff to Stage 2

Once `url_status` is `url_found` or `manual_override` for ≥85% of programs,
export the ready rows:

```python
import pandas as pd
df = pd.read_csv("output/pt_programs.csv")
ready = df[df["url_status"].isin(["url_found", "manual_override"])]
ready[["program_id", "school_name", "fact_sheet_url", "url_confidence"]].to_csv("stage2_input.csv", index=False)
```

Pass `stage2_input.csv` to the parsing agent.
