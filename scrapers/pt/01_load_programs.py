"""
01_load_programs.py — Load PT program list into master output CSV.

Reads input_programs.csv and initializes output/pt_programs.csv.
Safe to re-run — uses upsert so existing scraped data is never overwritten.

Expected input columns: program_id, school_name, city, state
Optional:              program_url
"""

import os
import sys
import pandas as pd
from csv_store import upsert_batch, load_csv, get_path

INPUT_FILE = os.path.join(os.path.dirname(__file__), "input_programs.csv")
OUTPUT_FILE = "pt_programs.csv"

REQUIRED_COLS = {"program_id", "school_name", "city", "state"}

# All columns that will exist in the master CSV
MASTER_COLUMNS = [
    "program_id",
    "school_name",
    "city",
    "state",
    "program_url",          # main program website (input, if available)
    "fact_sheet_url",       # DISCOVERED: URL of the financial fact sheet page
    "fact_sheet_url_2",     # DISCOVERED: backup URL if first is wrong
    "search_query_used",    # which query found it
    "url_confidence",       # high / medium / low
    "url_status",           # pending | url_found | url_not_found | search_exhausted | manual_override
    "search_attempts",      # how many queries were tried
    "scrape_notes",         # any warnings or issues
]


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: {INPUT_FILE} not found.")
        print("Create input_programs.csv with columns: program_id, school_name, city, state")
        sys.exit(1)

    df = pd.read_csv(INPUT_FILE, dtype=str).fillna("")

    # Validate required columns
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        print(f"ERROR: input_programs.csv is missing columns: {missing}")
        sys.exit(1)

    print(f"Loaded {len(df)} programs from input_programs.csv")

    # Check what's already in the output (don't overwrite)
    existing = load_csv(OUTPUT_FILE)
    existing_ids = set(existing["program_id"].tolist()) if not existing.empty else set()
    print(f"Already in output CSV: {len(existing_ids)} programs")

    # Build records — only set url_status=pending for new rows
    records = []
    new_count = 0
    for _, row in df.iterrows():
        pid = str(row["program_id"])
        record = {
            "program_id": pid,
            "school_name": row.get("school_name", ""),
            "city": row.get("city", ""),
            "state": row.get("state", ""),
            "program_url": row.get("program_url", ""),
        }
        if pid not in existing_ids:
            # New program — initialize with pending status
            record["url_status"] = "pending"
            record["search_attempts"] = "0"
            record["url_confidence"] = ""
            record["fact_sheet_url"] = ""
            record["fact_sheet_url_2"] = ""
            record["search_query_used"] = ""
            record["scrape_notes"] = ""
            new_count += 1
        # If already exists, upsert will only update school_name/city/state/program_url
        # and preserve url_status and discovered fields
        records.append(record)

    upsert_batch(OUTPUT_FILE, records)

    print(f"Done. {new_count} new programs added, {len(existing_ids)} existing preserved.")
    print(f"Output: output/{OUTPUT_FILE}")
    print(f"\nNext step: python 02_discover_urls.py")


if __name__ == "__main__":
    main()
