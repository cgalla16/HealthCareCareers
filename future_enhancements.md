# Healthcare Dashboard: Feature & Data Extraction Roadmap

## Context
The platform helps healthcare students make informed program decisions. Three pages are live and polished (map, career overview, program comparison). The core gap is **data depth**: the comparison table has scaffolded cost/length columns showing "Coming soon" because the underlying extraction pipelines are incomplete. This plan completes those pipelines, fixes known data accuracy issues, adds key architecture improvements, and organizes all work into independent parallel streams with zero file conflicts.

---

## Current State Assessment

| Data Type | PT | OT | RT | SLP |
|-----------|----|----|----|----|
| BLS salary + work settings | ✓ | ✓ | ✓ | ✓ |
| Program list in DB | ✓ 299 | ✓ 272 | ❌ | ❌ |
| Board pass rates | ✓ FPTA | ✓ NBCOT | ❌ | ❌ |
| Program cost | **78–81% extracted** | 0% | ❌ | ❌ |
| Program length | **86% extracted** | 0% | ❌ | ❌ |
| Growth rate | ❌ hardcoded 10% | ❌ 10% | ❌ -2% actual | ❌ 10% |

**Key findings:**
- PT pipeline is in excellent shape: 86% length, 78–81% cost extracted. Only **23 AUDIT_CLEARED rows** remain pending re-extraction (not 56 as previously estimated)
- OT URL discovery has a 77% rejection rate caused by Keiser University OTA PDFs contaminating Serper results; the fix is the ACOTE directory approach (no API needed)
- BLS OOH real growth rates: PT 14%, OT 12%, RT **-2%** (currently showing 10% — a credibility bug), SLP 19%
- RT/SLP program data: no centralized public data source equivalent to FPTA/NBCOT; low ROI relative to effort
- College Scorecard script ran only ~72/430 schools due to rate limiting; needs a background rerun

---

## Priority Matrix

| Item | User Value | Effort | Blocker |
|------|-----------|--------|---------|
| BLS growth rates (fix -2% RT bug) | **HIGH** | Low (15 lines) | None |
| PT audit finish + DB load | **HIGH** | Low (run scripts) | Run `09_audit_clean.py` then `08_extract_data.py` |
| OT URL fix (ACOTE directory) | **HIGH** | Med (new script) | None |
| OT cost/length extraction | **HIGH** | High (port of PT's 08) | OT URL fix |
| URL-based comparison sharing | **HIGH** | Med | None |
| Individual program pages `/programs/[id]` | Med | Med | Benefits from PT data |
| School Type filter in Browse | Med | Low | None |
| College Scorecard completion | Med | Low (rerun script) | API key in env |
| SLP program data | Low | Very High | No centralized source |
| RT program data | Low | High | No public accreditor mandate |

---

## Parallel Work Streams

> Each stream touches a distinct set of files — all can be assigned to separate agents and run simultaneously with zero conflicts.

---

### Stream A — BLS Growth Rates Fix
**Time estimate**: 1 hour
**Value**: High — RT currently shows +10% when real rate is -2%; credibility bug

**Design**: `bls_growth_pct` already exists in `occupation_national_stats` — no schema change needed. The issue is `_insert_national_stats()` in `work_settings.py` uses `INSERT OR IGNORE`, so re-runs never overwrite the hardcoded `10.0`. The fix: add a CSV-driven UPDATE pass that runs after `work_settings.py` creates the rows.

**Step 1 — Create source data file** (`raw/bls_ooh_projections.csv`):
```csv
occupation_name,bls_growth_pct,projection_period,source_url
Physical Therapists,14.0,2023-2033,https://www.bls.gov/ooh/healthcare/physical-therapists.htm
Occupational Therapists,12.0,2023-2033,https://www.bls.gov/ooh/healthcare/occupational-therapists.htm
Radiation Therapists,-2.0,2023-2033,https://www.bls.gov/ooh/healthcare/radiation-therapists.htm
Speech-Language Pathologists,19.0,2023-2033,https://www.bls.gov/ooh/healthcare/speech-language-pathologists.htm
```
This file is the single source of truth — update it when BLS releases new projections (every 2 years) and rerun `refresh_db.py`.

**Step 2 — Add OOH load function to `db/pipelines/occupations.py`**:
- Add `load_ooh_projections(con)` that reads `raw/bls_ooh_projections.csv`
- For each row, runs:
  ```sql
  UPDATE occupation_national_stats
  SET bls_growth_pct = ?
  WHERE occupation_id = (SELECT id FROM occupations WHERE name = ?)
  ```
- Uses UPDATE (not INSERT) so it always overwrites the placeholder `10.0` from `work_settings.py`
- Prints a warning if the CSV row's occupation name doesn't match any DB row (typo guard)

**Step 3 — Call it from `db/pipeline.py`** after `work_settings.load()`:
- `work_settings.load(con)` creates the `occupation_national_stats` rows (with placeholder 10.0)
- `occupations.load_ooh_projections(con)` immediately overwrites `bls_growth_pct` with CSV values

**Files touched**:
- New: `raw/bls_ooh_projections.csv` — source data (version-controlled, easy to update)
- `db/pipelines/occupations.py` — add `load_ooh_projections(con)` function
- `db/pipeline.py` — call `occupations.load_ooh_projections(con)` after `work_settings.load(con)`

**Verify**: Run `python refresh_db.py` → open `/careers/radiation-therapists` → KPI shows "-2%" not "10%"

---

### Stream B — PT Data Pipeline Completion
**Time estimate**: ~1 hour total (23 rows × ~2 min/row LLM run + DB rebuild)
**Value**: High — activates "Total Cost" and "Program Length" columns for ~280+ PT programs immediately, with the last ~19 rows filling in after re-extraction

**Step 1 — Finish audit** (`scrapers/pt/09_audit_clean.py`):
- Review current CLEANUPS list; verify program IDs 25, 88, 191, 129 are handled
- ID 129 (Clarke, $102k flagged): check `apta_program_url` to confirm before nulling
- Run `python 09_audit_clean.py` — nulls the remaining bad rows, sets `extraction_notes = "AUDIT_CLEARED"`

**Step 2 — Re-extract cleared rows** (`scrapers/pt/08_extract_data.py`):
- Run `python 08_extract_data.py` — script already re-processes rows where `cost_basis` is empty
- Only **23 AUDIT_CLEARED rows** remain — expect ~30–45 min run time

**Step 3 — Verify and load**:
- Spot-check `output/pt_programs.csv` for any remaining outliers
- Run `python refresh_db.py` from project root
- `clean_pt()` in `db/pipelines/schools.py` (lines 92–113) already merges scraper cost data — no code changes needed

**Step 4 — Verify UI** (no code changes):
- `ProgramComparison.jsx` already shows real values when `p.cost` / `p.lengthMonths` are non-null

**Files touched**: `scrapers/pt/09_audit_clean.py` (review/add rows), run scripts, run `refresh_db.py`

---

### Stream C — OT URL Fix (ACOTE Directory Approach)
**Time estimate**: 4–6 hours
**Value**: High — unblocks OT cost/length extraction for 272 programs

**Root cause**: Serper returns Keiser University OTA (associate-level) PDFs for ~29+ OT program searches. Secondary: wrong-school pages score high because `shared_search.py` rewards URL keywords without requiring school name match.

**Step 1 — Blocklist patch** (`scrapers/ot/shared_search.py`):
- Add Keiser OTA PDF URL and Milwaukee Area Technical College OTA PDF to `EXCLUDED_DOMAINS`
- Add `"ota"` to `NEGATIVE_URL_PATTERNS` (any URL containing `/ota/` or `ota-program` → score -2.0)

**Step 2 — Build ACOTE directory scraper** (new file: `scrapers/ot/08_parse_acote_directory.py`):
- Pattern: direct port of `scrapers/pt/07_parse_apta_directory.py`
- Fetch `https://acoteonline.org/accredited-programs/` (static HTML, no JS render needed — verify before building)
- Parse MOT and OTD entries only (skip OTA rows — critical filter)
- Fuzzy-match against `input_outcomes.csv` school names using `difflib.get_close_matches`
- Write `program_url` into both `ot_outcomes_urls.csv` and `ot_tuition_urls.csv` for matched rows
- Output: `ot_url_map.csv` (matched) + `ot_url_map_unmatched.csv` (for manual review)

**Step 3 — Run rediscovery with clean URLs**:
- Run `python 07_rediscover_rejected.py` for both outcomes and tuition pipelines
- The script already uses `program_url` as its starting point when available
- Let run unattended (~2–4 hours for 154 rejected rows)

**Step 4 — Validate and run extract** (depends on Step 3 results):
- Run `python 06_validate_urls.py` for both pipelines
- Build `scrapers/ot/09_extract_data.py` (port of `scrapers/pt/08_extract_data.py`) with OT-specific changes:
  - Dual URL inputs: `ot_tuition_urls.csv` (tuition) + `ot_outcomes_urls.csv` (outcomes)
  - Degree-type awareness: MOT ~2yr ($20–60k/yr), OTD ~3yr ($25–80k/yr)
  - No CAPTE fact sheets — heavier reliance on sub-page discovery
  - Adjust `RANGE_WARN` thresholds in system prompt accordingly

**Step 5 — DB integration** (`db/pipelines/schools.py`):
- Add scraper-data merge block to `clean_ot()` (currently at line ~192), mirroring the PT merge at lines 92–113
- Join on `school_name + state`, pull: `program_length_months`, `tuition_per_year`, `tuition_instate`, `tuition_is_oos`, `total_program_cost`

**Files touched**:
- `scrapers/ot/shared_search.py` — blocklist additions
- New: `scrapers/ot/08_parse_acote_directory.py`
- New: `scrapers/ot/09_extract_data.py`
- `db/pipelines/schools.py` — add OT scraper merge to `clean_ot()`

---

### Stream D — UI Architecture Improvements
**Time estimate**: 4–6 hours
**Value**: High (sharing) + Medium (program pages, filter)

#### D1: URL-Based Comparison Sharing (`web/components/ProgramComparison.jsx`)
**Why**: Users cannot share comparisons — a critical gap for a comparison tool.

- Add `useSearchParams()` and `useRouter()` hooks
- On mount: read `?career=PT&ids=14,87,203` and pre-populate `selectedCareer` + `selected[]`
- On state change: call `router.replace()` with updated params (shallow, no navigation)
- No server changes needed

#### D2: Individual Program Pages (new: `web/app/programs/[id]/page.jsx`)
- Server component with `generateStaticParams` over all program IDs
- New query: `getProgram(id)` in `web/lib/db.js` — full program row + `school_scorecard` join
- Display: school name, city/state, degree type, tuition breakdown (OOS vs in-state), pass rate, program length, `school_url` from scorecard (direct link to program website), area salary context
- Add "View details →" link from `BrowseCard` in `ProgramComparison.jsx`
- Build PT first (most complete data), OT scaffold follows

#### D3: School Type Filter in Browse (`web/components/ProgramComparison.jsx`)
- `school_scorecard.ownership` is already joined in `getPrograms()` and exposed as `p.schoolType`
- Add School Type dropdown (`All / Public / Private`) to `FilterBar`
- ~15-line change in `FilterBar` and `filtered` derivation

**Files touched** (all in `web/`):
- `web/components/ProgramComparison.jsx` — URL sync + school type filter + "View details" link
- `web/lib/db.js` — add `getProgram(id)` query
- New: `web/app/programs/[id]/page.jsx`

---

### Stream E — College Scorecard Completion (Background)
**Time estimate**: Background (1–2 days unattended)
**Value**: Medium — currently ~82% match rate but only ~72 schools scraped

- Set `SCORECARD_API_KEY` env var in shell
- Run `python scripts/explore_scorecard.py` — resume-capable, rate-limited to 1000/hr
- Output appends to `data/scorecard_exploration.csv`
- After completion, run `python refresh_db.py` to update `school_scorecard` table
- No code changes needed

**Files touched**: none (script runs as-is)

---

## Architecture Notes

### Not Recommended Now
- **ISR (Incremental Static Regeneration)**: Requires Vercel or Node runtime. Premature until deployment target is decided. Static build is correct for current local/dev use.
- **SLP program data**: ASHA CAA does not publish centralized pass rate CSVs. Program-level data would require scraping ~300 individual school websites with no standardized format. Effort is Very High, ROI is Low.
- **RT program data**: JRCERT data accessibility is unclear; RT is the smallest career (~17k employed). Defer.

### Recommended for Later (Post-Stream D)
- **Dark mode toggle**: CSS vars are already defined in `layout.jsx` — add a toggle button to `SiteNav.jsx` and a `prefers-color-scheme` media query
- **Print-friendly styles**: CSS `@media print` in `layout.jsx` for program comparison exports

---

## Recommended Execution Order

**Phase 1 (immediate, parallel):**
- Agent 1 → Stream A (BLS growth rates, ~1 hour)
- Agent 2 → Stream B (PT audit + re-extraction, ~1 hour including run time)
- Agent 3 → Stream D1 + D3 (URL sharing + school type filter, ~3 hours)
- Background → Stream E (Scorecard rerun, start and leave)

**Phase 2 (after Stream B runs):**
- Agent 4 → Stream D2 (individual program pages — benefits from PT cost data in DB)

**Phase 3 (after Stream C URL fix runs):**
- Agent 5 → Stream C extraction scripts + DB integration (OT 09_extract_data.py + schools.py merge)

---

## Verification

- **Stream A**: Open `/careers/radiation-therapists` → confirm KPI shows "-2%" not "10%"
- **Stream B**: Open `/programs` → filter to PT → verify cost and length show real values (not "Coming soon") for majority of programs
- **Stream C**: After OT extraction + DB load → open `/programs` → filter to OT → verify cost/length populate
- **Stream D1**: Navigate to `/programs?career=PT&ids=1,2` → confirm programs pre-selected
- **Stream D2**: Click "View details" on a PT card → confirm `/programs/[id]` renders with tuition, pass rate, school link
- **Stream D3**: Open Browse step → confirm Public/Private filter narrows results correctly
- **All**: Run `python refresh_db.py` and `cd web && npm run build` without errors
