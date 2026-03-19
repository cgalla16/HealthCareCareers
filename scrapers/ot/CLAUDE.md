# OT Program Data Pipeline — Claude Code Instructions

## Your Job
Run TWO separate data extraction pipelines for OT (Occupational Therapy) programs.

**Pipeline A — Outcomes**
Goal: Validate and extract cohort size, graduation rate, and pass rate from each program's outcomes page.
Output: `output/ot_outcomes_urls.csv`

**Pipeline B — Tuition**
Goal: Validate and extract tuition / cost of attendance from each program's tuition page.
Output: `output/ot_tuition_urls.csv`

`{degree_type}` is `MOT` or `OTD`. `{degree_full}` expands to:
- MOT → "Master of Occupational Therapy"
- OTD → "Doctor of Occupational Therapy"

These are completely independent — run them separately, resume independently.

## Setup First
```bash
pip install requests pandas python-dotenv anthropic beautifulsoup4 pdfplumber
```

Create a `.env` file in this directory:
```
ANTHROPIC_API_KEY=your_key_here
```

## Full Pipeline (Run Order)
```bash
# Step 1 — Load programs from input CSVs into output CSVs
python 01_load_programs.py

# Step 2 — Discover program homepage URLs from ACOTA accredited schools directory
# Runs once; re-run with --retry-not-found after manual fixes
python 02_discover_urls.py
# Output: output/ot_program_urls.csv  (shared program homepage URLs)

# Step 3 — Review & fix low-confidence or missing URLs manually
python 03_export_review.py
# Open output/ot_outcomes_review.csv / ot_tuition_review.csv, fill in manual_url column
python 04_apply_manual.py

# Step 4 — LLM validation + data extraction (Claude Haiku)
python 05_validate_urls.py --pipeline outcomes
python 05_validate_urls.py --pipeline tuition
```

## Input
`input_outcomes.csv`  — loaded into output/ot_outcomes_urls.csv (Pipeline A)
`input_financial.csv` — loaded into output/ot_tuition_urls.csv  (Pipeline B)
Required columns: `program_id`, `school_name`, `city`, `state`, `degree_type`
Optional: `program_url`

## Output Files
`output/ot_program_urls.csv`   — ACOTA-discovered program homepage URLs (shared, never delete)
  Columns: program_id, school_name, city, state, degree_type,
  acota_program_url, acota_match_name, acota_match_score,
  url_status, url_confidence, discovery_notes, last_updated

`output/ot_outcomes_urls.csv`  — outcomes page URLs + extracted data
  Columns added by pipeline: url_status, url_confidence, discovered_url,
  validation_status, rejection_reason, graduation_rate_pct, cohort_size,
  nbcot_pass_rate_pct, employment_rate_pct, data_year

`output/ot_tuition_urls.csv`   — tuition/cost page URLs + extracted data
  Columns added by pipeline: url_status, url_confidence, discovered_url,
  validation_status, rejection_reason, tuition_per_year, total_program_cost,
  fees_per_year, data_year

## Validation Status Values (05_validate_urls.py)
- `valid`        — correct page, data extracted
- `rejected`     — wrong school or wrong program type (e.g. OTA assistant program)
- `fetch_failed` — HTTP error or timeout fetching the URL
- `llm_error`    — Claude API error during validation

## Important Rules
- NEVER delete output CSVs — always upsert
- Re-running any script is always safe (idempotent via upsert_record)
- Use --force to re-run already-processed rows
- Use --limit N to test on a small batch first (especially for 02_discover_urls.py)
- Do NOT accept OTA (Occupational Therapy Assistant) program pages — these are 2-year
  associate programs, NOT the graduate MOT/OTD programs we need
- Input CSVs use encoding="latin-1" (school names have Windows-1252 special chars)
- Windows terminal: avoid Unicode chars (use [OK]/[X] not ✓/✗) — cp1252 will crash

## Cost Estimates
- 02_discover_urls.py: ~$0.10 one-time (Claude Haiku, directory parse + profile links)
- 05_validate_urls.py: ~$2-3 total per pipeline (Claude Haiku, ~1-2 cents/program)
