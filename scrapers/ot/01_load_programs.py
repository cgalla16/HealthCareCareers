"""
01_load_programs.py — Load OT program list into BOTH output CSVs.

Reads input_outcomes.csv  → output/ot_outcomes_urls.csv  (A.4.2 outcomes discovery)
Reads input_financial.csv → output/ot_tuition_urls.csv   (A.4.4 tuition discovery)

Safe to re-run — uses upsert so existing scraped data is never overwritten.

Expected input columns: program_id, school_name, city, state, degree_type
Optional:               program_url
"""

import os
import sys
import pandas as pd
from csv_store import upsert_batch, load_csv

INPUT_OUTCOMES  = os.path.join(os.path.dirname(__file__), "input_outcomes.csv")
INPUT_FINANCIAL = os.path.join(os.path.dirname(__file__), "input_financial.csv")

OUTCOMES_FILE = "ot_outcomes_urls.csv"
TUITION_FILE = "ot_tuition_urls.csv"

REQUIRED_COLS = {"program_id", "school_name", "city", "state"}

BASE_COLUMNS = [
    "program_id",
    "school_name",
    "city",
    "state",
    "degree_type",       # MOT or OTD — important, different products
    "program_url",       # main program website (input, if available)
    "discovered_url",    # the URL found by search
    "discovered_url_2",  # backup second-best result
    "url_confidence",    # high / medium / low / manual
    "url_status",        # pending | url_found | url_not_found | search_exhausted | manual_override | error
    "search_query_used",
    "search_attempts",
    "scrape_notes",
]


def load_into(input_file: str, output_file: str, label: str):
    if not os.path.exists(input_file):
        print(f"ERROR: {input_file} not found.")
        sys.exit(1)

    df = pd.read_csv(input_file, dtype=str, encoding="latin-1").fillna("")

    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        print(f"ERROR: {os.path.basename(input_file)} is missing columns: {missing}")
        sys.exit(1)

    if "degree_type" not in df.columns:
        print("WARNING: degree_type column not found — leaving blank.")
        df["degree_type"] = ""

    print(f"\n[{label}]")
    print(f"Loaded {len(df)} programs from {os.path.basename(input_file)}")

    existing = load_csv(output_file)
    existing_ids = set(existing["program_id"].tolist()) if not existing.empty else set()
    print(f"Already in CSV: {len(existing_ids)} programs")

    records = []
    new_count = 0
    for _, row in df.iterrows():
        pid = str(row["program_id"])
        record = {
            "program_id": pid,
            "school_name": row.get("school_name", ""),
            "city": row.get("city", ""),
            "state": row.get("state", ""),
            "degree_type": row.get("degree_type", ""),
            "program_url": row.get("program_url", ""),
        }
        if pid not in existing_ids:
            record["url_status"] = "pending"
            record["search_attempts"] = "0"
            record["url_confidence"] = ""
            record["discovered_url"] = ""
            record["discovered_url_2"] = ""
            record["search_query_used"] = ""
            record["scrape_notes"] = ""
            new_count += 1
        records.append(record)

    upsert_batch(output_file, records)
    print(f"Added {new_count} new, preserved {len(existing_ids)} existing -> output/{output_file}")


def main():
    for output_file, input_file, label in [
        (OUTCOMES_FILE, INPUT_OUTCOMES,  "Outcomes (A.4.2)"),
        (TUITION_FILE,  INPUT_FINANCIAL, "Tuition (A.4.4)"),
    ]:
        load_into(input_file, output_file, label)

    print(f"\nDone. Both CSVs initialized.")
    print(f"Next steps:")
    print(f"  Populate discovered_url columns from a program directory or manual lookup,")
    print(f"  then run: python 04_validate_urls.py --pipeline outcomes|tuition")


if __name__ == "__main__":
    main()
