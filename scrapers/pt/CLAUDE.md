# PT Program Data Pipeline — Instructions

## Goal
Collect tuition cost and program length for ~300 DPT (Doctor of Physical Therapy) programs.
Data may live on the program homepage, a sub-page, or a PDF — the pipeline handles all cases.

## Setup
```bash
pip install requests pandas python-dotenv beautifulsoup4 pdfplumber anthropic --break-system-packages
```

Create a `.env` file in this directory:
```
ANTHROPIC_API_KEY=your_key_here
```

Serper API is no longer needed for new runs (URL discovery now uses the APTA directory).

---

## Run Order

### Phase 1 — Populate program URLs (one-time, already done)
```bash
python 07_parse_apta_directory.py
```
Fetches https://aptaapps.apta.org/accreditedschoolsdirectory/AllPrograms.aspx (no API key needed),
extracts all DPT program homepage URLs, and writes them into `output/pt_programs.csv`.

Produces:
- `url_map.csv` — raw APTA harvest with match actions per school
- `url_map_unmatched.csv` — schools that couldn't be auto-matched (review manually)
- `output/pt_programs.csv` — updated with `apta_program_url` and `outcomes_url` columns

### Phase 2 — Validate URLs and extract data (validation + financial data)
```bash
python 05_validate_urls.py --retry-rejected   # re-process previously rejected/failed rows
python 05_validate_urls.py                    # process only new/unprocessed rows
python 05_validate_urls.py --force            # re-run everything including valid rows
python 05_validate_urls.py --limit 5          # test on 5 rows before full run
```

For each school the script tries two candidate URLs in priority order:
1. `fact_sheet_url` — previously discovered financial fact sheet (if present)
2. `apta_program_url` — DPT program homepage from APTA directory (reliable fallback)

It keeps the **best result** across both URLs using this priority ranking:
`valid` > `confirmed_landing` > `rejected` > `fetch_failed`

### Phase 3 — Extract program cost and length
```bash
python 08_extract_data.py --limit 5    # test run
python 08_extract_data.py              # process all remaining rows
python 08_extract_data.py --force      # reprocess everything
python 08_extract_data.py --stale-only # only rows with stale/missing data (year < 2025)
python 08_extract_data.py --landing-only # only confirmed_landing rows (sub-page path)
```

Targets:
- `program_length_months` — new column (not previously extracted)
- `total_program_cost` / `tuition_per_year` — refresh if data_year < 2025

Strategy per row:
- Fresh data (>=2025) + missing length → re-fetch known source, extract length only
- Stale + apta direct → fetch apta_program_url, extract cost + length
- Stale + apta landing → heuristic sub-page discovery (keyword-scored links, top 3 fetched)
- No apta → fallback to fact_sheet_url (noted as potentially stale)

### Phase 4 — Manual review of low-confidence rows
```bash
python 03_export_review.py    # exports rows needing manual URL correction
python 04_apply_manual.py     # merges manual fixes back into pt_programs.csv
```

---

## Validation Status Values

| Status | Meaning | Next step |
|--------|---------|-----------|
| `valid` | Data extracted successfully | Done |
| `confirmed_landing` | Correct school/program page, financial data is on a sub-page | Sub-page crawler (future) |
| `rejected` | Wrong school, PTA program, or unrelated page | Ignore |
| `fetch_failed` | HTTP/network error fetching the URL | Retry or manual fix |
| `llm_error` | Claude API error | Retry |

---

## Key Columns in pt_programs.csv

| Column | Source | Description |
|--------|--------|-------------|
| `fact_sheet_url` | Serper search (02_discover_urls.py) | Previously discovered financial fact sheet URL |
| `apta_program_url` | APTA directory (07_parse_apta_directory.py) | Reliable DPT program homepage |
| `outcomes_url` | APTA directory (07_parse_apta_directory.py) | CAPTE outcomes page (A.4.2) |
| `validation_status` | 05_validate_urls.py | See table above |
| `extracted_from_url` | 05_validate_urls.py | Which URL actually yielded valid data |
| `tuition_per_year` | 05_validate_urls.py | Extracted financial data |
| `total_program_cost` | 05_validate_urls.py | Extracted financial data |

---

## Important Rules
- NEVER delete `output/pt_programs.csv` — always upsert
- All scripts are resumable — re-running skips already-processed rows (unless --force)
- `fact_sheet_url_2` has been removed — it was lower-confidence than `fact_sheet_url` and added no value
- The APTA directory fetch requires no API key and has no rate limit concern

## Legacy Scripts (less relevant now)
- `01_load_programs.py` — initial CSV setup (already done)
- `02_discover_urls.py` — Serper-based URL discovery (replaced by 07 for new runs)
- `06_rediscover_rejected.py` — Claude web search rediscovery (no longer needed; APTA URLs serve this purpose)
