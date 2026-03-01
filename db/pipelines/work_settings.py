"""
db/pipelines/work_settings.py — BLS OEWS industry xlsx → work_setting_salaries
                                                        + occupation_national_stats

Reads xlsx files from:  raw/work_settings/
Outputs cleaned CSVs to: data/work_settings/
Writes to tables:        work_setting_salaries, occupation_national_stats

Adding a new occupation:
  1. Drop the BLS OEWS industry xlsx into raw/work_settings/
  2. Add an entry to FILE_TO_OCCUPATION matching the filename exactly
"""

import re
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DIR      = PROJECT_ROOT / "raw"  / "work_settings"
DATA_DIR     = PROJECT_ROOT / "data" / "work_settings"

# Filename → occupation name (must match occupations table)
FILE_TO_OCCUPATION = {
    "OccupationalTherapistsIndustry.xlsx":     "Occupational Therapists",
    "PhysicalTherapistsIndustry.xlsx":         "Physical Therapists",
    "RadiationTherapistsIndustry.xlsx":        "Radiation Therapists",
    "SpeechLangaugePathologistsIndustry.xlsx": "Speech-Language Pathologists",
}

# NAICS codes to keep and their user-facing display names
SETTINGS = {
    "62-1340": "Private Practice / Outpatient",
    "62-1100": "Physician Practices",           # dominant RT setting; minor for OT/PT/SLP
    "62-2000": "Hospitals",
    "62-1600": "Home Health",
    "62-3100": "Skilled Nursing Facilities",
    "61-1000": "Educational Services",
    "62-3300": "Assisted Living / CCRC",
    "99-9000": "Government",
    "62-1400": "Outpatient Care Centers",
    "56-1320": "Temporary / Travel",
}

TOTAL_NAICS = "00-0000"  # cross-industry total row

_NAICS_RE = re.compile(r"\(([0-9]{2}-[0-9A-Z-]+)\)\s*$")


def _extract_naics(name: str):
    m = _NAICS_RE.search(str(name))
    return m.group(1) if m else None


def _to_float(val):
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except (ValueError, TypeError):
        return None


def _to_int(val):
    f = _to_float(val)
    return int(f) if f is not None else None


def clean_xlsx(path: Path) -> tuple[pd.DataFrame, dict]:
    """
    Read one BLS OEWS industry xlsx.

    Returns:
        (settings_df, national_stats)
        settings_df   — rows for target NAICS work settings
        national_stats — dict of national-level salary/employment from 00-0000 row
    """
    df = pd.read_excel(path, skiprows=5, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    df["naics_code"] = df["Industry Name"].apply(_extract_naics)
    df = df[df["naics_code"].notna()].copy()

    # National stats from the cross-industry total row (before filtering it out)
    total_row = df[df["naics_code"] == TOTAL_NAICS]
    total_emp = _to_float(total_row["Employment (1)"].iloc[0]) if not total_row.empty else None

    national_stats = {}
    if not total_row.empty:
        r = total_row.iloc[0]
        national_stats = {
            "employment":    _to_int(r["Employment (1)"]),
            "annual_mean":   _to_float(r["Annual mean wage (2)"]),
            "annual_10th":   _to_float(r["Annual 10th percentile wage (2)"]),
            "annual_25th":   _to_float(r["Annual 25th percentile wage (2)"]),
            "annual_median": _to_float(r["Annual median wage (2)"]),
            "annual_75th":   _to_float(r["Annual 75th percentile wage (2)"]),
            "annual_90th":   _to_float(r["Annual 90th percentile wage (2)"]),
        }

    df = df[df["naics_code"].isin(SETTINGS)].copy()

    rows = []
    for _, row in df.iterrows():
        naics = row["naics_code"]
        emp   = _to_float(row["Employment (1)"])
        pct   = (emp / total_emp * 100) if (emp is not None and total_emp) else None
        rows.append({
            "naics_code":         naics,
            "setting_name":       SETTINGS[naics],
            "employment":         int(emp) if emp is not None else None,
            "pct_of_total":       round(pct, 1) if pct is not None else None,
            "annual_mean_wage":   _to_float(row["Annual mean wage (2)"]),
            "annual_median_wage": _to_float(row["Annual median wage (2)"]),
        })

    return pd.DataFrame(rows), national_stats


def _create_schema(cur) -> None:
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS work_setting_salaries (
            id                 INTEGER PRIMARY KEY,
            occupation_id      INTEGER NOT NULL REFERENCES occupations(id),
            naics_code         TEXT    NOT NULL,
            setting_name       TEXT    NOT NULL,
            employment         INTEGER,
            pct_of_total       REAL,
            annual_mean_wage   REAL,
            annual_median_wage REAL,
            UNIQUE (occupation_id, naics_code)
        );

        CREATE TABLE IF NOT EXISTS occupation_national_stats (
            id             INTEGER PRIMARY KEY,
            occupation_id  INTEGER NOT NULL REFERENCES occupations(id) UNIQUE,
            employment     INTEGER,
            annual_mean    REAL,
            annual_10th    REAL,
            annual_25th    REAL,
            annual_median  REAL,
            annual_75th    REAL,
            annual_90th    REAL,
            bls_growth_pct REAL
        );
    """)


def _get_or_create_occupation(cur, occupation_name: str) -> int:
    row = cur.execute(
        "SELECT id FROM occupations WHERE name = ?", (occupation_name,)
    ).fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO occupations (name) VALUES (?)", (occupation_name,))
    return cur.lastrowid


def _insert_settings(cur, con, df: pd.DataFrame, occ_id: int, occupation_name: str) -> None:
    for _, row in df.iterrows():
        cur.execute(
            """
            INSERT OR IGNORE INTO work_setting_salaries
                (occupation_id, naics_code, setting_name, employment,
                 pct_of_total, annual_mean_wage, annual_median_wage)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                occ_id,
                row["naics_code"],
                row["setting_name"],
                row.get("employment"),
                row.get("pct_of_total"),
                row.get("annual_mean_wage"),
                row.get("annual_median_wage"),
            ),
        )
    con.commit()
    print(f"         -> {len(df)} settings for {occupation_name}")


def _insert_national_stats(cur, con, stats: dict, occ_id: int) -> None:
    cur.execute(
        """
        INSERT OR IGNORE INTO occupation_national_stats
            (occupation_id, employment, annual_mean, annual_10th, annual_25th,
             annual_median, annual_75th, annual_90th, bls_growth_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            occ_id,
            stats.get("employment"),
            stats.get("annual_mean"),
            stats.get("annual_10th"),
            stats.get("annual_25th"),
            stats.get("annual_median"),
            stats.get("annual_75th"),
            stats.get("annual_90th"),
            10.0,   # BLS growth rate — hardcoded until OOH data is loaded
        ),
    )
    con.commit()


def load(con) -> None:
    """Load work setting salary data into the DB."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    cur = con.cursor()
    _create_schema(cur)

    for filename, occupation_name in FILE_TO_OCCUPATION.items():
        path = RAW_DIR / filename
        if not path.exists():
            print(f"  [SKIP] work_settings/{filename} not found")
            continue

        print(f"  [READ] work_settings/{filename}")
        df, national_stats = clean_xlsx(path)

        out_path = DATA_DIR / filename.replace(".xlsx", ".csv")
        df.to_csv(out_path, index=False)
        print(f"         -> {out_path} ({len(df)} rows)")

        occ_id = _get_or_create_occupation(cur, occupation_name)
        _insert_settings(cur, con, df, occ_id, occupation_name)
        _insert_national_stats(cur, con, national_stats, occ_id)

    con.commit()
