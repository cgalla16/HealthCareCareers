"""
06_rediscover_rejected.py — LLM-based URL re-discovery for rejected PT rows.

For rows where validation_status=rejected, uses Claude Sonnet with
web_search + web_fetch to navigate to the university site and find
the correct DPT Student Financial Fact Sheet page.

Navigation strategy:
  1. If program_url is known, fetch that page first then follow links
  2. If rejection was NOT wrong-school, reuse the old URL's domain (skip domain search)
  3. Otherwise, two-step site:edu search to find correct domain first

After finding a new URL, resets validation_status so 05_validate_urls.py
will re-validate and extract on the next run.

Usage:
  python 06_rediscover_rejected.py
  python 06_rediscover_rejected.py --limit 5
  python 06_rediscover_rejected.py --force
"""

import os
import sys
import re
import json
import time
import random
import argparse
from urllib.parse import urlparse

import anthropic
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

sys.path.insert(0, os.path.dirname(__file__))
from csv_store import load_csv, upsert_record

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
INPUT_FILE = "pt_programs.csv"
URL_COL = "fact_sheet_url"

MAX_CONTINUATIONS = 3
DELAY_MIN = 15.0
DELAY_MAX = 25.0
RATE_LIMIT_BACKOFF = [60, 120, 240]  # seconds — exponential backoff on 429

WRONG_SCHOOL_SIGNALS = [
    "different school", "different institution", "wrong school",
    "wrong institution", "not the same", "belongs to",
    "blank template", "blank form", "no actual", "not filled",
]

# Third-party domains that host generic/shared content — never reuse as school domain
THIRD_PARTY_DOMAINS = {
    "acapt.org",       # American Council of Academic Physical Therapy (blank templates)
    "capteonline.org", # CAPTE accreditor
    "apta.org",        # American Physical Therapy Association
    "aota.org",        # American Occupational Therapy Association
    "acoteonline.org", # ACOTE accreditor
    "nbcot.org",       # NBCOT board
    "fsbpt.org",       # Federation of State Boards of PT
}

SYSTEM_PROMPT = (
    "You are a precise web research assistant. Be terse. "
    "Do the minimum navigation needed to find the target URL. "
    "If a search result title and snippet clearly identify the correct page, "
    "return that URL immediately without fetching it — it will be validated separately. "
    "Only fetch a page if you need to navigate or verify. "
    "Reply only with the JSON result, no preamble."
)


class RediscoveryResult(BaseModel):
    url: Optional[str] = None
    confidence: str   # "high" | "medium" | "low"
    reasoning: str


def is_wrong_school(rejection_reason: str, domain: str = "") -> bool:
    if domain and domain.lower() in THIRD_PARTY_DOMAINS:
        return True
    return any(s in rejection_reason.lower() for s in WRONG_SCHOOL_SIGNALS)


def build_prompt(school_name: str, city: str, state: str, rejection_reason: str,
                 program_url: str, old_domain: str) -> str:
    location = f"{city}, {state}" if city and state else state or city or ""
    location_str = f" ({location})" if location else ""

    if program_url:
        nav_instruction = (
            f"Start here: {program_url}\n"
            f"Fetch that page first, then follow links to find the DPT Student "
            f"Financial Fact Sheet page."
        )
    elif old_domain and not is_wrong_school(rejection_reason, old_domain):
        # Domain is correct — skip step 1, search directly within it
        nav_instruction = (
            f"The school's domain is {old_domain}. Search directly:\n"
            f"  site:{old_domain} Doctor of Physical Therapy financial fact sheet\n"
            f"Then fetch the top result."
        )
    else:
        nav_instruction = (
            f"Use this two-step search strategy to avoid landing on the wrong school's pages:\n"
            f"  Step 1: Search for '{school_name} site:edu' to identify the correct .edu domain.\n"
            f"  Step 2: Search using that domain, e.g. 'site:schooldomain.edu "
            f"Doctor of Physical Therapy financial fact sheet'.\n"
            f"Then fetch the most relevant result."
        )

    return (
        f"I need to find DPT program data for {school_name}{location_str}.\n\n"
        f"A previous URL was rejected because: {rejection_reason}\n\n"
        f"{nav_instruction}\n\n"
        f"Preferred: the CAPTE Student Financial Fact Sheet — a single document with "
        f"tuition, fees, total program cost, graduation rate, NPTE pass rate, and "
        f"employment rate all in one place. Set confidence='high' if you find this.\n\n"
        f"Acceptable if no fact sheet exists: any official DPT program page that contains "
        f"at least one of: tuition per year, NPTE first-time pass rate, graduation rate, "
        f"or employment rate. Set confidence='medium' for these.\n\n"
        f"Do NOT return: a PTA (Physical Therapy Assistant) page, an undergraduate tuition "
        f"page, a generic cost-of-attendance calculator, a page from a different school, "
        f"or a page with none of the target data. Set confidence='low' for these.\n\n"
        f"Reply with ONLY this JSON:\n"
        f'{{"url": "https://...", "confidence": "high|medium|low", "reasoning": "brief"}}\n'
        f"If not found: "
        f'{{"url": null, "confidence": "low", "reasoning": "why not found"}}'
    )


def parse_with_haiku(client, text: str) -> RediscoveryResult:
    """Fallback: use Haiku structured output to parse Claude's free-text response."""
    try:
        response = client.messages.parse(
            model="claude-haiku-4-5",
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": (
                    f"Extract the URL and confidence level from this text. "
                    f"Set confidence to 'low' if no valid URL was found.\n\n{text}"
                ),
            }],
            output_format=RediscoveryResult,
        )
        return response.parsed_output
    except Exception:
        return RediscoveryResult(url=None, confidence="low", reasoning="parse_failed")


def parse_result(text: str, client) -> RediscoveryResult:
    """Try JSON parse first, fall back to Haiku extraction."""
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return RediscoveryResult(**data)
        except Exception:
            pass
    return parse_with_haiku(client, text)


def rediscover(client, school_name: str, city: str, state: str,
               rejection_reason: str, program_url: str,
               old_domain: str) -> RediscoveryResult:
    """
    Uses Claude Sonnet with web_search + web_fetch to find the correct URL.
    Returns a RediscoveryResult with url, confidence, and reasoning.
    """
    prompt = build_prompt(school_name, city, state, rejection_reason,
                          program_url, old_domain)

    tools = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209", "name": "web_fetch"},
    ]

    messages = [{"role": "user", "content": prompt}]

    for attempt in range(MAX_CONTINUATIONS):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )
        except anthropic.RateLimitError as e:
            wait = RATE_LIMIT_BACKOFF[min(attempt, len(RATE_LIMIT_BACKOFF) - 1)]
            try:
                wait = int(e.response.headers.get("retry-after", wait))
            except Exception:
                pass
            print(f"    Rate limited -- waiting {wait}s...")
            time.sleep(wait)
            continue
        except Exception as e:
            print(f"    API error: {e}")
            return RediscoveryResult(url=None, confidence="low", reasoning=str(e)[:200])

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if b.type == "text"), "")
            return parse_result(text, client)

        elif response.stop_reason == "pause_turn":
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response.content},
            ]
            continue

        else:
            print(f"    Unexpected stop_reason: {response.stop_reason}")
            break

    return RediscoveryResult(url=None, confidence="low", reasoning="max_continuations_reached")


def main():
    parser = argparse.ArgumentParser(description="Re-discover rejected PT fact sheet URLs")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true",
                        help="Re-run rows already attempted (rediscovery_status=not_found)")
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        print("  Option 1: export ANTHROPIC_API_KEY=your_key")
        print("  Option 2: add ANTHROPIC_API_KEY=your_key to .env file")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    df = load_csv(INPUT_FILE)
    if df.empty:
        print(f"ERROR: output/{INPUT_FILE} not found. Run earlier steps first.")
        sys.exit(1)

    if "validation_status" not in df.columns:
        print("No validation_status column found. Run 05_validate_urls.py first.")
        sys.exit(1)

    is_rejected = df["validation_status"] == "rejected"
    if args.force:
        to_process = df[is_rejected]
    else:
        if "rediscovery_status" not in df.columns:
            df["rediscovery_status"] = ""
        already_attempted = df["rediscovery_status"].isin(["found", "not_found"])
        to_process = df[is_rejected & ~already_attempted]

    if args.limit:
        to_process = to_process.head(args.limit)

    total = len(to_process)
    if total == 0:
        print("No rejected rows to re-discover. Use --force to retry not_found rows.")
        return

    print(f"\n{'='*60}")
    print(f"PT Fact Sheet URL Re-discovery")
    print(f"{'='*60}")
    print(f"Re-discovering {total} rejected rows...\n")

    found = not_found = low_confidence = 0

    for i, (_, row) in enumerate(to_process.iterrows()):
        program_id = row["program_id"]
        school_name = row["school_name"]
        city = row.get("city", "")
        state = row.get("state", "")
        rejection_reason = row.get("rejection_reason", "") or "unknown reason"
        program_url = row.get("program_url", "")
        old_url = row.get(URL_COL, "")
        old_domain = urlparse(old_url).netloc if old_url else ""

        print(f"[{i+1}/{total}] {school_name}")
        print(f"  Rejected: {rejection_reason[:100]}")
        if old_domain:
            reusing = not is_wrong_school(rejection_reason, old_domain)
            print(f"  Domain:   {old_domain} ({'reusing' if reusing else 'wrong school — skipping'})")

        result = rediscover(client, school_name, city, state, rejection_reason,
                            program_url, old_domain)

        if result.url and result.confidence in ("high", "medium"):
            found += 1
            print(f"  [FOUND] ({result.confidence}) {result.url[:80]}")
            print(f"  Reason: {result.reasoning}")
            upsert_record(INPUT_FILE, {
                "program_id": program_id,
                URL_COL: result.url,
                "rediscovery_status": "found",
                "validation_status": "",   # reset so 05 re-validates
                "rejection_reason": "",
            })
        elif result.url and result.confidence == "low":
            low_confidence += 1
            not_found += 1
            print(f"  [LOW CONFIDENCE] {result.reasoning}")
            upsert_record(INPUT_FILE, {
                "program_id": program_id,
                "rediscovery_status": "not_found",
            })
        else:
            not_found += 1
            print(f"  [NOT FOUND] {result.reasoning}")
            upsert_record(INPUT_FILE, {
                "program_id": program_id,
                "rediscovery_status": "not_found",
            })

        if i < total - 1:
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print(f"\n{'='*60}")
    print(f"Re-discovery complete.")
    print(f"  Found:          {found}")
    print(f"  Low confidence: {low_confidence}")
    print(f"  Not found:      {not_found - low_confidence}")
    if found:
        print(f"\nNext: python 05_validate_urls.py")
        print(f"      (validates the newly discovered URLs)")


if __name__ == "__main__":
    main()
