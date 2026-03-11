"""
shared_search.py — Shared Serper search + result scoring logic.
Used by both 02_discover_outcomes_urls.py and 03_discover_tuition_urls.py.
"""

import os
import re
import time
import random
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SERPER_URL = "https://google.serper.dev/search"

DELAY_MIN = 2.0
DELAY_MAX = 3.5

# Domains that are almost certainly not program pages
EXCLUDED_DOMAINS = {
    "google.com", "bing.com", "indeed.com", "glassdoor.com",
    "linkedin.com", "facebook.com", "twitter.com", "youtube.com",
    "reddit.com", "niche.com", "collegeconfidential.com",
    "gradschoolhub.com", "allalliedhealthschools.com",
    "petersons.com", "cappex.com", "usnews.com",
    "forbes.com", "bestcolleges.com", "aota.org",
    "acoteonline.org",  # the accreditor directory itself, not program pages
}

# URL path patterns that indicate wrong page type
NEGATIVE_URL_PATTERNS = [
    "apply-now", "request-info", "scholarship", "fafsa",
    "loans", "blog/", "news/", "faculty", "staff/",
    "directory", "events/", "giving/", "alumni/",
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
        "num": 10,
        "gl": "us",
        "hl": "en",
    }

    response = requests.post(SERPER_URL, headers=headers, json=payload, timeout=15)

    if response.status_code == 429:
        print("    Rate limited (429). Waiting 60 seconds...")
        time.sleep(60)
        response = requests.post(SERPER_URL, headers=headers, json=payload, timeout=15)

    response.raise_for_status()
    return response.json().get("organic", [])


def extract_year(url: str) -> str:
    """Extract a 4-digit year (2010-2029) from a URL, or '' if none found."""
    match = re.search(r'(20[12]\d)', url)
    return match.group(1) if match else ""


def score_result(result: dict, school_name: str, positive_signals: list, positive_url_signals: list) -> tuple:
    """
    Score a search result. Returns (score, confidence_label, estimated_year).

    positive_signals     — keywords to look for in title/snippet
    positive_url_signals — keywords to look for specifically in the URL
    """
    title = (result.get("title") or "").lower()
    snippet = (result.get("snippet") or "").lower()
    url = (result.get("link") or "").lower()
    domain = urlparse(url).netloc.replace("www.", "")

    if domain in EXCLUDED_DOMAINS:
        return -1.0, "excluded", ""

    estimated_year = extract_year(url)
    score = 0.0

    # Negative URL patterns
    for neg in NEGATIVE_URL_PATTERNS:
        if neg in url:
            score -= 0.3

    # Positive signals in title (strongest)
    for sig in positive_signals[:3]:
        if sig in title:
            score += 0.5

    # Positive signals in snippet
    for sig in positive_signals:
        if sig in snippet:
            score += 0.2

    # Positive signals in URL (very strong)
    for sig in positive_url_signals:
        if sig in url:
            score += 0.8

    # PDF boost (many ACOTE disclosure pages are PDFs)
    if url.endswith(".pdf"):
        score += 0.5

    # School name in domain or URL path
    school_words = school_name.lower().split()
    school_name_matched = False
    for word in school_words:
        if len(word) > 3 and word in domain:
            score += 0.4
            school_name_matched = True
            break
    for word in school_words:
        if len(word) > 3 and word in url:
            score += 0.15
            school_name_matched = True

    # Confidence label
    if score >= 1.2:
        confidence = "high"
    elif score >= 0.6:
        confidence = "medium"
    elif score >= 0.2:
        confidence = "low"
    else:
        confidence = "very_low"

    # Cap: no school name in domain or URL -> can't be high confidence
    if not school_name_matched and confidence == "high":
        confidence = "medium"

    # Cap: URL year < 2023 -> stale data, cap at low
    if estimated_year and int(estimated_year) < 2023:
        if confidence in ("high", "medium"):
            confidence = "low"

    return score, confidence, estimated_year


def find_best_results(results: list, school_name: str, positive_signals: list, positive_url_signals: list):
    """Score all results, return (best, second_best, best_score, best_confidence, estimated_year)."""
    scored = []
    for r in results:
        s, c, yr = score_result(r, school_name, positive_signals, positive_url_signals)
        if s > -1.0:
            scored.append((s, c, yr, r))
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return None, None, 0.0, "none", ""

    best_score, best_conf, best_year, best = scored[0]
    second = scored[1][3] if len(scored) > 1 else None
    return best, second, best_score, best_conf, best_year


def run_discovery(
    output_file: str,
    query_templates: list,
    positive_signals: list,
    positive_url_signals: list,
    label: str,
    args,
):
    """
    Core discovery loop — shared by outcomes and tuition scripts.
    Reads from output_file, searches, writes results back.
    """
    import sys
    from csv_store import load_csv, upsert_record
    from datetime import datetime

    if not SERPER_API_KEY:
        print("ERROR: SERPER_API_KEY not set.")
        print("  Option 1: export SERPER_API_KEY=your_key in your shell")
        print("  Option 2: create a .env file in this directory with SERPER_API_KEY=your_key")
        sys.exit(1)

    df = load_csv(output_file)
    if df.empty:
        print(f"ERROR: output/{output_file} not found. Run 01_load_programs.py first.")
        sys.exit(1)

    print(f"Loaded {len(df)} programs from output/{output_file}")

    # Determine rows to process
    if args.force:
        to_process = df
        print("--force: processing all rows")
    elif args.retry_notfound:
        to_process = df[df["url_status"].isin(["pending", "error", "url_not_found", "search_exhausted", ""])]
        print(f"--retry-notfound: {len(to_process)} rows")
    else:
        # Always retry error rows by default (transient failures should auto-recover)
        to_process = df[df["url_status"].isin(["pending", "error", ""])]
        print(f"Processing {len(to_process)} pending/error rows (skipping already-found)")

    if hasattr(args, "limit") and args.limit:
        to_process = to_process.head(args.limit)
        print(f"--limit: capping at {args.limit} rows")

    total = len(to_process)
    if total == 0:
        print("Nothing to process.")
        return

    print(f"\nStarting {label} discovery for {total} programs...")
    print(f"Estimated time: {total * 8 / 60:.1f}–{total * 15 / 60:.1f} minutes\n")

    found = not_found = errors = 0
    start_time = datetime.now()

    for i, (_, row) in enumerate(to_process.iterrows()):
        school_name = row["school_name"]
        program_id = row["program_id"]
        prev_attempts = int(row.get("search_attempts", 0) or 0)
        max_queries = max(0, 3 - prev_attempts)

        print(f"[{i+1}/{total}] {school_name} ({row['city']}, {row['state']})")

        if max_queries == 0:
            print("    Max attempts reached — marking search_exhausted")
            upsert_record(output_file, {"program_id": program_id, "url_status": "search_exhausted"})
            continue

        queries = query_templates[:max_queries]
        best_url = backup_url = query_used = best_year = ""
        best_score = 0.0
        best_confidence = ""
        notes = []

        DEGREE_FULL = {
            "MOT": "Master of Occupational Therapy",
            "OTD": "Doctor of Occupational Therapy",
        }
        degree_type = row.get("degree_type", "OT")
        degree_full = DEGREE_FULL.get(degree_type, degree_type)

        try:
            for j, template in enumerate(queries):
                query = template.format(
                    school_name=school_name,
                    degree_type=degree_type,
                    degree_full=degree_full,
                )
                print(f"    Query {j+1}/{len(queries)}: {query}")

                try:
                    results = serper_search(query)
                except requests.exceptions.HTTPError as e:
                    notes.append(f"HTTP error q{j+1}: {e}")
                    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
                    continue
                except Exception as e:
                    notes.append(f"Error q{j+1}: {e}")
                    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
                    continue

                best, second, score, confidence, year = find_best_results(
                    results, school_name, positive_signals, positive_url_signals
                )

                if best and score > best_score:
                    best_score = score
                    best_confidence = confidence
                    best_url = best.get("link", "")
                    best_year = year
                    query_used = query
                    if second:
                        backup_url = second.get("link", "")

                year_tag = f" [{year}]" if year else ""
                print(f"    Best: [{confidence}] score={score:.2f}{year_tag} -> {best_url[:70]}")

                if best_confidence == "high":
                    print("    [OK] High confidence -- stopping search.")
                    break

                if j < len(queries) - 1:
                    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

            # Determine status
            if best_url and best_confidence in ("high", "medium"):
                status = "url_found"
            elif best_url and best_confidence == "low":
                status = "url_found_low_confidence"
            elif best_url:
                status = "url_found_very_low_confidence"
            else:
                status = "url_not_found"

            upsert_record(output_file, {
                "program_id": program_id,
                "discovered_url": best_url,
                "discovered_url_2": backup_url,
                "url_confidence": best_confidence,
                "url_status": status,
                "estimated_year": best_year,
                "search_query_used": query_used,
                "search_attempts": str(prev_attempts + len(queries)),
                "scrape_notes": " | ".join(notes),
            })

            if "url_found" in status:
                found += 1
                year_tag = f" [{best_year}]" if best_year else ""
                print(f"    -> {status} [{best_confidence}]{year_tag}")
            else:
                not_found += 1
                print(f"    -> {status}")

        except KeyboardInterrupt:
            print("\n\nInterrupted. Progress saved. Re-run to resume.")
            sys.exit(0)
        except Exception as e:
            errors += 1
            print(f"    ERROR: {e}")
            upsert_record(output_file, {
                "program_id": program_id,
                "url_status": "error",
                "scrape_notes": str(e),
            })

        if i < total - 1:
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    elapsed = (datetime.now() - start_time).seconds // 60
    print(f"\n{'='*60}")
    print(f"{label} discovery complete in ~{elapsed} minutes")
    print(f"  Found:     {found}")
    print(f"  Not found: {not_found}")
    print(f"  Errors:    {errors}")
