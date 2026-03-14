# PT Program Data Pipeline

Collects program cost and length for ~300 accredited DPT (Doctor of Physical Therapy) programs.
Data sourced from the [APTA Accredited Schools Directory](https://aptaapps.apta.org/accreditedschoolsdirectory/AllPrograms.aspx) (no API key needed).

---

## Setup

```bash
pip install requests pandas python-dotenv beautifulsoup4 pdfplumber anthropic --break-system-packages
```

Create a `.env` file in this directory:
```
ANTHROPIC_API_KEY=your_key_here
```

---

## Pipeline

### Phase 1 — URL harvest from APTA directory *(one-time, already done)*
```bash
python 07_parse_apta_directory.py
```
Fetches the APTA accredited schools directory, extracts DPT program homepage URLs, and fuzzy-matches them into `output/pt_programs.csv`.

Produces:
- `url_map.csv` — raw APTA harvest (~300 DPT programs) with match actions
- `url_map_unmatched.csv` — schools that couldn't be auto-matched (review manually)
- Updates `output/pt_programs.csv` with `apta_program_url` and `outcomes_url`

### Phase 2 — Validate URLs + initial data extraction
```bash
python 05_validate_urls.py                    # process new/unprocessed rows
python 05_validate_urls.py --retry-rejected   # retry rejected/failed rows
python 05_validate_urls.py --retry-stale      # re-check valid rows with data_year < 2024
python 05_validate_urls.py --force            # reprocess everything
python 05_validate_urls.py --limit 5          # test run
```

For each program, tries URLs in priority order: `fact_sheet_url` → `apta_program_url`.
Keeps the best result: `valid` > `confirmed_landing` > `rejected` > `fetch_failed`.

| Status | Meaning |
|--------|---------|
| `valid` | Data extracted directly from the page |
| `confirmed_landing` | Correct program page, but financial data is on a sub-page |
| `rejected` | Wrong school, PTA program, or unrelated |
| `fetch_failed` | HTTP/network error |

### Phase 3 — Extract program cost and length
```bash
python 08_extract_data.py --limit 5               # test run
python 08_extract_data.py                          # process all remaining rows
python 08_extract_data.py --force --recalculate-cost  # re-extract everything (use after prompt changes)
python 08_extract_data.py --stale-only             # only rows with data_year < 2025
python 08_extract_data.py --landing-only           # only confirmed_landing rows
```

Primary targets: `total_program_cost` (computed from any format) and `program_length_months`.

Handles all cost display formats:
- Explicit total → stored directly, `cost_basis="total"`
- Per year → multiplied by program years, `cost_basis="per_year"`
- Per semester → multiplied by semesters, `cost_basis="per_semester"`
- Per credit hour → multiplied by total credits, `cost_basis="per_credit"`

For `confirmed_landing` rows: heuristic keyword scoring selects candidate sub-pages (no extra API calls), fetches top 3, merges best cost + length found.

---

## Output: `output/pt_programs.csv`

**Never delete this file — all scripts upsert, never overwrite.**

| Column | Source | Description |
|--------|--------|-------------|
| `program_id` | Input | DB primary key |
| `school_name`, `city`, `state` | Input | Location |
| `fact_sheet_url` | Legacy Serper search | Previously discovered financial fact sheet |
| `apta_program_url` | `07_parse_apta_directory.py` | APTA-verified DPT homepage |
| `outcomes_url` | `07_parse_apta_directory.py` | CAPTE outcomes page (A.4.2) |
| `validation_status` | `05_validate_urls.py` | See status table above |
| `extracted_from_url` | `05_validate_urls.py` | Which URL yielded data |
| `apta_landing_confirmed` | `05_validate_urls.py` | APTA URL verified as correct program page |
| `total_program_cost` | `08_extract_data.py` | Full program cost (computed if needed) |
| `tuition_per_year` | `05`/`08` | Annual tuition figure |
| `cost_basis` | `08_extract_data.py` | How total was derived: total/per_year/per_semester/per_credit |
| `cost_components` | `08_extract_data.py` | Raw figures e.g. `"1150/cr x 126cr"` |
| `program_length_months` | `08_extract_data.py` | Total DPT program duration |
| `data_year` | `05`/`08` | Academic year of extracted data |
| `extraction_notes` | `08_extract_data.py` | Compact provenance string |

---

## Legacy Scripts

These scripts from the original Serper-based discovery phase are no longer needed for new runs:
- `01_load_programs.py` — initial CSV setup (done)
- `02_discover_urls.py` — Serper Google search discovery (replaced by `07`)
- `03_export_review.py` / `04_apply_manual.py` — manual URL review workflow
- `06_rediscover_rejected.py` — Claude web search rediscovery (replaced by APTA URL fallback)
