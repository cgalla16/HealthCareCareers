"""
03_export_review.py — Export rows needing human review from BOTH OT pipelines.

Writes:
  output/ot_outcomes_review.csv  — A.4.2 rows needing attention
  output/ot_tuition_review.csv   — A.4.4 rows needing attention

Prints a combined summary of both pipelines.
"""

import sys
import pandas as pd
from csv_store import load_csv, save_csv, get_path

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

REVIEW_STATUSES = [
    "url_not_found",
    "url_found_low_confidence",
    "url_found_very_low_confidence",
    "search_exhausted",
    "error",
    "blocked",
]

STATUS_PRIORITY = {
    "url_found_low_confidence": 1,
    "url_found_very_low_confidence": 2,
    "url_not_found": 3,
    "search_exhausted": 4,
    "error": 5,
    "blocked": 6,
}


def print_summary(df: pd.DataFrame, label: str):
    total = len(df)
    print(f"\n  {label}")
    print(f"  {'-'*50}")
    status_counts = df["url_status"].value_counts()
    for status, count in status_counts.items():
        pct = count / total * 100
        icon = "[OK]" if status == "url_found" else "[~]" if "low" in str(status) else "[X]"
        print(f"    {icon} {status:<35} {count:>4}  ({pct:.0f}%)")
    print(f"    {'TOTAL':<35} {total:>4}")

    found = df[df["url_status"] == "url_found"]
    if not found.empty:
        conf_counts = found["url_confidence"].value_counts()
        conf_str = ", ".join(f"{c}: {n}" for c, n in conf_counts.items())
        print(f"    Confidence breakdown: {conf_str}")


def export_review(pipeline: dict) -> int:
    df = load_csv(pipeline["master"])
    if df.empty:
        print(f"  WARNING: {pipeline['master']} not found — skipping")
        return 0

    review_df = df[df["url_status"].isin(REVIEW_STATUSES)].copy()
    if review_df.empty:
        print(f"  [OK] {pipeline['label']}: No rows need review")
        return 0

    review_df["_priority"] = review_df["url_status"].map(lambda s: STATUS_PRIORITY.get(s, 50))
    review_df = review_df.sort_values("_priority").drop(columns=["_priority"])

    if "manual_url" not in review_df.columns:
        review_df.insert(
            review_df.columns.get_loc("discovered_url") + 1,
            "manual_url",
            ""
        )
    if "reviewer_notes" not in review_df.columns:
        review_df["reviewer_notes"] = ""

    save_csv(review_df, pipeline["review"])
    print(f"  {pipeline['label']}: {len(review_df)} rows -> output/{pipeline['review']}")
    return len(review_df)


def main():
    print(f"\n{'='*60}")
    print("OT URL Discovery — Status Summary")
    print(f"{'='*60}")

    any_data = False
    for pipeline in PIPELINES:
        df = load_csv(pipeline["master"])
        if not df.empty:
            print_summary(df, pipeline["label"])
            any_data = True

    if not any_data:
        print("No output CSVs found. Run 01_load_programs.py first.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print("Exporting review files...")
    total_review = 0
    for pipeline in PIPELINES:
        total_review += export_review(pipeline)

    if total_review == 0:
        print("\n[OK] Both pipelines complete - no rows need manual review!")
    else:
        print(f"\n{total_review} total rows need review across both pipelines.")
        print("\nInstructions:")
        print("  1. Open ot_outcomes_review.csv and ot_tuition_review.csv")
        print("  2. For each row, find the correct URL manually")
        print("  3. Paste it in 'manual_url' column")
        print("  4. Set url_status = 'manual_override'")
        print("  5. Run: python 04_apply_manual.py")

    # Cross-pipeline coverage report
    outcomes_df = load_csv(PIPELINES[0]["master"])
    tuition_df = load_csv(PIPELINES[1]["master"])
    if not outcomes_df.empty and not tuition_df.empty:
        o_found = set(outcomes_df[outcomes_df["url_status"].isin(["url_found", "manual_override"])]["program_id"])
        t_found = set(tuition_df[tuition_df["url_status"].isin(["url_found", "manual_override"])]["program_id"])
        both = o_found & t_found
        either = o_found | t_found
        print(f"\nCross-pipeline coverage:")
        print(f"  Both URLs found:   {len(both)} programs (fully ready for Stage 2)")
        print(f"  Outcomes URL only: {len(o_found - t_found)} programs")
        print(f"  Tuition URL only:  {len(t_found - o_found)} programs")
        print(f"  Neither found:     {len(outcomes_df) - len(either)} programs")


if __name__ == "__main__":
    main()
