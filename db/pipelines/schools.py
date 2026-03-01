"""
db/pipelines/schools.py — School program CSVs → DB tables

Expects CSVs in:         raw/schools/<occupation>/
Outputs cleaned CSVs to: data/schools/<occupation>/
Writes to tables:        schools, programs

Adding a new occupation:
  1. Create raw/schools/<key>/ and drop CSVs there
  2. Write a clean_<key>(raw_dir: Path) -> pd.DataFrame normalizer below
  3. Add an entry to NORMALIZERS

  For occupations whose data comes from a single fixed file (e.g. NBCOT),
  set the third tuple element to the Path of that file instead of None.
  The normalizer's raw_dir arg will point to that file's parent directory.
"""

import re
from pathlib import Path

import pandas as pd

from constants.states import STATE_ABBREVS

PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DIR      = PROJECT_ROOT / "raw"  / "schools"
DATA_DIR     = PROJECT_ROOT / "data" / "schools"

ABBREV_TO_STATE = {v: k for k, v in STATE_ABBREVS.items()}

# Fixed-location source files (not under raw/schools/)
NBCOT_CSV = PROJECT_ROOT / "raw" / "nbcot_pass_rates_2024.csv"


# ---------------------------------------------------------------------------
# PT normalizer
# ---------------------------------------------------------------------------

def clean_pt(raw_dir: Path) -> pd.DataFrame:
    """
    Merge the two FPTA PT pass-rate CSVs into the standard programs schema.

    Detects files by column content:
      - File with "first-time" in a column name → first-time pass rates
      - File with "ultimate"   in a column name → ultimate pass rates

    Both files are joined on School Code (FPTA's stable program identifier).
    School names come from the first-time file (cleaner, no "(PT)" suffix).
    Only 2023-2024 data is used from the ultimate file.
    """
    first_df = None
    ultimate_df = None

    for path in sorted(raw_dir.glob("*.csv")):
        df = pd.read_csv(path, dtype=str)
        df.columns = [c.strip() for c in df.columns]
        cols_lower = " ".join(df.columns).lower()
        if "first-time" in cols_lower or "first time" in cols_lower:
            first_df = _prep_first_time(df)
        elif "ultimate" in cols_lower:
            ultimate_df = _prep_ultimate(df)

    if first_df is None and ultimate_df is None:
        raise ValueError(f"No recognized PT CSVs found in {raw_dir}")

    if first_df is not None and ultimate_df is not None:
        merged = pd.merge(
            first_df, ultimate_df,
            on="school_code", how="outer",
            suffixes=("", "_ult"),
        )
        # Prefer first-time file's name/state; fall back to ultimate's for schools only there
        merged["school_name"]  = merged["school_name"].fillna(merged["school_name_ult"])
        merged["state_abbrev"] = merged["state_abbrev"].fillna(merged["state_abbrev_ult"])
        merged = merged.drop(columns=["school_name_ult", "state_abbrev_ult"], errors="ignore")
    elif first_df is not None:
        merged = first_df
        merged["board_pass_rate_ultimate_2yr"] = pd.NA
    else:
        merged = ultimate_df.rename(columns={
            "school_name_ult":  "school_name",
            "state_abbrev_ult": "state_abbrev",
        })
        merged["board_pass_rate_first_time_2yr"] = pd.NA
        merged["graduates_tested"] = pd.NA

    merged["state"]       = merged["state_abbrev"].map(ABBREV_TO_STATE)
    merged["degree_type"] = "DPT"
    merged["city"]        = None

    return merged[[
        "school_code", "school_name", "city", "state", "degree_type",
        "board_pass_rate_first_time_2yr", "board_pass_rate_ultimate_2yr",
        "graduates_tested",
    ]]


def _prep_first_time(df: pd.DataFrame) -> pd.DataFrame:
    rate_col  = next(
        c for c in df.columns
        if "first-time" in c.lower() or "first time" in c.lower()
    )
    grads_col = next(
        c for c in df.columns
        if "graduates" in c.lower() or ("npte" in c.lower() and "took" in c.lower())
    )
    return pd.DataFrame({
        "state_abbrev":                   df["State"],
        "school_code":                    df["School Code"],
        "school_name":                    df["School"],
        "board_pass_rate_first_time_2yr": _to_numeric(df[rate_col]),
        "graduates_tested":               _to_numeric(df[grads_col]),
    })


def _prep_ultimate(df: pd.DataFrame) -> pd.DataFrame:
    ultimate_col = next(
        c for c in df.columns
        if "ultimate" in c.lower() and "2023-2024" in c
    )
    school_names = (
        df["School"]
        .str.replace(r"\s*\(PT\)\s*$", "", regex=True)   # strip "(PT)" suffix
        .str.replace(r"\s*–\s*", " - ", regex=True)       # em-dash → hyphen
        .str.replace("`", "'")                             # backtick → apostrophe
        .str.strip()
    )
    return pd.DataFrame({
        "state_abbrev_ult":               df["State"],
        "school_code":                    df["School Code"],
        "school_name_ult":                school_names,
        "board_pass_rate_ultimate_2yr":   _to_numeric(df[ultimate_col]),
    })


def _to_numeric(series: pd.Series) -> pd.Series:
    """Replace '*' (FPTA suppression marker), strip trailing periods, coerce to float."""
    return (
        series
        .replace("*", pd.NA)
        .str.rstrip(".")
        .pipe(pd.to_numeric, errors="coerce")
    )


# ---------------------------------------------------------------------------
# SLP normalizer (stub — format TBD)
# ---------------------------------------------------------------------------

def clean_slp(raw_dir: Path) -> pd.DataFrame:
    """Normalize SLP pass-rate CSVs. Format TBD."""
    raise NotImplementedError("SLP normalizer not yet implemented")


# ---------------------------------------------------------------------------
# OT / OTA normalizers  (source: raw/nbcot_pass_rates_2024.csv)
# ---------------------------------------------------------------------------

def clean_ot(raw_dir: Path) -> pd.DataFrame:
    """
    NBCOT 2024 pass rates for OT Doctoral and Masters programs.
    Both credential tracks produce the same OTR license → same occupation.
    """
    df = pd.read_csv(NBCOT_CSV)
    df = df[df["program_type"].isin([
        "OT Doctoral-Level Programs",
        "OT Masters-Level Programs",
    ])].copy()

    degree_map = {
        "OT Doctoral-Level Programs": "OTD",
        "OT Masters-Level Programs":  "MOT",
    }
    return pd.DataFrame({
        "school_code":                    None,
        "school_name":                    df["school"].str.strip().values,
        "city":                           None,
        "state":                          df["state"].values,
        "degree_type":                    df["program_type"].map(degree_map).values,
        "board_pass_rate_first_time_2yr": pd.to_numeric(df["pass_rate"], errors="coerce").values,
        "board_pass_rate_ultimate_2yr":   pd.NA,
        "graduates_tested":               pd.NA,
    })


def clean_ota(raw_dir: Path) -> pd.DataFrame:
    """NBCOT 2024 pass rates for OTA programs (separate occupation from OT)."""
    df = pd.read_csv(NBCOT_CSV)
    df = df[df["program_type"] == "OTA Level Program"].copy()

    return pd.DataFrame({
        "school_code":                    None,
        "school_name":                    df["school"].str.strip().values,
        "city":                           None,
        "state":                          df["state"].values,
        "degree_type":                    "AAS",
        "board_pass_rate_first_time_2yr": pd.to_numeric(df["pass_rate"], errors="coerce").values,
        "board_pass_rate_ultimate_2yr":   pd.NA,
        "graduates_tested":               pd.NA,
    })


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

# Each entry: key -> (occupation_name, normalizer_fn, check_file_or_None)
#   check_file=None  → look for CSVs in raw/schools/<key>/
#   check_file=Path  → check that specific file exists; raw_dir = file's parent
NORMALIZERS = {
    "pt":  ("Physical Therapists",           clean_pt,  None),
    "slp": ("Speech-Language Pathologists",  clean_slp, None),
    "ot":  ("Occupational Therapists",        clean_ot,  NBCOT_CSV),
    "ota": ("Occupational Therapy Assistant", clean_ota, NBCOT_CSV),
}


def _create_schema(cur) -> None:
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS schools (
            id       INTEGER PRIMARY KEY,
            name     TEXT NOT NULL,
            city     TEXT,
            state_id INTEGER REFERENCES states(id)
        );

        CREATE TABLE IF NOT EXISTS programs (
            id                             INTEGER PRIMARY KEY,
            school_id                      INTEGER NOT NULL REFERENCES schools(id),
            occupation_id                  INTEGER NOT NULL REFERENCES occupations(id),
            school_code                    TEXT,
            degree_type                    TEXT,
            program_length_months          INTEGER,
            acceptance_rate                REAL,
            applications_received          INTEGER,
            seats_available                INTEGER,
            graduation_rate                REAL,
            board_pass_rate_first_time_2yr REAL,
            board_pass_rate_ultimate_2yr   REAL,
            tuition_per_year               REAL,
            graduates_tested               INTEGER,
            UNIQUE (school_id, occupation_id, degree_type)
        );
    """)


def _get_or_create_school(cur, name: str, city, state_id) -> int:
    row = cur.execute(
        "SELECT id FROM schools WHERE name = ? AND state_id IS ?",
        (name, state_id),
    ).fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO schools (name, city, state_id) VALUES (?, ?, ?)",
        (name, city, state_id),
    )
    return cur.lastrowid


def _insert_programs(cur, con, df: pd.DataFrame, occupation_name: str) -> None:
    occ_row = cur.execute(
        "SELECT id FROM occupations WHERE name = ?", (occupation_name,)
    ).fetchone()
    if occ_row is None:
        cur.execute("INSERT INTO occupations (name) VALUES (?)", (occupation_name,))
        occ_id = cur.lastrowid
    else:
        occ_id = occ_row[0]

    def val(row, col):
        v = row.get(col)
        try:
            return None if v is None or pd.isna(v) else v
        except (TypeError, ValueError):
            return v

    total_rows = 0
    for _, row in df.iterrows():
        state_row = cur.execute(
            "SELECT id FROM states WHERE name = ?", (row.get("state"),)
        ).fetchone()
        state_id = state_row[0] if state_row else None

        school_id = _get_or_create_school(
            cur, val(row, "school_name"), val(row, "city"), state_id
        )

        cur.execute(
            """
            INSERT OR IGNORE INTO programs (
                school_id, occupation_id, school_code, degree_type,
                program_length_months, acceptance_rate, applications_received,
                seats_available, graduation_rate,
                board_pass_rate_first_time_2yr, board_pass_rate_ultimate_2yr,
                tuition_per_year, graduates_tested
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                school_id, occ_id,
                val(row, "school_code"),    val(row, "degree_type"),
                val(row, "program_length_months"),
                val(row, "acceptance_rate"), val(row, "applications_received"),
                val(row, "seats_available"), val(row, "graduation_rate"),
                val(row, "board_pass_rate_first_time_2yr"),
                val(row, "board_pass_rate_ultimate_2yr"),
                val(row, "tuition_per_year"), val(row, "graduates_tested"),
            ),
        )
        total_rows += 1

    con.commit()
    print(f"         -> {total_rows} program rows for {occupation_name}")


def load(con) -> None:
    """Load school/program data into the DB. Creates schools and programs tables."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    cur = con.cursor()
    _create_schema(cur)

    for key, entry in NORMALIZERS.items():
        occupation_name, normalizer, check_file = entry

        data_subdir = DATA_DIR / key
        data_subdir.mkdir(parents=True, exist_ok=True)

        if check_file is not None:
            if not check_file.exists():
                print(f"  [SKIP] schools/{key} - {check_file.name} not found")
                continue
            raw_subdir = check_file.parent
        else:
            raw_subdir = RAW_DIR / key
            if not raw_subdir.exists() or not list(raw_subdir.glob("*.csv")):
                print(f"  [SKIP] schools/{key} - no CSVs in raw/schools/{key}/")
                continue

        print(f"  [READ] schools/{key}")
        try:
            df = normalizer(raw_subdir)
        except NotImplementedError:
            print(f"         -> normalizer not yet implemented, skipping")
            continue

        out_path = data_subdir / f"{key}_programs.csv"
        df.to_csv(out_path, index=False)
        print(f"         -> {out_path} ({len(df)} rows)")

        _insert_programs(cur, con, df, occupation_name)

    con.commit()
