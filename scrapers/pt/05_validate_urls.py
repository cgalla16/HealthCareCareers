"""
05_validate_urls.py — Validate discovered PT fact sheet URLs using Claude Haiku + extract data.

Fetches each fact_sheet_url, asks Claude to:
  1. Confirm the page belongs to the correct school and DPT (not PTA) program
  2. Extract financial and outcome data if valid

Adds columns to pt_programs.csv:
  validation_status  — valid | rejected | fetch_failed | llm_error
  rejection_reason   — why it was rejected (empty if valid)
  tuition_per_year, total_program_cost, fees_per_year,
  graduation_rate_pct, board_pass_rate_pct, employment_rate_pct, data_year

Usage:
  python 05_validate_urls.py
  python 05_validate_urls.py --limit 5
  python 05_validate_urls.py --force
"""

import os
import sys
import io
import time
import random
import argparse

import requests
import anthropic
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

sys.path.insert(0, os.path.dirname(__file__))
from csv_store import load_csv, upsert_record

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
INPUT_FILE = "pt_programs.csv"
URL_COL = "fact_sheet_url"

MAX_PAGE_CHARS = 12000
DELAY_MIN = 1.5
DELAY_MAX = 3.0


class FactSheetExtraction(BaseModel):
    is_correct_page: bool
    rejection_reason: str
    tuition_per_year: Optional[int] = None          # dollars
    total_program_cost: Optional[int] = None        # dollars
    fees_per_year: Optional[int] = None             # dollars
    graduation_rate_pct: Optional[float] = None     # e.g. 92.5
    board_pass_rate_pct: Optional[float] = None     # NPTE first-time pass rate
    employment_rate_pct: Optional[float] = None
    data_year: Optional[str] = None                 # e.g. "2023-2024"


def fetch_page_text(url: str) -> tuple:
    """Fetch URL, return (text, status_tag). Returns ('', tag) on failure."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "").lower()
        is_pdf = "pdf" in content_type or url.lower().split("?")[0].endswith(".pdf")

        if is_pdf:
            if not HAS_PDFPLUMBER:
                return "", "pdf_unavailable"
            parts = []
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                for page in pdf.pages[:10]:
                    t = page.extract_text()
                    if t:
                        parts.append(t)
            return "\n".join(parts)[:MAX_PAGE_CHARS], "pdf"

        else:
            if HAS_BS4:
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["nav", "header", "footer", "script", "style", "aside"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
            else:
                text = resp.text
            return text[:MAX_PAGE_CHARS], "html"

    except requests.exceptions.HTTPError as e:
        return "", f"http_{e.response.status_code}"
    except requests.exceptions.Timeout:
        return "", "timeout"
    except Exception as e:
        return "", f"error_{type(e).__name__}"


def validate_and_extract(client, url: str, school_name: str) -> dict:
    """Fetch page and ask Claude to validate + extract. Returns update dict."""
    page_text, fetch_status = fetch_page_text(url)
    if not page_text:
        return {"validation_status": "fetch_failed", "rejection_reason": fetch_status}

    system = (
        "You are validating whether a web page is a Student Financial Fact Sheet for a specific "
        "DPT (Doctor of Physical Therapy) graduate program. "
        "Reject the page if it belongs to: a PTA (Physical Therapy Assistant) program, "
        "a different school, or is unrelated to PT financial/outcome data."
    )
    user_msg = (
        f"School: {school_name}\n"
        f"Program: Doctor of Physical Therapy (DPT)\n"
        f"URL: {url}\n\n"
        f"Page content:\n{page_text}\n\n"
        f"Does this page contain financial or outcome data for {school_name}'s DPT program? "
        f"Extract tuition, fees, total program cost, graduation rate, NPTE board pass rate, "
        f"and employment rate if present."
    )

    try:
        response = client.messages.parse(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            output_format=FactSheetExtraction,
        )
        result = response.parsed_output
        update = {
            "validation_status": "valid" if result.is_correct_page else "rejected",
            "rejection_reason": result.rejection_reason,
        }
        for field, value in result.model_dump().items():
            if field not in ("is_correct_page", "rejection_reason") and value is not None:
                update[field] = str(value)
        return update

    except Exception as e:
        return {"validation_status": "llm_error", "rejection_reason": str(e)[:200]}


def main():
    parser = argparse.ArgumentParser(description="Validate PT fact sheet URLs with Claude Haiku")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="Re-validate already-processed rows")
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        print("  Option 1: export ANTHROPIC_API_KEY=your_key")
        print("  Option 2: add ANTHROPIC_API_KEY=your_key to .env file")
        sys.exit(1)

    if not HAS_BS4:
        print("WARNING: beautifulsoup4 not installed -- pip install beautifulsoup4")
    if not HAS_PDFPLUMBER:
        print("WARNING: pdfplumber not installed -- pip install pdfplumber")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    df = load_csv(INPUT_FILE)
    if df.empty:
        print(f"ERROR: output/{INPUT_FILE} not found. Run earlier steps first.")
        sys.exit(1)

    has_url = df[URL_COL].notna() & (df[URL_COL] != "")

    done_statuses = ["valid", "rejected", "fetch_failed", "llm_error"]
    if args.force:
        to_process = df[has_url]
    else:
        if "validation_status" not in df.columns:
            df["validation_status"] = ""
        already_done = df["validation_status"].isin(done_statuses)
        to_process = df[has_url & ~already_done]

    if args.limit:
        to_process = to_process.head(args.limit)

    total = len(to_process)
    if total == 0:
        print("Nothing to process. Use --force to re-validate.")
        return

    print(f"\n{'='*60}")
    print(f"PT Fact Sheet Validation")
    print(f"{'='*60}")
    print(f"Processing {total} rows...\n")

    valid = rejected = failed = 0

    for i, (_, row) in enumerate(to_process.iterrows()):
        program_id = row["program_id"]
        school_name = row["school_name"]
        url = row[URL_COL]

        print(f"[{i+1}/{total}] {school_name}")
        print(f"  URL: {url[:80]}")

        result = validate_and_extract(client, url, school_name)
        result["program_id"] = program_id
        upsert_record(INPUT_FILE, result)

        status = result.get("validation_status", "?")
        reason = result.get("rejection_reason", "")
        if status == "valid":
            valid += 1
            print(f"  [VALID]")
        elif status == "rejected":
            rejected += 1
            print(f"  [REJECTED] {reason}")
        else:
            failed += 1
            print(f"  [FAILED] {reason}")

        if i < total - 1:
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print(f"\n{'='*60}")
    print(f"Done.")
    print(f"  Valid:    {valid}")
    print(f"  Rejected: {rejected}  -> run 06_rediscover_rejected.py")
    print(f"  Failed:   {failed}")


if __name__ == "__main__":
    main()
