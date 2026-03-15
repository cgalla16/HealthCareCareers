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

---

## Cost & Length Data Audit (2026-03-14)

Post-extraction analysis of 299 DPT programs. `09_audit_clean.py` has cleared 56 known-bad rows.

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

- APTA directory fetch (07) gave reliable program homepage URLs with no API key
- `csv_store.py` atomic upserts prevented corruption on interrupts; safe to Ctrl+C and resume
- `extraction_notes` and `cost_basis` columns provide full traceability for every value
- `09_audit_clean.py` caught systematic contamination groups and documented root causes

### Next Steps

**P0 — Add 3 more rows to 09_audit_clean.py, then re-run:**
- Program 25 (Mercy): null length — 12 months is impossible
- Program 191 (Winston-Salem): null cost — $633 is fees only
- Program 88 (UNF): null cost — $2,291 is in-state fees (fact_sheet already cleared)
- Program 129 (Clarke): verify $102k is truly per-year before deciding

```bash
python 09_audit_clean.py
python 08_extract_data.py   # re-extracts AUDIT_CLEARED rows via apta_program_url
```

**P1 — State school in-state/OOS review:**
Manually check the ~7 programs with tuition < $10k (listed in table above). Consider adding a
`tuition_residency` column ("in_state" / "out_of_state" / "unknown").

**P2 — Load into DB (after P0–P1 complete):**
Update `db/pipelines/schools.py` to populate `tuition_per_year` and `program_length_months`
in the `programs` table. Both columns already exist in the schema.
