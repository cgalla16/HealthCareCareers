"""
db/pipelines/scorecard.py — College Scorecard enrichment pipeline.

Reads data/scorecard_exploration.csv (produced by scripts/explore_scorecard.py)
and populates:
  - schools.scorecard_unitid        (UPDATE)
  - school_scorecard table          (INSERT OR REPLACE)

Acceptance criteria (both must pass or the row is skipped):
  1. match_score >= 0.95  — conservative threshold; eliminates wrong-institution
     and wrong-campus fuzzy matches while keeping clear name-variant matches
  2. scorecard_state == our_state abbreviation — rejects cross-state campus matches

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
from constants.states import STATE_ABBREVS

PROJECT_ROOT = Path(__file__).parent.parent.parent
CSV_PATH     = PROJECT_ROOT / "data" / "scorecard_exploration.csv"

MIN_SCORE = 0.95


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

    matched = 0
    skip_no_unitid = 0
    skip_low_score = 0
    skip_state_mismatch = 0
    skip_no_db_match = 0

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            unitid = row.get("scorecard_unitid", "").strip()
            if not unitid:
                skip_no_unitid += 1
                continue

            score = _float(row.get("match_score"))
            if score is None or score < MIN_SCORE:
                skip_low_score += 1
                continue

            our_state     = row["our_state"].strip()
            scorecard_st  = row.get("scorecard_state", "").strip()
            expected_abbr = STATE_ABBREVS.get(our_state)
            if expected_abbr and scorecard_st and scorecard_st != expected_abbr:
                skip_state_mismatch += 1
                continue

            school_name  = row["our_school_name"].strip()
            ownership    = row.get("ownership", "").strip() or None
            locale       = row.get("locale", "").strip() or None
            school_url   = row.get("school_url", "").strip() or None
            enrollment   = _int(row.get("total_enrollment"))

            # Look up school by name + state
            school_row = cur.execute("""
                SELECT s.id FROM schools s
                JOIN states st ON st.id = s.state_id
                WHERE s.name = ? AND st.name = ?
            """, (school_name, our_state)).fetchone()

            if school_row is None:
                skip_no_db_match += 1
                continue

            school_id = school_row[0]

            cur.execute(
                "UPDATE schools SET scorecard_unitid = ? WHERE id = ?",
                (int(unitid), school_id),
            )
            cur.execute("""
                INSERT OR REPLACE INTO school_scorecard
                    (school_id, ownership, locale, school_url, total_enrollment)
                VALUES (?, ?, ?, ?, ?)
            """, (school_id, ownership, locale, school_url, enrollment))

            matched += 1

    con.commit()
    total_skipped = skip_no_unitid + skip_low_score + skip_state_mismatch + skip_no_db_match
    print(f"  [scorecard] {matched} schools enriched, {total_skipped} skipped "
          f"(no_unitid={skip_no_unitid}, low_score={skip_low_score}, "
          f"state_mismatch={skip_state_mismatch}, no_db_match={skip_no_db_match})")


def _float(val):
    try:
        return float(val) if val and str(val).strip() else None
    except (ValueError, TypeError):
        return None


def _int(val):
    try:
        return int(val) if val and str(val).strip() else None
    except (ValueError, TypeError):
        return None
