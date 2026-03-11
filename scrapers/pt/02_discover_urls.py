"""
02_discover_urls.py — PT Financial Fact Sheet URL Discovery Agent

For each pending PT program, runs up to 3 Google searches via Serper API
to find the URL of the program's Financial Fact Sheet.

Resumable: re-running skips all url_found rows.
Rate limited: 2-3s between searches, 60s backoff on 429.

Search query cascade (tries in order until a confident result is found):
  1. "{school_name} DPT financial fact sheet"
  2. "{school_name} physical therapy financial fact sheet"
  3. "{school_name} DPT program costs tuition fees"

Usage:
  python 02_discover_urls.py
  python 02_discover_urls.py --retry-notfound   # also retries url_not_found rows
  python 02_discover_urls.py --force            # re-runs everything including url_found
  python 02_discover_urls.py --limit 10         # only process first N pending rows (for testing)
"""

import os
import sys
import time
import random
import argparse
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from urllib.parse import urlparse

from csv_store import load_csv, upsert_record

load_dotenv()

OUTPUT_FILE = "pt_programs.csv"
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SERPER_URL = "https://google.serper.dev/search"

# How long to pause between searches (seconds)
DELAY_MIN = 2.0
DELAY_MAX = 3.5

# Domains that are almost certainly NOT fact sheet pages — skip if top result
EXCLUDED_DOMAINS = {
    "google.com", "bing.com", "indeed.com", "glassdoor.com",
    "linkedin.com", "facebook.com", "twitter.com", "youtube.com",
    "reddit.com", "niche.com", "collegeconfidential.com",
    "gradschoolhub.com", "allalliedhealthschools.com",
    "petersons.com", "cappex.com", "zinch.com",
    "usnews.com", "forbes.com", "bestcolleges.com",
}

# Keywords that strongly suggest a financial fact sheet page
POSITIVE_SIGNALS = [
    "financial fact sheet",
    "fact sheet",
    "financial information",
    "program costs",
    "cost of attendance",
    "tuition and fees",
    "dpt program",
    "doctor of physical therapy",
    "physical therapy program",
]

# Keywords in URL/title that suggest it's NOT a fact sheet
NEGATIVE_SIGNALS = [
    "admissions/apply",
    "apply-now",
    "request-info",
    "scholarship",
    "financial-aid",  # financial aid page ≠ fact sheet
    "fafsa",
    "loans",
    "blog",
    "news",
    "faculty",
    "staff",
    "directory",
]

# Search query cascade — tried in order
QUERY_TEMPLATES = [
    "{school_name} DPT financial fact sheet",
    "{school_name} physical therapy financial fact sheet",
    "{school_name} DPT program costs tuition fees",
]


def serper_search(query: str) -> list:
    """Call Serper API. Returns list of organic result dicts."""
    if not SERPER_API_KEY:
        raise ValueError("SERPER_API_KEY not set. Add it to .env file.")

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "num": 10,  # get top 10 results to score
        "gl": "us",
        "hl": "en",
    }

    response = requests.post(SERPER_URL, headers=headers, json=payload, timeout=15)

    if response.status_code == 429:
        print("    Rate limited (429). Waiting 60 seconds...")
        time.sleep(60)
        # Retry once
        response = requests.post(SERPER_URL, headers=headers, json=payload, timeout=15)

    response.raise_for_status()
    data = response.json()
    return data.get("organic", [])


def score_result(result: dict, school_name: str) -> tuple[float, str]:
    """
    Score a search result on how likely it is to be the financial fact sheet.
    Returns (score, confidence_label).
    """
    title = (result.get("title") or "").lower()
    snippet = (result.get("snippet") or "").lower()
    url = (result.get("link") or "").lower()

    school_words = school_name.lower().split()
    combined = f"{title} {snippet} {url}"

    score = 0.0

    # Negative domain check
    domain = urlparse(url).netloc.replace("www.", "")
    if domain in EXCLUDED_DOMAINS:
        return -1.0, "excluded"

    # Negative signal check — these pages are almost certainly wrong
    for neg in NEGATIVE_SIGNALS:
        if neg in url:
            score -= 0.3

    # Positive signals in title (strongest signal)
    for pos in POSITIVE_SIGNALS[:3]:  # first 3 are strongest
        if pos in title:
            score += 0.5

    # Positive signals in snippet
    for pos in POSITIVE_SIGNALS:
        if pos in snippet:
            score += 0.2

    # School name match in URL domain (great signal)
    for word in school_words:
        if len(word) > 3 and word in domain:
            score += 0.4
            break

    # School name in URL path
    for word in school_words:
        if len(word) > 3 and word in url:
            score += 0.15

    # PDF is a very strong signal for fact sheets
    if url.endswith(".pdf"):
        score += 0.6

    # "fact-sheet" or "factsheet" in URL is the jackpot
    if "fact-sheet" in url or "factsheet" in url:
        score += 1.0

    # Determine confidence label
    if score >= 1.2:
        confidence = "high"
    elif score >= 0.6:
        confidence = "medium"
    elif score >= 0.2:
        confidence = "low"
    else:
        confidence = "very_low"

    return score, confidence


def find_best_result(results: list, school_name: str) -> tuple[dict | None, dict | None, float, str]:
    """
    Score all results and return the best and second-best.
    Returns (best_result, second_result, best_score, confidence)
    """
    scored = []
    for r in results:
        score, confidence = score_result(r, school_name)
        if score > -1.0:  # not excluded
            scored.append((score, confidence, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return None, None, 0.0, "none"

    best_score, best_conf, best = scored[0]
    second = scored[1][2] if len(scored) > 1 else None

    return best, second, best_score, best_conf


def process_program(row: pd.Series, attempt_queries: list) -> dict:
    """
    Try search queries in order until a high-confidence result is found.
    Returns a dict of fields to update in the CSV.
    """
    school_name = row["school_name"]
    program_id = row["program_id"]
    existing_attempts = int(row.get("search_attempts", 0) or 0)

    best_url = ""
    backup_url = ""
    best_score = 0.0
    best_confidence = ""
    query_used = ""
    notes = []

    for i, query_template in enumerate(attempt_queries):
        query = query_template.format(school_name=school_name)
        attempt_num = existing_attempts + i + 1

        print(f"    Query {i+1}/{len(attempt_queries)}: {query}")

        try:
            results = serper_search(query)
        except requests.exceptions.HTTPError as e:
            notes.append(f"HTTP error on query {i+1}: {e}")
            print(f"    HTTP error: {e}")
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
            continue
        except Exception as e:
            notes.append(f"Search error on query {i+1}: {e}")
            print(f"    Error: {e}")
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
            continue

        best, second, score, confidence = find_best_result(results, school_name)

        if best:
            url = best.get("link", "")
            print(f"    Best result: [{confidence}] score={score:.2f} → {url[:80]}")

            if score > best_score:
                best_score = score
                best_confidence = confidence
                best_url = url
                query_used = query
                if second:
                    backup_url = second.get("link", "")

        # If we found a high-confidence result, stop searching
        if best_confidence == "high":
            print(f"    ✓ High confidence match found, stopping search.")
            break

        # Delay before next query
        if i < len(attempt_queries) - 1:
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            time.sleep(delay)

    # Determine final status
    if best_url and best_confidence in ("high", "medium"):
        status = "url_found"
    elif best_url and best_confidence == "low":
        status = "url_found_low_confidence"
    elif best_url:
        status = "url_found_very_low_confidence"
    else:
        status = "url_not_found"

    return {
        "program_id": program_id,
        "fact_sheet_url": best_url,
        "fact_sheet_url_2": backup_url,
        "url_confidence": best_confidence,
        "url_status": status,
        "search_query_used": query_used,
        "search_attempts": str(existing_attempts + len(attempt_queries)),
        "scrape_notes": " | ".join(notes) if notes else "",
    }


def main():
    parser = argparse.ArgumentParser(description="PT Financial Fact Sheet URL Discovery")
    parser.add_argument("--retry-notfound", action="store_true",
                        help="Also retry rows with url_not_found status")
    parser.add_argument("--force", action="store_true",
                        help="Re-run all rows including url_found")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process first N rows (for testing)")
    args = parser.parse_args()

    if not SERPER_API_KEY:
        print("ERROR: SERPER_API_KEY not set.")
        print("1. Sign up at https://serper.dev (free, 2500 searches)")
        print("2. Create .env file with: SERPER_API_KEY=your_key_here")
        sys.exit(1)

    df = load_csv(OUTPUT_FILE)
    if df.empty:
        print("ERROR: output/pt_programs.csv not found. Run 01_load_programs.py first.")
        sys.exit(1)

    print(f"Loaded {len(df)} programs from output/{OUTPUT_FILE}")

    # Determine which rows to process
    if args.force:
        to_process = df
        print("--force: processing all rows")
    elif args.retry_notfound:
        to_process = df[df["url_status"].isin(["pending", "url_not_found", "search_exhausted", ""])]
        print(f"--retry-notfound: processing {len(to_process)} pending + not-found rows")
    else:
        to_process = df[df["url_status"].isin(["pending", ""])]
        print(f"Processing {len(to_process)} pending rows (skipping already-found)")

    if args.limit:
        to_process = to_process.head(args.limit)
        print(f"--limit: capping at {args.limit} rows")

    total = len(to_process)
    if total == 0:
        print("Nothing to process. All programs have url_status set.")
        print("Use --retry-notfound or --force to re-process.")
        sys.exit(0)

    print(f"\nStarting discovery for {total} programs...")
    print(f"Estimated time: {total * 8 / 60:.1f} – {total * 15 / 60:.1f} minutes\n")

    found = 0
    not_found = 0
    errors = 0
    start_time = datetime.now()

    for i, (_, row) in enumerate(to_process.iterrows()):
        school_name = row["school_name"]
        print(f"[{i+1}/{total}] {school_name} ({row['city']}, {row['state']})")

        # Decide how many queries to try based on previous attempts
        prev_attempts = int(row.get("search_attempts", 0) or 0)
        max_queries = max(0, 3 - prev_attempts)

        if max_queries == 0:
            print("    Max attempts reached — marking search_exhausted")
            upsert_record(OUTPUT_FILE, {
                "program_id": row["program_id"],
                "url_status": "search_exhausted",
            })
            continue

        queries_to_try = QUERY_TEMPLATES[:max_queries]

        try:
            result = process_program(row, queries_to_try)
            upsert_record(OUTPUT_FILE, result)

            if "url_found" in result["url_status"]:
                found += 1
                print(f"    → {result['url_status']} [{result['url_confidence']}]: {result['fact_sheet_url'][:80]}")
            else:
                not_found += 1
                print(f"    → {result['url_status']}")

        except KeyboardInterrupt:
            print("\n\nInterrupted by user. Progress saved. Re-run to resume.")
            sys.exit(0)
        except Exception as e:
            errors += 1
            print(f"    ERROR: {e}")
            upsert_record(OUTPUT_FILE, {
                "program_id": row["program_id"],
                "url_status": "error",
                "scrape_notes": str(e),
            })

        # Delay between schools
        if i < total - 1:
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            time.sleep(delay)

    elapsed = (datetime.now() - start_time).seconds // 60
    print(f"\n{'='*60}")
    print(f"Discovery complete in ~{elapsed} minutes")
    print(f"  Found:     {found}")
    print(f"  Not found: {not_found}")
    print(f"  Errors:    {errors}")
    print(f"\nNext step: python 03_export_review.py")


if __name__ == "__main__":
    main()
