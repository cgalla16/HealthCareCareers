# OT URL Discovery Agent

Finds two separate URLs per OT program:
- **A.4.2** — Outcomes page (cohort size, graduation rate, NBCOT pass rate)
- **A.4.4** — Tuition/cost page (cost of attendance, program fees)

Both pipelines are independent and can run simultaneously in separate terminals.

---

## Setup

```bash
pip install -r requirements.txt
```

Set your API keys. Or create a `.env` file in this directory:
```
SERPER_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
```

> Note: Must be exported in **each terminal** you run a script from. Or create a `.env` file:
> `echo "SERPER_API_KEY=your_key" > scrapers/ot/.env`

### Input CSVs

`input_outcomes.csv` → loaded into `output/ot_outcomes_urls.csv`
`input_financial.csv` → loaded into `output/ot_tuition_urls.csv`

| Column | Required | Description |
|--------|----------|-------------|
| `program_id` | ✅ | Unique ID from your DB |
| `school_name` | ✅ | Full school name |
| `city` | ✅ | City |
| `state` | ✅ | State abbreviation |
| `degree_type` | ✅ | `MOT` or `OTD` — different products |
| `program_url` | optional | Program's main website |

---

## Running the Pipeline

```bash
# Step 1 — Load both CSVs
python 01_load_programs.py

# Step 2a — Find outcomes pages — run in terminal 1
python 02_discover_outcomes_urls.py

# Step 2b — Find tuition pages — run in terminal 2 simultaneously
python 03_discover_tuition_urls.py

# Step 3 — Review summary + export review files
python 04_export_review.py

# Step 4 — After filling in manual_url in review CSVs
python 05_apply_manual.py

# Step 5 — Validate URLs with Claude Haiku (run once per pipeline)
python 06_validate_urls.py --pipeline outcomes
python 06_validate_urls.py --pipeline tuition

# Step 6 — Re-discover rejected URLs with Claude Sonnet
python 07_rediscover_rejected.py --pipeline outcomes
python 07_rediscover_rejected.py --pipeline tuition

# Step 7 — Re-validate newly discovered URLs
python 06_validate_urls.py --pipeline outcomes
python 06_validate_urls.py --pipeline tuition
```

### Options (same for both discovery scripts)
```bash
--limit 10           # test on first 10 rows only
--retry-notfound     # also retry url_not_found rows
--force              # re-run everything including url_found
```

---

## Output Files

| File | Description |
|------|-------------|
| `output/ot_outcomes_urls.csv` | A.4.2 outcomes page URLs — **never delete** |
| `output/ot_tuition_urls.csv` | A.4.4 tuition page URLs — **never delete** |
| `output/ot_outcomes_review.csv` | Outcomes rows needing manual review |
| `output/ot_tuition_review.csv` | Tuition rows needing manual review |

### Output CSV columns
| Column | Description |
|--------|-------------|
| `program_id` | DB ID |
| `school_name`, `city`, `state`, `degree_type` | Program info |
| `discovered_url` | Best URL found |
| `discovered_url_2` | Second-best result (backup) |
| `url_confidence` | `high` / `medium` / `low` / `manual` |
| `url_status` | See status values below |
| `estimated_year` | Year extracted from URL (e.g. `2024`) — blank if none found |
| `search_query_used` | Which query produced the result |
| `search_attempts` | How many queries were tried |
| `scrape_notes` | Errors or warnings |
| `validation_status` | `valid` / `rejected` / `fetch_failed` / `llm_error` |
| `rejection_reason` | Why the URL was rejected |
| `rediscovery_status` | `found` / `not_found` (set by Step 6) |

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
| `pending` | Not yet searched |
| `url_found` | High or medium confidence — ready for Stage 2 |
| `url_found_low_confidence` | Found but uncertain — review recommended |
| `url_not_found` | All queries returned nothing useful |
| `search_exhausted` | Hit 3-attempt max |
| `manual_override` | Human-verified URL |
| `error` | Network/API error — auto-retried next run |

### To start completely fresh
```bash
rm output/ot_outcomes_urls.csv output/ot_tuition_urls.csv
python 01_load_programs.py
```

---

## Search Query Cascades

`{degree_type}` is `MOT` or `OTD` — pulled per-row from the CSV, making queries program-specific.

### Outcomes
1. `{school_name} {degree_full} Publication of Program Outcomes`
2. `{school_name} {degree_full} program outcomes cohort graduation rate`
3. `{school_name} {degree_type} ACOTE outcomes data`

### Tuition
1. `{school_name} {degree_full} tuition cost of attendance`
2. `{school_name} {degree_full} program cost fees`
3. `{school_name} {degree_type} tuition fees cost`

`{degree_full}` expands to the full degree name (e.g. "Master of Occupational Therapy") for better search targeting. `{degree_type}` is the abbreviation (`MOT` or `OTD`).

## Scoring Rules

- Result with **no school name** in domain or URL path: capped at `medium` (prevents false matches from other schools' pages)
- URL containing a **year before 2023**: capped at `low` (stale data — forces manual review)
- PDF files get a score boost (ACOTE disclosures are often PDFs)
- Aggregator sites (US News, LinkedIn, Indeed, etc.) are excluded entirely

---

## Cost Estimate

~270 OT schools × 2 pipelines × up to 3 queries = ~1,600 searches worst case.
Combined with PT's ~900 searches, total = ~2,500 — right at Serper's free limit.

**Recommendation:** Sign up for both Serper (2,500 free) and Scrapingdog (11,000 free, no CC).
Use Serper for PT, Scrapingdog for OT — total cost: **$0**.

To use Scrapingdog instead of Serper, change in `.env`:
```
SCRAPINGDOG_API_KEY=your_key_here
```
And update `shared_search.py` → `serper_search()` to use Scrapingdog's endpoint.

---

## Handoff to Stage 2

```python
import pandas as pd

outcomes = pd.read_csv("output/ot_outcomes_urls.csv")
tuition = pd.read_csv("output/ot_tuition_urls.csv")

# Merge on program_id for programs that have BOTH URLs
ready_outcomes = outcomes[outcomes["url_status"].isin(["url_found", "manual_override"])]
ready_tuition = tuition[tuition["url_status"].isin(["url_found", "manual_override"])]

stage2 = ready_outcomes[["program_id", "school_name", "degree_type", "discovered_url"]].rename(
    columns={"discovered_url": "outcomes_url"}
).merge(
    ready_tuition[["program_id", "discovered_url"]].rename(
        columns={"discovered_url": "tuition_url"}
    ),
    on="program_id",
    how="outer"
)

stage2.to_csv("ot_stage2_input.csv", index=False)
print(f"{len(stage2)} programs ready for Stage 2")
```
