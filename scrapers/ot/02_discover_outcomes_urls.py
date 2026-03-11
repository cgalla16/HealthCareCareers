"""
02_discover_outcomes_urls.py — OT A.4.2 Outcomes Page URL Discovery

Finds the page where each OT program publishes cohort size and graduation rate
as required by ACOTE Standard A.4.2 (Publication of Program Outcomes).

Output: output/ot_outcomes_urls.csv

Usage:
  python 02_discover_outcomes_urls.py
  python 02_discover_outcomes_urls.py --limit 10          # test on 10 rows
  python 02_discover_outcomes_urls.py --retry-notfound    # retry not-found rows
  python 02_discover_outcomes_urls.py --force             # re-run everything
"""

import argparse
from shared_search import run_discovery

OUTPUT_FILE = "ot_outcomes_urls.csv"

# Query cascade — tried in order until high confidence found
QUERY_TEMPLATES = [
    "{school_name} {degree_full} Publication of Program Outcomes",
    "{school_name} {degree_full} program outcomes cohort graduation rate",
    "{school_name} {degree_type} ACOTE outcomes data",
]

# Keywords that suggest this is the right page (title/snippet)
POSITIVE_SIGNALS = [
    "program outcomes",
    "a.4.2",
    "acote",
    "cohort size",
    "graduation rate",
    "pass rate",
    "nbcot",
    "licensure",
    "employment rate",
    "occupational therapy",
    "program data",
    "student outcomes",
]

# Keywords in URL that are strong indicators
POSITIVE_URL_SIGNALS = [
    "outcomes",
    "program-data",
    "a-4-2",
    "a4.2",
    "accreditation",
    "nbcot",
    "program-outcomes",
    "student-outcomes",
    "acote",
]


def main():
    parser = argparse.ArgumentParser(description="OT A.4.2 Outcomes URL Discovery")
    parser.add_argument("--retry-notfound", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    print("OT Outcomes URL Discovery (A.4.2)")
    print("="*60)

    run_discovery(
        output_file=OUTPUT_FILE,
        query_templates=QUERY_TEMPLATES,
        positive_signals=POSITIVE_SIGNALS,
        positive_url_signals=POSITIVE_URL_SIGNALS,
        label="OT Outcomes (A.4.2)",
        args=args,
    )

    print(f"\nNext step: python 03_discover_tuition_urls.py")
    print(f"Or run both simultaneously in separate terminals.")


if __name__ == "__main__":
    main()
