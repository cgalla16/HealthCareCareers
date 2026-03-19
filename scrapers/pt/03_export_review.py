"""
03_export_review.py — Export rows needing human review to a separate CSV.

Writes output/pt_review.csv with all non-success rows, sorted by priority.
Open this in Excel/Sheets and manually fill in fact_sheet_url + set url_status=manual_override.
Then run 04_apply_manual.py to merge the corrections back into pt_programs.csv.

Also prints a summary of results by status.
"""

import os
import sys
import pandas as pd
from csv_store import load_csv, save_csv, get_path

OUTPUT_FILE = "pt_programs.csv"
REVIEW_FILE = "pt_review.csv"

# Sort order for review priority (most actionable first)
STATUS_PRIORITY = {
    "url_found_low_confidence": 1,
    "url_found_very_low_confidence": 2,
    "url_not_found": 3,
    "search_exhausted": 4,
    "error": 5,
    "blocked": 6,
    "manual_override": 99,  # already handled, put last
}


def main():
    df = load_csv(OUTPUT_FILE)
    if df.empty:
        print("ERROR: output/pt_programs.csv not found. Run previous steps first.")
        sys.exit(1)

    total = len(df)

    # Summary by status
    print(f"\n{'='*60}")
    print(f"PT URL Discovery — Status Summary")
    print(f"{'='*60}")
    status_counts = df["url_status"].value_counts()
    for status, count in status_counts.items():
        pct = count / total * 100
        icon = "[OK]" if status == "url_found" else "[~]" if "low" in str(status) else "[X]"
        print(f"  {icon} {status:<35} {count:>4} ({pct:.1f}%)")
    print(f"  {'TOTAL':<35} {total:>4}")

    # Confidence breakdown for found URLs
    found = df[df["url_status"] == "url_found"]
    if not found.empty:
        print(f"\n  URL Confidence Breakdown (url_found rows):")
        conf_counts = found["url_confidence"].value_counts()
        for conf, count in conf_counts.items():
            print(f"    {conf:<15} {count}")

    # Year distribution
    if "estimated_year" in df.columns:
        has_url = df[df["fact_sheet_url"].notna() & (df["fact_sheet_url"] != "")]
        print(f"\n  Estimated Year of Data (rows with a URL):")
        year_counts = has_url["estimated_year"].replace("", "unknown").value_counts().sort_index()
        for year, count in year_counts.items():
            stale = " [stale]" if year.isdigit() and int(year) < 2023 else ""
            print(f"    {year:<10} {count}{stale}")
        stale_count = has_url[has_url["estimated_year"].apply(
            lambda y: y.isdigit() and int(y) < 2023
        )].shape[0]
        if stale_count:
            print(f"\n  WARNING: {stale_count} URLs appear stale (year < 2023)")

    # Export review file
    review_statuses = [
        "url_not_found",
        "url_found_low_confidence",
        "url_found_very_low_confidence",
        "search_exhausted",
        "error",
        "blocked",
    ]

    review_df = df[df["url_status"].isin(review_statuses)].copy()

    if review_df.empty:
        print(f"\n[OK] No rows need review! All programs have confident URLs.")
        return

    # Sort by priority
    review_df["_priority"] = review_df["url_status"].map(
        lambda s: STATUS_PRIORITY.get(s, 50)
    )
    review_df = review_df.sort_values("_priority").drop(columns=["_priority"])

    # Add a manual_url column for reviewers to fill in
    if "manual_url" not in review_df.columns:
        review_df.insert(
            review_df.columns.get_loc("fact_sheet_url") + 1,
            "manual_url",
            ""
        )

    # Add reviewer notes column
    if "reviewer_notes" not in review_df.columns:
        review_df["reviewer_notes"] = ""

    save_csv(review_df, REVIEW_FILE)
    review_path = get_path(REVIEW_FILE)

    print(f"\n{'='*60}")
    print(f"Review file written: output/{REVIEW_FILE}")
    print(f"  {len(review_df)} rows need review")
    print(f"\nInstructions for manual review:")
    print(f"  1. Open output/{REVIEW_FILE} in Excel or Google Sheets")
    print(f"  2. For each row, search Google for: <school_name> DPT financial fact sheet")
    print(f"  3. Paste the correct URL in the 'manual_url' column")
    print(f"  4. Set url_status = 'manual_override' for rows you've fixed")
    print(f"  5. Run python 04_apply_manual.py to merge back into master CSV")

    # Estimate review time
    minutes = len(review_df) * 2  # ~2 min per school
    print(f"\n  Estimated review time: {minutes // 60}h {minutes % 60}m ({len(review_df)} rows × ~2 min)")


if __name__ == "__main__":
    main()
