"""
04_apply_manual.py — Merge manual review fixes into both OT master CSVs.

Reads ot_outcomes_review.csv and ot_tuition_review.csv.
For any row with url_status=manual_override and a manual_url filled in,
copies that URL into the corresponding master CSV.
"""

import sys
from csv_store import load_csv, upsert_record

PIPELINES = [
    {
        "master": "ot_outcomes_urls.csv",
        "review": "ot_outcomes_review.csv",
        "label": "Outcomes (A.4.2)",
    },
    {
        "master": "ot_tuition_urls.csv",
        "review": "ot_tuition_review.csv",
        "label": "Tuition (A.4.4)",
    },
]


def apply_pipeline(pipeline: dict) -> int:
    review = load_csv(pipeline["review"])
    if review.empty:
        print(f"  {pipeline['label']}: review file not found or empty — skipping")
        return 0

    to_apply = review[
        (review["url_status"] == "manual_override") &
        (review["manual_url"].str.strip() != "")
    ]

    if to_apply.empty:
        print(f"  {pipeline['label']}: no manual overrides to apply")
        return 0

    print(f"\n  {pipeline['label']} — applying {len(to_apply)} overrides:")
    applied = 0
    for _, row in to_apply.iterrows():
        upsert_record(pipeline["master"], {
            "program_id": row["program_id"],
            "discovered_url": row["manual_url"].strip(),
            "url_confidence": "manual",
            "url_status": "manual_override",
            "search_query_used": "manual",
            "scrape_notes": f"Manual override. {row.get('reviewer_notes', '')}".strip(),
        })
        applied += 1
        print(f"    [OK] {row['school_name']} -> {row['manual_url'][:65]}")

    return applied


def main():
    print("Applying manual overrides to OT master CSVs...")
    total = 0
    for pipeline in PIPELINES:
        total += apply_pipeline(pipeline)

    if total == 0:
        print("\nNothing applied.")
        print("Fill in manual_url and set url_status=manual_override in the review CSVs first.")
    else:
        print(f"\n[OK] {total} total records updated.")
        print("Re-run 03_export_review.py to see updated summary.")


if __name__ == "__main__":
    main()
