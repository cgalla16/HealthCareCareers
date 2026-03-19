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
python 02_parse_apta_directory.py
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
python 06_extract_data.py --limit 5    # test run
python 06_extract_data.py              # process all remaining rows
python 06_extract_data.py --force      # reprocess everything
python 06_extract_data.py --stale-only # only rows with stale/missing data (year < 2025)
python 06_extract_data.py --landing-only # only confirmed_landing rows (sub-page path)
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
| `fact_sheet_url` | Legacy Serper discovery (historical) | Previously discovered financial fact sheet URL |
| `apta_program_url` | APTA directory (02_parse_apta_directory.py) | Reliable DPT program homepage |
| `outcomes_url` | APTA directory (02_parse_apta_directory.py) | CAPTE outcomes page (A.4.2) |
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

---

## Cost & Length Data Audit (2026-03-14)

Post-extraction analysis of 299 DPT programs. `07_audit_clean.py` has cleared 56 known-bad rows.

### Summary Stats

| Metric | program_length_months | tuition_per_year |
|--------|----------------------|-----------------|
| Valid rows | 259 / 299 (86.6%) | 225 / 299 (75.3%) |
| Missing | 40 (13.4%) | 74 (24.7%) |
| Min | 12 (Mercy — wrong) | $633 (Winston-Salem — wrong) |
| Max | 66 (Duquesne — AUDIT_CLEARED) | $102,000 (Clarke) |
| Mean | 33.2 months | $37,346 |
| Median | 34 months | $37,934 |

### Does the Distribution Make Sense?

**Length — mostly yes.** Mode is 36 months (44%), the standard 3-year DPT cadence. 83% fall
30–36 months. Accelerated programs at 24–27 months exist legitimately (e.g., Army-Baylor at 23
months). Outliers at 12 and 66 months are clearly extraction errors.

**Tuition — partially, with a structural problem.** Private schools at $40–60k/yr is realistic.
But many state schools likely extracted in-state tuition only — most DPT students are out-of-state.
The $37k mean is inflated by private schools and the distribution is effectively bimodal
(public vs. private) without that label in the data.

### Confirmed Outliers

**Clearly wrong — should be nulled:**

| ID | School | Value | Why it's wrong |
|----|--------|-------|----------------|
| 25 | Mercy University | 12 months | No accredited DPT is 12 months |
| 191 | Winston-Salem State | $633/yr | Admin fees only, not tuition |
| 88 | Univ North Florida | $2,291/yr | In-state fees, not full tuition |

**Suspicious — needs verification:**

| ID | School | Value | Concern |
|----|--------|-------|---------|
| 129 | Clarke University | $102,000/yr | Verify this is per-year, not total cost mislabeled |
| 74/65 | USC Hybrid | $86,125/yr | High but plausible for USC hybrid program |
| 19 | SUNY Downstate | $9,282/yr | Likely in-state only |
| 192 | Western Carolina | $8,154/yr | Likely in-state only |
| 170 | U Montana | $9,241/yr | Likely in-state only |
| 267 | Angelo State | $6,170/yr | Likely in-state only |
| 299 | U Puerto Rico | $7,317/yr | May be accurate (PR is a commonwealth) |

### What We Missed and Why

**1. Domain mismatch detection (biggest miss, ~43+ rows contaminated)**
Serper returned popular PDFs (UNLV, Idaho State, U Montana, U Mary, BU) as top Google hits for
many unrelated DPT searches. `05_validate_urls.py` checked page content with Claude but didn't
verify the source domain matched the school's own domain. Should have checked `urlparse(url).netloc`
or page `<title>` against the school name — would have caught >90% of these before extraction.

**2. In-state vs. out-of-state tuition not standardized**
State schools report both rates; Claude grabbed whichever appeared first (usually in-state).
The extraction prompt didn't specify a preference. Should have extracted both rates explicitly
and used out-of-state as the display value.

**3. No post-extraction range validation**
Calculation errors ($334,884 for UW, $419,022 for Mercer) and fees-only values ($633, $1,130)
weren't caught until a manual audit pass. Should have auto-flagged anything outside [8000, 85000]
for tuition and [24, 42] for length at write time.

**4. LLM summing in-state + out-of-state columns**
Three programs had costs calculated as in-state + OOS summed together (e.g., $334,884 = $167k × 2).
HTML tables show both columns side-by-side. Should have added a prompt guard: "If you see two
tuition columns, extract ONLY the out-of-state value. Never sum them."

### What We Did Well

- APTA directory fetch (02) gave reliable program homepage URLs with no API key
- `csv_store.py` atomic upserts prevented corruption on interrupts; safe to Ctrl+C and resume
- `extraction_notes` and `cost_basis` columns provide full traceability for every value
- `07_audit_clean.py` caught systematic contamination groups and documented root causes

### Next Steps

**P0 — Add 3 more rows to 07_audit_clean.py, then re-run:**
- Program 25 (Mercy): null length — 12 months is impossible
- Program 191 (Winston-Salem): null cost — $633 is fees only
- Program 88 (UNF): null cost — $2,291 is in-state fees (fact_sheet already cleared)
- Program 129 (Clarke): verify $102k is truly per-year before deciding

```bash
python 07_audit_clean.py
python 06_extract_data.py   # re-extracts AUDIT_CLEARED rows via apta_program_url
```

**P1 — State school in-state/OOS review:**
Manually check the ~7 programs with tuition < $10k (listed in table above). Consider adding a
`tuition_residency` column ("in_state" / "out_of_state" / "unknown").

**P2 — Load into DB (after P0–P1 complete):**
Update `db/pipelines/schools.py` to populate `tuition_per_year` and `program_length_months`
in the `programs` table. Both columns already exist in the schema.
