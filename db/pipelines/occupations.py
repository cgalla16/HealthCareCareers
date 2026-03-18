"""
db/pipelines/occupations.py — BLS OEWS xlsx → cleaned CSVs → DB tables

Expects xlsx files in:  raw/occupations/
Outputs cleaned CSVs to: data/occupations/
Writes to tables:        states, occupations, employment_stats
"""

import re
import sqlite3
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

from constants.states import STATE_ABBREVS

PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DIR      = PROJECT_ROOT / "raw"  / "occupations"
DATA_DIR     = PROJECT_ROOT / "data" / "occupations"
DB_PATH      = PROJECT_ROOT / "healthcare.db"

KNOWN_STATES = set(STATE_ABBREVS.keys())

FILES = {
    "Occupational Therapists":      "OccupationalTherapists",
    "Physical Therapists":          "PhysicalTherapists",
    "Radiation Therapists":         "RadiationTherapists",
    "Speech-Language Pathologists": "SpeechLanguagePathologists",
}

COL_MAP = {
    "Number of Employees":          "number_of_employees",
    "Hourly mean wage":             "hourly_mean_wage",
    "Annual mean wage":             "annual_mean_wage",
    "Hourly 10th percentile wage":  "hourly_10th_percentile_wage",
    "Hourly 25th percentile wage":  "hourly_25th_percentile_wage",
    "Hourly median wage":           "hourly_median_wage",
    "Hourly 75th percentile wage":  "hourly_75th_percentile_wage",
    "Hourly 90th percentile wage":  "hourly_90th_percentile_wage",
    "Annual 10th percentile wage":  "annual_10th_percentile_wage",
    "Annual 25th percentile wage":  "annual_25th_percentile_wage",
    "Annual median wage":           "annual_median_wage",
    "Annual 75th percentile wage":  "annual_75th_percentile_wage",
    "Annual 90th percentile wage":  "annual_90th_percentile_wage",
    "Employment per 1,000 jobs":    "employment_per_1000_jobs",
    "Location Quotient":            "location_quotient",
}


def strip_footnote_markers(col: str) -> str:
    return re.sub(r"\s*\(\d+\)\s*$", "", str(col)).strip()


def clean_xlsx(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, skiprows=5, engine="openpyxl")

    rse_cols = [c for c in df.columns if "relative standard error" in str(c).lower()]
    df = df.drop(columns=rse_cols)

    df.columns = [strip_footnote_markers(c) for c in df.columns]

    state_col = df.columns[0]
    df = df.rename(columns={state_col: "States"})
    df["States"] = df["States"].astype(str).str.extract(r"^([^(]+)")[0].str.strip()

    df = df[df["States"].isin(KNOWN_STATES)].reset_index(drop=True)

    emp_col = next(
        (c for c in df.columns if c.startswith("Employment") and "per" not in c.lower()),
        None,
    )
    if emp_col and emp_col != "Number of Employees":
        df = df.rename(columns={emp_col: "Number of Employees"})

    df = df.replace(r"^\(8\).*$", float("nan"), regex=True)
    df = df.replace("*", float("nan"))

    for col in df.columns:
        if col != "States":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _create_schema(cur) -> None:
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS states (
            id   INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS occupations (
            id   INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS employment_stats (
            id                          INTEGER PRIMARY KEY,
            state_id                    INTEGER NOT NULL REFERENCES states(id),
            occupation_id               INTEGER NOT NULL REFERENCES occupations(id),
            number_of_employees         REAL,
            hourly_mean_wage            REAL,
            annual_mean_wage            REAL,
            hourly_10th_percentile_wage REAL,
            hourly_25th_percentile_wage REAL,
            hourly_median_wage          REAL,
            hourly_75th_percentile_wage REAL,
            hourly_90th_percentile_wage REAL,
            annual_10th_percentile_wage REAL,
            annual_25th_percentile_wage REAL,
            annual_median_wage          REAL,
            annual_75th_percentile_wage REAL,
            annual_90th_percentile_wage REAL,
            employment_per_1000_jobs    REAL,
            location_quotient           REAL,
            UNIQUE (state_id, occupation_id)
        );
    """)


def _insert_dfs(cur, con, dfs: dict) -> None:
    all_states = sorted({s for df in dfs.values() for s in df["States"].tolist()})
    for state in all_states:
        cur.execute("INSERT OR IGNORE INTO states (name) VALUES (?)", (state,))

    for occupation in dfs:
        cur.execute("INSERT OR IGNORE INTO occupations (name) VALUES (?)", (occupation,))

    con.commit()

    stat_cols = list(COL_MAP.values())
    total_rows = 0

    for occupation, df in dfs.items():
        df_mapped = df.rename(columns=COL_MAP)
        occ_id = cur.execute(
            "SELECT id FROM occupations WHERE name = ?", (occupation,)
        ).fetchone()[0]

        for _, row in df_mapped.iterrows():
            state_id = cur.execute(
                "SELECT id FROM states WHERE name = ?", (row["States"],)
            ).fetchone()[0]

            values = [state_id, occ_id] + [
                None if pd.isna(row[c]) else row[c] for c in stat_cols
            ]
            cur.execute(
                f"""
                INSERT INTO employment_stats
                    (state_id, occupation_id, {', '.join(stat_cols)})
                VALUES
                    ({', '.join(['?'] * (2 + len(stat_cols)))})
                """,
                values,
            )
            total_rows += 1

    con.commit()
    print(f"  {len(all_states)} states, {len(dfs)} occupations, {total_rows} employment_stats rows")


def build_db(dfs: dict) -> None:
    """Build the DB from DataFrames directly. Used by tests and standalone runs."""
    if DB_PATH.exists():
        DB_PATH.unlink()

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    _create_schema(cur)
    _insert_dfs(cur, con, dfs)
    con.close()


def _read_files() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dfs = {}
    for occupation, stem in FILES.items():
        xlsx_path = RAW_DIR / f"{stem}.xlsx"
        csv_path  = DATA_DIR / f"{stem}.csv"

        if xlsx_path.exists():
            print(f"  [READ] {xlsx_path}")
            df = clean_xlsx(xlsx_path)
            df.to_csv(csv_path, index=False)
            print(f"         -> {csv_path} ({len(df)} rows)")
        elif csv_path.exists():
            print(f"  [CSV]  {csv_path} (no xlsx, using existing CSV)")
            df = pd.read_csv(csv_path)
            df.columns = [strip_footnote_markers(c) for c in df.columns]
        else:
            print(f"  [SKIP] {stem} - no xlsx in raw/occupations/ and no CSV in data/occupations/")
            continue

        dfs[occupation] = df
    return dfs


OOH_PATH = PROJECT_ROOT / "raw" / "bls_ooh_projections.csv"


def load_ooh_projections(con) -> None:
    """
    Update bls_growth_pct in occupation_national_stats from raw/bls_ooh_projections.csv.

    Must be called AFTER work_settings.load() has created the occupation_national_stats rows.
    Uses UPDATE (not INSERT) so it always overwrites the placeholder 10.0.
    To refresh projections: edit raw/bls_ooh_projections.csv and rerun refresh_db.py.
    """
    if not OOH_PATH.exists():
        print(f"  [SKIP] bls_ooh_projections.csv not found at {OOH_PATH}")
        return

    df = pd.read_csv(OOH_PATH)
    cur = con.cursor()
    updated = 0

    for _, row in df.iterrows():
        result = cur.execute(
            """
            UPDATE occupation_national_stats
            SET bls_growth_pct = ?
            WHERE occupation_id = (SELECT id FROM occupations WHERE name = ?)
            """,
            (float(row["bls_growth_pct"]), str(row["occupation_name"])),
        )
        if result.rowcount == 0:
            print(f"  [WARN] bls_ooh_projections: no DB row for '{row['occupation_name']}' — skipped")
        else:
            updated += 1

    con.commit()
    print(f"  [OOH]  Updated bls_growth_pct for {updated} occupations from {OOH_PATH.name}")


def load(con) -> None:
    """Load occupation data into a provided DB connection. Used by the orchestrator."""
    cur = con.cursor()
    _create_schema(cur)
    dfs = _read_files()
    if not dfs:
        print("  No occupation data found.")
        return
    _insert_dfs(cur, con, dfs)
