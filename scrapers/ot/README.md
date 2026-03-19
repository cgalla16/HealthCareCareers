# OT Program Data Pipeline

Validates and extracts data from two URLs per OT program:
- **A.4.2** — Outcomes page (cohort size, graduation rate, NBCOT pass rate)
- **A.4.4** — Tuition/cost page (cost of attendance, program fees)

Both pipelines are independent and can run simultaneously in separate terminals.

---

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in this directory:
```
ANTHROPIC_API_KEY=your_key_here
```

### Input CSVs

`input_outcomes.csv` → loaded into `output/ot_outcomes_urls.csv`
`input_financial.csv` → loaded into `output/ot_tuition_urls.csv`

| Column | Required | Description |
|--------|----------|-------------|
| `program_id` | ✅ | Unique ID from your DB |
| `school_name` | ✅ | Full school name |
| `city` | ✅ | City |
| `state` | ✅ | State abbreviation |
| `degree_type` | ✅ | `MOT` or `OTD` |
| `program_url` | optional | Program's main website |

---

## Running the Pipeline

```bash
# Step 1 — Load both CSVs
python 01_load_programs.py

# Step 2 — Discover program homepage URLs from ACOTA directory (one-time run)
python 02_discover_urls.py
# Use --limit 10 to test first; --retry-not-found to retry unmatched schools

# Step 3 — Review summary + export low-confidence/unmatched rows
python 03_export_review.py
# Open review CSVs, fill in manual_url, set url_status=manual_override

# Step 4 — Apply manual URL corrections
python 04_apply_manual.py

# Step 5 — Validate URLs with Claude Haiku (run once per pipeline)
python 05_validate_urls.py --pipeline outcomes
python 05_validate_urls.py --pipeline tuition
```

### Options (discover script)
```bash
--limit 10           # test on first 10 pending programs only
--force              # re-match all programs including already-matched
--retry-not-found    # retry only url_not_found rows
```

### Options (validate script)
```bash
--limit 10           # test on first 10 rows only
--force              # re-run everything including already-valid rows
--retry-rejected     # retry rejected rows
```

---

## Pipeline Scripts

| Script | Role |
|--------|------|
| `01_load_programs.py` | Initialize output CSVs from input files |
| `02_discover_urls.py` | Discover program homepage URLs from ACOTA directory (agentic) |
| `03_export_review.py` | Export unmatched/unfound rows for manual review |
| `04_apply_manual.py` | Merge manual URL corrections |
| `05_validate_urls.py` | Validate URLs + extract data via Claude Haiku |
| `csv_store.py` | Atomic CSV upsert utility |

---

## Output Files

| File | Description |
|------|-------------|
| `output/ot_program_urls.csv` | ACOTA-discovered program homepage URLs — **never delete** |
| `output/ot_outcomes_urls.csv` | A.4.2 outcomes page URLs — **never delete** |
| `output/ot_tuition_urls.csv` | A.4.4 tuition page URLs — **never delete** |
| `output/ot_outcomes_review.csv` | Outcomes rows needing manual review |
| `output/ot_tuition_review.csv` | Tuition rows needing manual review |

### Output CSV columns

| Column | Description |
|--------|-------------|
| `program_id` | DB ID |
| `school_name`, `city`, `state`, `degree_type` | Program info |
| `discovered_url` | URL to validate |
| `url_status` | See status values below |
| `validation_status` | `valid` / `rejected` / `fetch_failed` / `llm_error` |
| `rejection_reason` | Why the URL was rejected |

**Outcomes pipeline additional columns:**
| Column | Description |
|--------|-------------|
| `graduation_rate_pct` | Extracted graduation rate (%) |
| `cohort_size` | Cohort size |
| `nbcot_pass_rate_pct` | NBCOT first-time pass rate (%) |
| `employment_rate_pct` | Employment rate (%) |
| `data_year` | Year the data refers to |

**Tuition pipeline additional columns:**
| Column | Description |
|--------|-------------|
| `tuition_per_year` | Tuition (dollars) |
| `total_program_cost` | Total program cost (dollars) |
| `fees_per_year` | Fees (dollars) |
| `data_year` | Year the data refers to |

### URL Status values
| Status | Meaning |
|--------|---------|
| `pending` | Not yet validated |
| `manual_override` | Human-verified URL |
| `error` | Network/API error — auto-retried next run |

---

## Important Rules

- NEVER delete output CSVs — always upsert
- Re-running any script is always safe (idempotent via upsert_record)
- Do NOT accept OTA (Occupational Therapy Assistant) program pages — these are 2-year
  associate programs, NOT the graduate MOT/OTD programs we need
- Input CSVs use `encoding="latin-1"` (school names have Windows-1252 special chars)
- Windows terminal: avoid Unicode chars (use `[OK]/[X]` not `✓/✗`) — cp1252 will crash

---

## Cost Estimate

- `02_discover_urls.py`: ~$0.10 one-time (Claude Haiku, directory parse + profile links)
- `05_validate_urls.py`: ~$2-3 total per pipeline (Claude Haiku, ~1-2 cents/program)
