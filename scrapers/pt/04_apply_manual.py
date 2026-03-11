"""
04_apply_manual.py — Merge manual review fixes back into master CSV.

After you fill in manual_url in output/pt_review.csv and set url_status=manual_override,
run this script to merge those URLs into output/pt_programs.csv.
"""

import sys
import pandas as pd
from csv_store import load_csv, upsert_record

MASTER_FILE = "pt_programs.csv"
REVIEW_FILE = "pt_review.csv"


def main():
    master = load_csv(MASTER_FILE)
    review = load_csv(REVIEW_FILE)

    if review.empty:
        print("output/pt_review.csv not found or empty.")
        sys.exit(1)

    # Only process rows where reviewer set manual_override and filled in manual_url
    to_apply = review[
        (review["url_status"] == "manual_override") &
        (review["manual_url"].str.strip() != "")
    ]

    if to_apply.empty:
        print("No rows with url_status=manual_override and a manual_url found.")
        print("Fill in manual_url and set url_status=manual_override in pt_review.csv first.")
        sys.exit(0)

    print(f"Applying {len(to_apply)} manual overrides to master CSV...")

    applied = 0
    for _, row in to_apply.iterrows():
        upsert_record(MASTER_FILE, {
            "program_id": row["program_id"],
            "fact_sheet_url": row["manual_url"].strip(),
            "url_confidence": "manual",
            "url_status": "manual_override",
            "search_query_used": "manual",
            "scrape_notes": f"Manual override. {row.get('reviewer_notes', '')}".strip(),
        })
        applied += 1
        print(f"  ✓ {row['school_name']} → {row['manual_url'][:70]}")

    print(f"\nDone. {applied} records updated in output/{MASTER_FILE}")
    print("Re-run 03_export_review.py to see updated summary.")


if __name__ == "__main__":
    main()
