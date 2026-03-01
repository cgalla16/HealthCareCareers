# Healthcare Occupation Salary Explorer

An interactive data visualization dashboard that maps US healthcare occupation salaries by state, built with Streamlit and Plotly. Data sourced from the **Bureau of Labor Statistics (BLS) May 2024** Occupational Employment and Wage Statistics.

---

## Product Overview

### What It Does
Users can explore how salaries for specific healthcare occupations vary across all 50 US states (plus DC and Puerto Rico) through an interactive choropleth map. Hovering over any state reveals the annual mean wage, annual median wage, and total number of employees in that state for the selected occupation.

### Current Occupations Covered
- Occupational Therapists
- Physical Therapists
- Radiation Therapists
- Speech-Language Pathologists

### Key Features
- **Interactive US map** — color-coded by annual mean wage (Blues scale, min-to-max range per occupation)
- **Sidebar occupation selector** — radio toggle to switch between occupation types
- **Rich hover tooltips** — Annual Mean Wage (formatted), Annual Median Wage, and Employee count per state
- **Missing data callout** — states with no BLS data are shown in gray with a caption listing them by name
- **Cached queries** — Streamlit's `@st.cache_data` prevents redundant database reads on re-renders

### Current Build Status
> MVP with 4 occupations and choropleth map. Refactored into module directories.
> Pending: growth rate data, field landing pages, percentile charts, field comparison view.

---

## Technical Overview

### Architecture

```
raw/*.xlsx  (BLS source files)
      │
      ▼
db/pipeline.py              ← cleans xlsx → writes data/*.csv → builds healthcare.db
      │                         (falls back to existing CSVs if no xlsx present)
      ├── data/*.csv          ← intermediate, auditable cleaned CSVs
      │
      ▼
healthcare.db               ← SQLite database (3 tables)
      │
      ▼
db/queries.py               ← cached data layer (pandas + sqlite3)
      │
      ▼
viz/map.py                  ← Plotly choropleth builder
      │
      ▼
app.py                      ← Streamlit entry point (UI + wiring)
```

### File Structure

```
app.py                       # Streamlit entry point
refresh_db.py                # thin wrapper → calls db/pipeline.py
requirements.txt

healthcare.db                # SQLite DB (generated, not committed)
raw/                         # input BLS xlsx files (drop new files here)
data/                        # cleaned intermediate CSVs (auditable, one per occupation)

constants/
    states.py                # STATE_ABBREVS dict (full name → 2-letter abbreviation)

db/
    queries.py               # load_data() — cached SQL query via pandas
    pipeline.py              # full ETL: xlsx → cleaned CSV → DB

viz/
    map.py                   # choropleth builder (setup_page, build_map, render_map, show_missing_note)
    charts.py                # placeholder for future percentile charts
```

### Module Responsibilities

| File | Role |
|------|------|
| [app.py](app.py) | Main Streamlit entry point — page setup, sidebar filter, data load, map render |
| [refresh_db.py](refresh_db.py) | Thin CLI wrapper — calls `db/pipeline.main()` |
| [db/pipeline.py](db/pipeline.py) | Full ETL — reads xlsx from `raw/`, cleans data, writes CSVs, builds SQLite DB |
| [db/queries.py](db/queries.py) | Cached SQL query — returns a `DataFrame` with state abbrev and formatted wage columns |
| [viz/map.py](viz/map.py) | Plotly choropleth figure builder and Streamlit rendering helpers |
| [constants/states.py](constants/states.py) | Static dict mapping full state names → 2-letter USPS abbreviations (52 entries) |
| [requirements.txt](requirements.txt) | Python dependencies |

### Database Schema

**`states`**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| name | TEXT UNIQUE | Full state name (e.g., "California") |

**`occupations`**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| name | TEXT UNIQUE | Occupation label (e.g., "Physical Therapists") |

**`employment_stats`**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| state_id | INTEGER FK | → states.id |
| occupation_id | INTEGER FK | → occupations.id |
| number_of_employees | REAL | |
| hourly_mean_wage | REAL | |
| annual_mean_wage | REAL | Primary map color dimension |
| hourly_10th/25th/75th/90th_percentile_wage | REAL | Full wage distribution |
| annual_10th/25th/75th/90th_percentile_wage | REAL | Full wage distribution |
| annual_median_wage | REAL | Shown in hover tooltip |
| employment_per_1000_jobs | REAL | BLS location metric |
| location_quotient | REAL | BLS concentration metric |

Unique constraint on `(state_id, occupation_id)`. Current DB: **52 states, 4 occupations, 204 rows**.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| UI / App framework | [Streamlit](https://streamlit.io/) >= 1.32 |
| Visualization | [Plotly Express](https://plotly.com/python/plotly-express/) >= 5.20 |
| Data manipulation | [pandas](https://pandas.pydata.org/) >= 2.0 |
| Database | SQLite (stdlib `sqlite3`) |
| Excel parsing | openpyxl >= 3.1 |
| Language | Python 3.11+ |

### Setup & Running

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Drop BLS xlsx files into raw/ then build the database
#    (falls back to existing CSVs in data/ for any occupation without a new xlsx)
python refresh_db.py

# 3. Launch the app
python -m streamlit run app.py
```

---

## Data Source & ETL

**Bureau of Labor Statistics — Occupational Employment and Wage Statistics (OEWS)**
- Survey period: May 2024
- Coverage: US states, DC, and Puerto Rico
- Source files: BLS xlsx downloads, placed in `raw/` (one per occupation)

### ETL Pipeline (`db/pipeline.py`)

Each xlsx file goes through the following cleaning steps before being written to `data/*.csv` and loaded into the DB:

1. **Skip BLS metadata rows** — rows 1–5 are header/metadata; row 6 contains column headers
2. **Drop RSE columns** — relative standard error columns are removed
3. **Strip footnote markers** — e.g., `"Annual mean wage (2)"` → `"Annual mean wage"`
4. **Normalize state names** — e.g., `"Alabama (01-00000)"` → `"Alabama"`; non-state rows are dropped
5. **Replace suppression markers** — BLS `(8)` and `*` values replaced with `NaN`
6. **Coerce to numeric** — all data columns cast to float; unparseable values become `NaN`

### Data Columns Ingested

| Cleaned BLS Column | DB Column |
|--------------------|-----------|
| Number of Employees | number_of_employees |
| Hourly mean wage | hourly_mean_wage |
| Annual mean wage | annual_mean_wage |
| Hourly 10th/25th/75th/90th percentile wage | hourly_*_percentile_wage |
| Annual 10th/25th/75th/90th percentile wage | annual_*_percentile_wage |
| Annual median wage | annual_median_wage |
| Employment per 1,000 jobs | employment_per_1000_jobs |
| Location Quotient | location_quotient |

### Adding a New Occupation

1. Download the BLS OES xlsx for the occupation
2. Name it consistently (e.g., `PhysicalTherapists.xlsx`) and drop it into `raw/`
3. Add an entry to `FILES` in [db/pipeline.py](db/pipeline.py) and to `OCCUPATIONS` in [app.py](app.py)
4. Run `python refresh_db.py`

---

## Roadmap / Planned Improvements

- [ ] Percentile wage distribution charts per state (viz/charts.py)
- [ ] Field landing pages — deep-dive view per occupation
- [ ] Field comparison view — side-by-side salary across occupations
- [ ] Growth rate data overlay (BLS employment projections)
- [ ] Year-over-year salary comparison (multi-year BLS data)
- [ ] Wage range filter in sidebar
- [ ] Export to CSV from UI
- [ ] Deployment (Streamlit Community Cloud or similar)
