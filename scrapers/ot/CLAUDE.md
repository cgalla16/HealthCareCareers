# OT URL Discovery Agent — Claude Code Instructions

## Your Job
You are running TWO separate URL discovery pipelines for OT (Occupational Therapy) programs,
followed by LLM-based validation and re-discovery.

**Pipeline A — Outcomes**
Goal: Find the page where each OT program publishes cohort size and graduation rate.
Output: `output/ot_outcomes_urls.csv`
Queries use full degree names: `{school_name} {degree_full} Publication of Program Outcomes`

**Pipeline B — Tuition**
Goal: Find the page where each OT program publishes cost of attendance / tuition.
Output: `output/ot_tuition_urls.csv`
Queries use full degree names: `{school_name} {degree_full} tuition cost of attendance`

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
SERPER_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
```

Get a Serper key at https://serper.dev (2,500 free searches — no credit card needed)

## Full Pipeline (Run Order)
```bash
# Step 1 — Load programs from input CSVs into output CSVs
python 01_load_programs.py

# Step 2 — Serper-based URL discovery (run both in parallel in separate terminals)
python 02_discover_outcomes_urls.py
python 03_discover_tuition_urls.py

# Step 3 — Review & fix low-confidence or missing URLs manually
python 04_export_review.py
# Open output/ot_review.csv, fill in manual_url column, set url_status=manual_override
python 05_apply_manual.py

# Step 4 — LLM validation + data extraction (Claude Haiku)
python 06_validate_urls.py --pipeline outcomes
python 06_validate_urls.py --pipeline tuition

# Step 5 — LLM re-discovery for rejected URLs (Claude Sonnet + web_search + web_fetch)
python 07_rediscover_rejected.py --pipeline outcomes
python 07_rediscover_rejected.py --pipeline tuition

# Step 6 — Re-validate newly discovered URLs
python 06_validate_urls.py --pipeline outcomes
python 06_validate_urls.py --pipeline tuition
```

## Input
`input_outcomes.csv`  — loaded into output/ot_outcomes_urls.csv (Pipeline A)
`input_financial.csv` — loaded into output/ot_tuition_urls.csv  (Pipeline B)
Required columns: `program_id`, `school_name`, `city`, `state`, `degree_type`
Optional: `program_url`

## Output Files
`output/ot_outcomes_urls.csv`  — outcomes page URLs + extracted data
  Columns added by pipeline: url_status, url_confidence, discovered_url, search_query_used,
  estimated_year, validation_status, rejection_reason, graduation_rate_pct, cohort_size,
  nbcot_pass_rate_pct, employment_rate_pct, data_year, rediscovery_status

`output/ot_tuition_urls.csv`   — tuition/cost page URLs + extracted data
  Columns added by pipeline: url_status, url_confidence, discovered_url, search_query_used,
  estimated_year, validation_status, rejection_reason, tuition_per_year, total_program_cost,
  fees_per_year, data_year, rediscovery_status

## Validation Status Values (06_validate_urls.py)
- `valid`        — correct page, data extracted
- `rejected`     — wrong school or wrong program type (e.g. OTA assistant program)
- `fetch_failed` — HTTP error or timeout fetching the URL
- `llm_error`    — Claude API error during validation

## Re-discovery Status Values (07_rediscover_rejected.py)
- `found`     — new URL found, validation_status reset to "" for re-validation
- `not_found` — Claude could not find a correct URL after searching

## Important Rules
- NEVER delete output CSVs — always upsert
- Re-running any script is always safe (idempotent via upsert_record)
- Use --force to re-run already-processed rows
- Use --limit N to test on a small batch first
- Rate limit: 2-3 second delay between searches, 60s backoff on 429
- Max 3 search attempts per school per pipeline before marking `search_exhausted`
- Do NOT accept OTA (Occupational Therapy Assistant) program pages — these are 2-year
  associate programs, NOT the graduate MOT/OTD programs we need
- Input CSVs use encoding="latin-1" (school names have Windows-1252 special chars)
- Windows terminal: avoid Unicode chars (use [OK]/[X] not ✓/✗) — cp1252 will crash

## Cost Estimates
- 06_validate_urls.py: ~$2-3 total per pipeline (Claude Haiku, ~1-2 cents/program)
- 07_rediscover_rejected.py: ~$15-25 total per pipeline (Claude Sonnet + web tools)
