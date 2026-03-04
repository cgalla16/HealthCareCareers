"""
explore_scorecard.py — One-off script to match PT/OT schools against the
College Scorecard API and dump all available useful fields to a CSV.

Prerequisites:
    pip install requests
    export SCORECARD_API_KEY=your_key_here   (get one free at https://api.data.gov/signup)

Output:
    data/scorecard_exploration.csv

Usage:
    python scripts/explore_scorecard.py
"""

import csv
import difflib
import os
import sqlite3
import sys
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("SCORECARD_API_KEY", "")
BASE_URL = "https://api.data.gov/ed/collegescorecard/v1/schools"

# CIP codes relevant to our programs
# 512308 = Physical Therapist (DPT)
# 512306 = Occupational Therapy/Therapist
CIP_PT = "512308"
CIP_OT = "512306"

# Scorecard credential levels for each program type
# 7  = Master's degree (MOT)
# 18 = Doctor's degree — professional practice (DPT, OTD)
CRED_DPT = [18]
CRED_OT  = [7, 18]  # accept both MOT and OTD; filtered further per-row below

DB_PATH = Path(__file__).parent.parent / "healthcare.db"
OUT_CSV = Path(__file__).parent.parent / "data" / "scorecard_exploration.csv"

# Canonical column order — must match every row dict written
FIELDNAMES = [
    "our_school_name", "our_state", "our_occupations", "our_degree_types", "our_school_code",
    "match_score", "unmatched_reason",
    "scorecard_unitid", "scorecard_name", "scorecard_city", "scorecard_state",
    "ownership", "school_url", "locale", "carnegie_basic", "highest_degree",
    "total_enrollment", "admission_rate",
    "pt_earnings_6yr_median", "pt_earnings_10yr_median", "pt_debt_median", "pt_debt_monthly", "pt_credential_level",
    "ot_earnings_6yr_median", "ot_earnings_10yr_median", "ot_debt_median", "ot_debt_monthly", "ot_credential_level",
]

# Scorecard school.ownership codes → human labels
OWNERSHIP = {1: "Public", 2: "Private nonprofit", 3: "For-profit"}

# Scorecard locale codes → labels
LOCALE = {
    11: "City: Large", 12: "City: Midsize", 13: "City: Small",
    21: "Suburb: Large", 22: "Suburb: Midsize", 23: "Suburb: Small",
    31: "Town: Fringe", 32: "Town: Distant", 33: "Town: Remote",
    41: "Rural: Fringe", 42: "Rural: Distant", 43: "Rural: Remote",
}

# School-level fields to request in the search call
SCHOOL_FIELDS = ",".join([
    "id",
    "school.name",
    "school.city",
    "school.state",
    "school.ownership",
    "school.school_url",
    "school.locale",
    "school.carnegie_basic",
    "school.degrees_awarded.highest",
    "latest.student.size",
    "latest.cost.tuition.in_state",
    "latest.cost.tuition.out_of_state",
    "latest.cost.avg_net_price.public",
    "latest.cost.avg_net_price.private",
    "latest.admissions.admission_rate.overall",
])

STATE_ABBREVS = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME",
    "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Puerto Rico": "PR",
    "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT",
    "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def scorecard_get(params: dict, retries: int = 1) -> dict | None:
    """GET request to the Scorecard API; returns parsed JSON or None on error."""
    params["api_key"] = API_KEY
    try:
        resp = requests.get(BASE_URL, params=params, timeout=15)
        if resp.status_code == 429:
            if retries > 0:
                print("  Rate-limited; waiting 60s ...", file=sys.stderr)
                time.sleep(60)
                return scorecard_get(params, retries - 1)
            print("  ERROR: still rate-limited after retry", file=sys.stderr)
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        return None


def best_match(our_name: str, candidates: list[dict]) -> tuple[dict | None, float]:
    """Return (best_candidate, ratio) from a list of Scorecard school records."""
    best_ratio = 0.0
    best_cand = None
    our_lower = our_name.lower()
    for cand in candidates:
        sc_name = (cand.get("school.name") or "").lower()
        ratio = difflib.SequenceMatcher(None, our_lower, sc_name).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_cand = cand
    return best_cand, best_ratio


def extract_program_earnings(programs: list[dict], cip_prefix: str,
                             credential_levels: list[int] | None = None) -> dict:
    """
    Filter a nested programs list for a given CIP prefix (and optionally
    credential level) and return the best (most complete) earnings/debt record.

    Scorecard credential levels relevant here:
        7  = Master's degree        (MOT)
        18 = Doctoral professional  (DPT, OTD)

    Scorecard program records look like: {'code': '512308', 'title': ..., ...}
    """
    matches = [
        p for p in programs
        if str(p.get("code", "")).startswith(cip_prefix[:4])  # 4-digit CIP match
    ]
    # Prefer exact 6-digit match
    exact = [p for p in matches if str(p.get("code", "")) == cip_prefix]
    pool = exact or matches

    # Filter by credential level when specified; fall back to full pool if none match
    if credential_levels:
        level_filtered = [
            p for p in pool
            if _deep(p, "credential", "level") in credential_levels
        ]
        if level_filtered:
            pool = level_filtered
    if not pool:
        return {}

    # Pick the record with the most non-null earnings fields
    def completeness(p):
        return sum(1 for k in ["earnings_6yr_median", "earnings_10yr_median",
                                "debt_median", "debt_monthly"] if p.get(k) is not None)

    normalized = []
    for p in pool:
        normalized.append({
            "earnings_6yr_median":  _deep(p, "earnings", "6_yr", "median"),
            "earnings_10yr_median": _deep(p, "earnings", "10_yr", "median"),
            "debt_median":          _deep(p, "debt", "median_debt"),
            "debt_monthly":         _deep(p, "debt", "monthly_payments"),
            "credential_level":     _deep(p, "credential", "level"),
            "ipeds_awards":         _deep(p, "counts", "ipeds_awards2"),
        })
    return max(normalized, key=completeness)


def _deep(d: dict, *keys):
    """Safe nested dict access — returns None if any key is missing."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def load_schools_from_db() -> list[dict]:
    """
    Return one row per unique (school_name, state) for PT and OT programs.
    Aggregates occupations/degrees if the same school appears for both.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            s.name          AS school_name,
            st.name         AS state,
            GROUP_CONCAT(DISTINCT o.name)        AS occupations,
            GROUP_CONCAT(DISTINCT p.degree_type) AS degree_types,
            MAX(p.school_code)                   AS school_code
        FROM programs p
        JOIN schools     s  ON s.id  = p.school_id
        JOIN states      st ON st.id = s.state_id
        JOIN occupations o  ON o.id  = p.occupation_id
        WHERE o.name IN ('Physical Therapists', 'Occupational Therapists')
        GROUP BY s.name, st.name
        ORDER BY s.name
    """)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not API_KEY:
        sys.exit(
            "ERROR: SCORECARD_API_KEY environment variable not set.\n"
            "Get a free key at https://api.data.gov/signup"
        )

    schools = load_schools_from_db()
    print(f"Loaded {len(schools)} unique PT/OT schools from DB.")

    # Resume support: skip schools already written to the CSV
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    already_done = set()
    write_header = not OUT_CSV.exists()
    if not write_header:
        with open(OUT_CSV, newline="", encoding="utf-8") as f:
            already_done = {row["our_school_name"] for row in csv.DictReader(f)}
        print(f"Resuming — {len(already_done)} schools already in CSV, skipping them.")

    csv_file = open(OUT_CSV, "a" if already_done else "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES, extrasaction="ignore")
    if write_header:
        writer.writeheader()

    matched_count = 0
    unmatched_count = 0

    for i, school in enumerate(schools, 1):
        name = school["school_name"]
        state = school["state"]
        abbrev = STATE_ABBREVS.get(state, "")

        if name in already_done:
            print(f"[{i}/{len(schools)}] SKIP {name}")
            continue

        print(f"[{i}/{len(schools)}] {name} ({abbrev})", end="  ", flush=True)

        # --- Step 1: search by name + state ---
        search_words = " ".join(
            w for w in name.replace(",", " ").replace("-", " ").split()
            if len(w) >= 3
        )
        params = {
            "_fields": SCHOOL_FIELDS,
            "_per_page": 5,
            "school.name": search_words,
        }
        if abbrev:
            params["school.state"] = abbrev

        data = scorecard_get(params)
        results = (data or {}).get("results", [])

        cand, ratio = best_match(name, results)

        # Retry without state filter if no results (e.g. multi-state campuses)
        if not cand and abbrev:
            data2 = scorecard_get({**params, "_per_page": 10, "school.state": None})
            results2 = (data2 or {}).get("results", [])
            cand, ratio = best_match(name, results2)

        if not cand or ratio < 0.55:
            print(f"NO MATCH (best ratio={ratio:.2f})")
            writer.writerow({
                "our_school_name":  name,
                "our_state":        state,
                "our_occupations":  school["occupations"],
                "our_degree_types": school["degree_types"],
                "our_school_code":  school["school_code"] or "",
                "match_score":      round(ratio, 3),
                "unmatched_reason": "ratio below threshold" if cand else "no results",
            })
            csv_file.flush()
            unmatched_count += 1
            time.sleep(0.05)
            continue

        print(f"matched → {cand.get('school.name')} (score={ratio:.2f})")

        unitid = cand.get("id")

        # --- Step 2: fetch program-level data (cip_4_digit nested) ---
        prog_data = scorecard_get({
            "id": unitid,
            "all_programs_nested": "true",
            "_fields": "id,programs.cip_4_digit",
            "_per_page": 1,
        })
        nested_programs = []
        if prog_data and prog_data.get("results"):
            raw = prog_data["results"][0].get("programs", {}).get("cip_4_digit", [])
            nested_programs = raw if isinstance(raw, list) else []

        pt_prog = extract_program_earnings(nested_programs, CIP_PT, CRED_DPT)
        # For OT: if school only has MOT, use [7]; only OTD, use [18]; both → [7,18]
        degree_types = school.get("degree_types", "") or ""
        has_mot = "MOT" in degree_types
        has_otd = "OTD" in degree_types
        ot_levels = ([7] if has_mot and not has_otd else
                     [18] if has_otd and not has_mot else
                     CRED_OT)
        ot_prog = extract_program_earnings(nested_programs, CIP_OT, ot_levels)

        # --- Build output row ---
        writer.writerow({
            "our_school_name":    name,
            "our_state":          state,
            "our_occupations":    school["occupations"],
            "our_degree_types":   school["degree_types"],
            "our_school_code":    school["school_code"] or "",
            "match_score":        round(ratio, 3),
            "unmatched_reason":   "",
            "scorecard_unitid":   unitid,
            "scorecard_name":     cand.get("school.name", ""),
            "scorecard_city":     cand.get("school.city", ""),
            "scorecard_state":    cand.get("school.state", ""),
            "ownership":          OWNERSHIP.get(cand.get("school.ownership"), ""),
            "school_url":         cand.get("school.school_url", ""),
            "locale":             LOCALE.get(cand.get("school.locale"), ""),
            "carnegie_basic":     cand.get("school.carnegie_basic", ""),
            "highest_degree":     cand.get("school.degrees_awarded.highest", ""),
            "total_enrollment":   cand.get("latest.student.size", ""),
            "admission_rate":     cand.get("latest.admissions.admission_rate.overall", ""),
            "pt_earnings_6yr_median":  pt_prog.get("earnings_6yr_median", ""),
            "pt_earnings_10yr_median": pt_prog.get("earnings_10yr_median", ""),
            "pt_debt_median":          pt_prog.get("debt_median", ""),
            "pt_debt_monthly":         pt_prog.get("debt_monthly", ""),
            "pt_credential_level":     pt_prog.get("credential_level", ""),
            "ot_earnings_6yr_median":  ot_prog.get("earnings_6yr_median", ""),
            "ot_earnings_10yr_median": ot_prog.get("earnings_10yr_median", ""),
            "ot_debt_median":          ot_prog.get("debt_median", ""),
            "ot_debt_monthly":         ot_prog.get("debt_monthly", ""),
            "ot_credential_level":     ot_prog.get("credential_level", ""),
        })
        csv_file.flush()
        matched_count += 1

        time.sleep(0.05)  # stay well under 1000 req/hr

    csv_file.close()
    print(f"\nDone. {matched_count} matched, {unmatched_count} unmatched → {OUT_CSV}")


if __name__ == "__main__":
    main()
