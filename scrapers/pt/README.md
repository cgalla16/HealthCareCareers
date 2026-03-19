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
python 02_parse_apta_directory.py
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
python 06_extract_data.py --limit 5               # test run
python 06_extract_data.py                          # process all remaining rows
python 06_extract_data.py --force --recalculate-cost  # re-extract everything (use after prompt changes)
python 06_extract_data.py --stale-only             # only rows with data_year < 2025
python 06_extract_data.py --landing-only           # only confirmed_landing rows
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
| `apta_program_url` | `02_parse_apta_directory.py` | APTA-verified DPT homepage |
| `outcomes_url` | `02_parse_apta_directory.py` | CAPTE outcomes page (A.4.2) |
| `validation_status` | `05_validate_urls.py` | See status table above |
| `extracted_from_url` | `05_validate_urls.py` | Which URL yielded data |
| `apta_landing_confirmed` | `05_validate_urls.py` | APTA URL verified as correct program page |
| `total_program_cost` | `06_extract_data.py` | Full program cost (computed if needed) |
| `tuition_per_year` | `05`/`08` | Annual tuition figure |
| `cost_basis` | `06_extract_data.py` | How total was derived: total/per_year/per_semester/per_credit |
| `cost_components` | `06_extract_data.py` | Raw figures e.g. `"1150/cr x 126cr"` |
| `program_length_months` | `06_extract_data.py` | Total DPT program duration |
| `data_year` | `05`/`08` | Academic year of extracted data |
| `extraction_notes` | `06_extract_data.py` | Compact provenance string |

---

## Pipeline Scripts

| Script | Role |
|--------|------|
| `01_load_programs.py` | Initialize master CSV from input |
| `02_parse_apta_directory.py` | Harvest canonical URLs from APTA directory |
| `03_export_review.py` | Export unmatched/unfound rows for manual review |
| `04_apply_manual.py` | Merge manual URL corrections |
| `05_validate_urls.py` | Validate URLs + extract financial data via Claude Haiku |
| `06_extract_data.py` | Extract program cost and length |
| `07_audit_clean.py` | Null known-bad data (run once) |
| `csv_store.py` | Atomic CSV upsert utility |

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

**P0 — Done (2026-03-16): audit cleanup expanded to 60 rows**
- Added IDs 25 (Mercy 12mo), 191 (Winston-Salem $633), 129 (Clarke $102k) to `07_audit_clean.py`
- Clarke ($102k) confirmed wrong via FPTA PDF form fields: actual values Yr1=$39,480 / Yr2=$37,260 / Yr3=$33,200 / Total=$109,940
- ID 88 (UNF $2,291 in-state) was already in cleanup list and re-nulled

```bash
python 07_audit_clean.py   # already run; 60 rows cleaned
```

**P1 — Re-extract with hardened prompt (run after adding ANTHROPIC_API_KEY to .env)**

06_extract_data.py now has 3 new guardrails:
- OOS preference: extracts OOS as `tuition_per_year`, in-state as `tuition_instate`
- No-summing guard: never add side-by-side columns together
- Range sanity: flags values outside [$8k–$85k]/yr or [$50k–$280k] total in `notes`

New CSV columns added: `tuition_instate`, `tuition_is_oos`
PDF form field extraction also added (fixes FPTA fillable PDF parsing)

```bash
# Create .env with ANTHROPIC_API_KEY=your_key, then:

# 1. Re-extract known state-school rows with OOS-first prompt
python 06_extract_data.py --program-ids 19,192,170,267,299

# 2. Re-extract all rows with missing or AUDIT_CLEARED cost/length
python 06_extract_data.py

# 3. Target: >=85% tuition coverage (>= 255/299) before DB load
python -c "import pandas as pd; df=pd.read_csv('output/pt_programs.csv'); print(df['tuition_per_year'].notna().sum(), '/ 299 tuition')"
```

State school OOS verification checklist (check after re-extraction):

| ID | School | Old value | Expected |
|----|--------|-----------|----------|
| 19 | SUNY Downstate | $9,282 in-state | OOS rate |
| 192 | Western Carolina | $8,154 in-state | OOS rate |
| 170 | U Montana | $9,241 in-state | OOS rate |
| 267 | Angelo State | $6,170 in-state | OOS rate |
| 299 | U Puerto Rico | $7,317 | Likely correct (keep) |

**P2 — DB + frontend: DONE (2026-03-16)**

- DB schema: added `total_program_cost`, `tuition_instate`, `tuition_is_oos` columns
- `db/pipelines/schools.py` `clean_pt()`: merges scraper CSV on school_name+state
- `web/lib/db.js` `getPrograms()`: returns all new fields + `schoolType` (public/private from scorecard)
- `web/components/ProgramComparison.jsx`: shows total cost as primary metric (barMax $250k),
  Public/Private pill on browse cards, OOS badge in compare table, Best Value insight

After re-extraction, run `python refresh_db.py` and `cd web && npm run build` to push to production.

### Prompt Guardrails (added to 06_extract_data.py)

These rules exist because of specific failure modes observed in the 2026-03-14 audit:

1. **OOS preference** — State school pages show both rates; LLM was grabbing in-state first.
   Rule: extract OOS as primary, in-state as secondary.

2. **No-summing guard** — Three programs had costs calculated as in-state + OOS summed
   (e.g. $334,884 = $167k × 2). Side-by-side table columns look like addends.
   Rule: extract each column separately, never sum them.

3. **Range sanity** — Values like $633/yr (fees only) and $334,884 (summing error) weren't caught
   until manual audit. Rule: flag values outside plausible ranges in `notes` field, don't null them.

---

## Spot-Check Audit (2026-03-16) — In-State/OOS Re-extraction + Residency Leakage

After re-running `06_extract_data.py` with the hardened OOS-first prompt, coverage is now ~212/299
(71%) tuition. Spot-checking identified additional bad data and new next steps.

### Spot-Check Findings

**High outliers verified (>$70k/yr):**

| ID | School | Tuition/yr | Total | Status |
|----|--------|-----------|-------|--------|
| 35 | Boston University | $70,110 | $190,623 | CORRECT (within 3-5% of live page) |
| 74 | USC Hybrid DPT | $86,125 | $232,815 | CORRECT (2025 data, credible breakdown) |
| 64 | Pacific University CA | $73,731 | $158,258 | STALE — 2022-23, needs refresh |
| 217 | Pacific University OR | $74,469 | $165,065 | INCOMPLETE — Year 3 cost missing |
| 69 | USA Health (St Augustine CA) | $84,023 | $226,805 | UNVERIFIED — page 404'd |

**Public school in-state/OOS verified:**

| ID | School | In-State | OOS | Status |
|----|--------|---------|-----|--------|
| 72 | San Diego State | $28,434 | $47,334 | CORRECT — verified on live page (2025-26) |
| 53 | Arkansas State | per-credit $378 | — | CORRECT — verified on live page |
| 192 | Western Carolina NC | $8,154 | — | VALID but OOS rate not extracted — re-extract |

**Residency/fellowship leakage — NEW discoveries (programs to null in 07_audit_clean.py):**

These programs had residency/fellowship financial fact sheets extracted instead of DPT data.
All show suspiciously low total costs ($225–$9,557) that are only residency fees.

| ID | School | Bad Total | Root Cause |
|----|--------|-----------|------------|
| 128 | St Ambrose University IA | $9,557 | Orthopaedic/Fellowship fact sheet; malformed APTA URL |
| 141 | Franciscan U LA | $3,554 | SLU pt-residency-financial-factsheet.pdf |
| 162 | Maryville U MO | $5,331 | pt-residency-financial-factsheet.pdf |
| 172 | Creighton University NE | $225 | 25-26-financial-fact-sheet-Geri-Res.pdf (geriatric residency) |
| 202 | University of Toledo OH | $2,210 | residency-and-fellowship-financial-fact-sheet2024-2025-sports.pdf |
| 264 | UT Southwestern TX | $647 | Financial-Fact-Sheet-Nuero-PT-Residency.pdf |
| 272 | UTMB Galveston TX | $647 | Same neuro PT residency PDF |
| 276 | UT Southwestern variant | $647 | Same neuro PT residency PDF |
| 277 | UT Southwestern variant | $647 | Same neuro PT residency PDF |
| 297 | Carroll University WI | $8,000 | residency-financial-fact-sheet.pdf; length 27mo also wrong |

**Length anomaly confirmed via spot-check:**

| ID | School | CSV Length | Actual | Action |
|----|--------|-----------|--------|--------|
| 187 | Faulkner University AL | 28 months | ~48 months (8 semesters) | Null length |

---

### Next Steps (as of 2026-03-16)

**Step 1 — Add new residency rows to `07_audit_clean.py`:**

Add the following to the `CLEANUPS` list:

```python
# Group P: Residency/fellowship programs mistakenly extracted (spot-check 2026-03-16)
(128, True, False, True,  "St Ambrose: residency/fellowship fact sheet, not DPT; malformed APTA URL"),
(141, True, False, True,  "Franciscan U LA: SLU pt-residency fact sheet extracted, not DPT"),
(162, True, False, True,  "Maryville U MO: pt-residency fact sheet, not DPT"),
(172, True, False, True,  "Creighton NE: geriatric residency (Geri-Res) fact sheet, not DPT"),
(202, True, False, True,  "U Toledo OH: sports PT residency fact sheet, not DPT"),
(264, True, False, True,  "UT Southwestern TX: neuro PT residency fact sheet, not DPT"),
(272, True, False, True,  "UTMB Galveston TX: neuro PT residency fact sheet, not DPT"),
(276, True, False, True,  "UT Southwestern variant: neuro PT residency, not DPT"),
(277, True, False, True,  "UT Southwestern variant: neuro PT residency, not DPT"),
(297, True,  True, True,  "Carroll WI: residency financial fact sheet, not DPT; wrong length too"),
# Group Q: Length anomaly confirmed via spot-check
(187, False, True, False, "Faulkner AL: 28mo wrong; website shows 8 semesters (~48mo DPT)"),
```

**Step 2 — Add residency detection guardrail to SYSTEM_PROMPT in `06_extract_data.py`:**

```
RESIDENCY GUARD: If the page is clearly about a postgraduate residency or fellowship
program (not an entry-level DPT degree), return all fields as null and set
notes='RESIDENCY_SKIP: not entry-level DPT'.
```

This prevents future re-extraction from landing on residency pages after fact_sheet_url is cleared.

**Step 3 — Re-run cleanup and re-extract:**

```bash
# 1. Apply extended cleanup
python 07_audit_clean.py

# 2. Re-extract stale programs (Pacific CA 2022, USC main blank/2022, UPR 2019)
python 06_extract_data.py --stale-only

# 3. Re-extract specific problem programs
python 06_extract_data.py --program-ids 217,192

# 4. Check coverage
python -c "
import pandas as pd
df = pd.read_csv('output/pt_programs.csv')
df['tuition_per_year'] = pd.to_numeric(df['tuition_per_year'], errors='coerce')
print('tuition_per_year:', df['tuition_per_year'].notna().sum(), '/', len(df))
df['program_length_months'] = pd.to_numeric(df['program_length_months'], errors='coerce')
print('program_length_months:', df['program_length_months'].notna().sum(), '/', len(df))
"
```

**Target:** ≥230/299 (77%+) tuition coverage after this pass.

**Step 4 (optional P1) — Add cross-validation sanity check to `07_audit_clean.py`:**

Flag rows where `total_program_cost / (program_length_months / 12)` differs from
`tuition_per_year` by more than 40%. This catches future Carroll-style mismatches
($34,945/yr vs $8,000 total) before they ship to the DB.

### Programs Still Needing Manual Attention (as of 2026-03-16)

| ID | School | Issue |
|----|--------|-------|
| 64 | Pacific University CA | Stale 2022-23 data — re-extract should fix |
| 65 | USC main DPT | Blank / 2022 data — re-extract should fix |
| 217 | Pacific University OR | Year 3 cost missing — re-extract should fix |
| 299 | University of Puerto Rico | 2019-20 data — re-extract with newer fact sheet |
| 192 | Western Carolina NC | Only in-state extracted — re-extract for OOS |

---

## Audit + Prompt Hardening (2026-03-17) — ×12 Multiplication Bug + RANGE_WARN Fix

### Root Causes Found

**1. ×12 multiplication bug (6 rows confirmed)**
`total_program_cost` was being set to `tuition_per_year × 12` instead of `× years`. The SYSTEM_PROMPT
said "use `known_program_length_months/12`" — the LLM was using the months value (e.g., 36) as the
multiplier directly. One variant: the LLM treated an annual figure as per-semester and multiplied by
6 semesters (ratio = 6.0 exactly).

**2. RANGE_WARN never reached the CSV**
The LLM was correctly returning `notes='RANGE_WARN: ...'` for out-of-range values, but `build_update()`
in `06_extract_data.py` never read `result.notes` — it was silently discarded. The `extraction_notes`
column only received the strategy string (e.g., `"cost+len:apta_direct"`).

**3. 07_audit_clean.py is not safe to re-run**
The script replays ALL ~60 CLEANUPS entries every time. Of those, 39 rows had already been
successfully re-extracted after prior cleanup passes. Re-running would re-null all 39, triggering
another 130+ row processing cycle. Future one-off nulls must use targeted inline commands instead.

### Fixes Applied to `06_extract_data.py`

1. **RESIDENCY_SKIP guard** — added at top of SYSTEM_PROMPT. If the page is a residency/fellowship
   program, LLM returns all null and sets `notes='RESIDENCY_SKIP: not entry-level DPT'`.

2. **Years-explicit cost rules** — changed "use `known_program_length_months/12`" to "multiply by
   the X.X YEARS value from the hint, NOT the months value." Prevents ×12 confusion.

3. **CALC CHECK guard** — added after COST RULES: verifies `total / tuition ≈ program years (2–5)`.
   If ratio exceeds 6, LLM must recheck before returning.

4. **Length hint rewritten** — user message now leads with `X.X YEARS` and gives explicit multipliers:
   `"Per-year costs: multiply by 3.0. Per-semester costs: multiply by 6.0 semesters."`

5. **`result.notes` now written to CSV** — `build_update()` appends LLM `notes` to `extraction_notes`
   so RANGE_WARN and RESIDENCY_SKIP surface in the output file.

### Warning Added to `07_audit_clean.py`

Header now documents the re-run hazard. Groups R and S are added as commented entries only —
they were applied via targeted one-off null command.

### Rows Fixed This Session

| ID | School | Before | After |
|----|--------|--------|-------|
| 106 | Brenau GA | $180k total (×12 bug) | $40,240/yr, $139k total ✅ |
| 181 | Kean NJ | $396k total implausible | $38,565 OOS / $28,060 in-state, $108k ✅ |
| 185 | Alabama State | $22k in-state only | $32,960/yr, $94k total ✅ |
| 88 | U North Florida | $18k in-state only | $62,784/yr, $188k total ✅ |
| 192 | Western Carolina NC | $8k in-state only | $26,239 OOS / $9,959 in-state ✅ |
| 131 | Allen College | $14k bad | $31,358/yr, $118k total ✅ |
| 145 | U Maryland Eastern Shore | $16k in-state | $24,576/yr, $95k total ✅ |
| 231 | Misericordia PA | $207k (×12 bug) | $69,000/yr, $207k total — ratio 3.0 ✅ |
| 129 | Clarke IA | $306k (×12 bug) | $109,940 total (manual, from FPTA PDF) ✅ |

Rows nulled, awaiting next API run:

| ID | School | Issue |
|----|--------|-------|
| 211 | U Dayton OH | ratio=6.0 (annual treated as per-semester × 6); re-extract |
| 266 | UTEP TX | Extraction landed on a news article — wrong URL |
| 299 | UPR | 2021 PDF returns per-credit fees ($200), not tuition |
| 264 | UT Southwestern TX | No usable URL; HEERF page has no program data |
| 278 | U Utah | In-state $13,440 only; OOS total $120,670 — mixed data |

### Coverage After This Session

| Metric | Count | % |
|--------|-------|---|
| tuition_per_year | 232 / 299 | 77.6% |
| total_program_cost | 238 / 299 | 79.6% |
| program_length_months | 257 / 299 | 86.0% |
| tuition_instate populated | 24 / 299 | 8.0% |
| tuition_is_oos = yes | 22 / 299 | 7.4% |

Tuition range: min $10,000 / median $40,290 / max $86,125 (USC Hybrid, verified correct).
Ratio > 6 remaining: 1 row (U Utah 278 — in-state/OOS mismatch, not a bug).

### Programs Still Needing Attention

| ID | School | Issue |
|----|--------|-------|
| 211 | U Dayton OH | Re-extract with fixed prompt (ratio=6.0 bug) |
| 65 | USC main DPT | Re-extract to test RANGE_WARN fires at $95k+ |
| 266 | UTEP TX | Needs correct DPT program URL |
| 299 | U Puerto Rico | Needs post-2021 tuition source |
| 264 | UT Southwestern TX | No usable DPT URL found |
| 278 | U Utah | Mixed in-state/OOS — re-extract for OOS rate |
