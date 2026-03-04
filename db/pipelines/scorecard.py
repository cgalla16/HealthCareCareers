"""
db/pipelines/scorecard.py — College Scorecard enrichment pipeline.

Reads data/scorecard_exploration.csv (produced by scripts/explore_scorecard.py)
and populates:
  - schools.scorecard_unitid        (UPDATE)
  - school_scorecard table          (INSERT OR REPLACE)

Gracefully skips if the CSV is absent so refresh_db.py works offline.

school_scorecard columns kept:
  ownership        "Public" / "Private nonprofit" / "For-profit"
  locale           "City: Large", "Suburb: Midsize", etc.
  school_url       link to school website
  total_enrollment total headcount enrollment (all programs)

Fields intentionally excluded:
  admission_rate   — Scorecard reports undergrad rate; misleading for DPT/MOT/OTD
  carnegie_basic   — raw integer code with no lookup table
  highest_degree   — all our schools grant doctorates; not informative
  program earnings/debt — 0% populated for PT/OT grad programs in Scorecard data
"""

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
CSV_PATH     = PROJECT_ROOT / "data" / "scorecard_exploration.csv"


def _create_schema(cur) -> None:
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS school_scorecard (
            school_id        INTEGER PRIMARY KEY REFERENCES schools(id),
            ownership        TEXT,
            locale           TEXT,
            school_url       TEXT,
            total_enrollment INTEGER
        );
    """)


def load(con) -> None:
    """Enrich schools and create school_scorecard from the Scorecard CSV."""
    if not CSV_PATH.exists():
        print(f"  [SKIP] scorecard - {CSV_PATH.name} not found (run scripts/explore_scorecard.py)")
        return

    cur = con.cursor()
    _create_schema(cur)

    # Cache occupation IDs
    occ_pt = cur.execute("SELECT id FROM occupations WHERE name = 'Physical Therapists'").fetchone()
    occ_ot = cur.execute("SELECT id FROM occupations WHERE name = 'Occupational Therapists'").fetchone()

    matched = 0
    skipped = 0

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            unitid = row.get("scorecard_unitid", "").strip()
            if not unitid:
                skipped += 1
                continue

            school_name  = row["our_school_name"].strip()
            state_name   = row["our_state"].strip()
            ownership    = row.get("ownership", "").strip() or None
            locale       = row.get("locale", "").strip() or None
            school_url   = row.get("school_url", "").strip() or None
            enrollment   = _int(row.get("total_enrollment"))

            # Look up school by name + state
            school_row = cur.execute("""
                SELECT s.id FROM schools s
                JOIN states st ON st.id = s.state_id
                WHERE s.name = ? AND st.name = ?
            """, (school_name, state_name)).fetchone()

            if school_row is None:
                skipped += 1
                continue

            school_id = school_row[0]

            # Update schools.scorecard_unitid
            cur.execute(
                "UPDATE schools SET scorecard_unitid = ? WHERE id = ?",
                (int(unitid), school_id),
            )

            # Upsert school_scorecard
            cur.execute("""
                INSERT OR REPLACE INTO school_scorecard
                    (school_id, ownership, locale, school_url, total_enrollment)
                VALUES (?, ?, ?, ?, ?)
            """, (school_id, ownership, locale, school_url, enrollment))

            matched += 1

    con.commit()
    print(f"  [scorecard] {matched} schools enriched, {skipped} skipped (unmatched or no unitid)")


def _int(val):
    try:
        return int(val) if val and str(val).strip() else None
    except (ValueError, TypeError):
        return None
