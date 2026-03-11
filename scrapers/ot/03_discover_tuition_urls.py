"""
03_discover_tuition_urls.py — OT A.4.4 Tuition/Cost Page URL Discovery

Finds the page where each OT program publishes cost of attendance / tuition
as required by ACOTE Standard A.4.4 (Published Policies and Procedures).

Output: output/ot_tuition_urls.csv

Usage:
  python 03_discover_tuition_urls.py
  python 03_discover_tuition_urls.py --limit 10          # test on 10 rows
  python 03_discover_tuition_urls.py --retry-notfound    # retry not-found rows
  python 03_discover_tuition_urls.py --force             # re-run everything
"""

import argparse
from shared_search import run_discovery

OUTPUT_FILE = "ot_tuition_urls.csv"

# Query cascade — tried in order until high confidence found
QUERY_TEMPLATES = [
    "{school_name} {degree_full} tuition cost of attendance",
    "{school_name} {degree_full} program cost fees",
    "{school_name} {degree_type} tuition fees cost",
]

# Keywords that suggest this is the right page (title/snippet)
POSITIVE_SIGNALS = [
    "tuition",
    "cost of attendance",
    "a.4.4",
    "program costs",
    "fees",
    "financial",
    "occupational therapy",
    "mot program",
    "otd program",
    "graduate tuition",
    "total cost",
    "estimated cost",
]

# Keywords in URL that are strong indicators
POSITIVE_URL_SIGNALS = [
    "tuition",
    "cost",
    "financial",
    "a-4-4",
    "a4.4",
    "fees",
    "cost-of-attendance",
    "program-cost",
    "mot-",
    "otd-",
]


def main():
    parser = argparse.ArgumentParser(description="OT A.4.4 Tuition URL Discovery")
    parser.add_argument("--retry-notfound", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    print("OT Tuition URL Discovery (A.4.4)")
    print("="*60)

    run_discovery(
        output_file=OUTPUT_FILE,
        query_templates=QUERY_TEMPLATES,
        positive_signals=POSITIVE_SIGNALS,
        positive_url_signals=POSITIVE_URL_SIGNALS,
        label="OT Tuition (A.4.4)",
        args=args,
    )

    print(f"\nNext step: python 04_export_review.py")


if __name__ == "__main__":
    main()
