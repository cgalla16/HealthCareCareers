"""
05_validate_urls.py — Validate discovered URLs using Claude Haiku + extract data.

Fetches each discovered URL, asks Claude to:
  1. Confirm the page belongs to the correct school and graduate program
  2. Extract program data (outcomes or tuition) if valid

Adds columns to the URL CSV:
  validation_status  — valid | rejected | fetch_failed | llm_error
  rejection_reason   — why it was rejected (empty if valid)
  + data fields depending on pipeline (graduation_rate_pct, tuition_per_year, etc.)

Usage:
  python 05_validate_urls.py --pipeline outcomes
  python 05_validate_urls.py --pipeline tuition
  python 05_validate_urls.py --pipeline outcomes --limit 5
  python 05_validate_urls.py --pipeline outcomes --force
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

# Optional deps — warn if missing
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

DEGREE_FULL = {
    "MOT": "Master of Occupational Therapy",
    "OTD": "Doctor of Occupational Therapy",
}

PIPELINES = {
    "outcomes": {
        "input_file": "ot_outcomes_urls.csv",
        "url_col": "discovered_url",
        "label": "OT Outcomes Validation",
        "data_desc": "graduation rate, NBCOT pass rate, cohort size, and employment rate",
        "reject_desc": "OTA (Occupational Therapy Assistant), associate-level, or a different school",
    },
    "tuition": {
        "input_file": "ot_tuition_urls.csv",
        "url_col": "discovered_url",
        "label": "OT Tuition Validation",
        "data_desc": "tuition per year, total program cost, and fees",
        "reject_desc": "OTA program, undergraduate tuition page, or a different school",
    },
}

MAX_PAGE_CHARS = 12000  # ~3k tokens of content
DELAY_MIN = 1.5
DELAY_MAX = 3.0


# --- Pydantic extraction schemas ---

class OutcomesExtraction(BaseModel):
    is_correct_page: bool
    rejection_reason: str
    graduation_rate_pct: Optional[float] = None      # e.g. 87.5
    cohort_size: Optional[int] = None
    nbcot_pass_rate_pct: Optional[float] = None
    employment_rate_pct: Optional[float] = None
    data_year: Optional[str] = None                  # e.g. "2023-2024"


class TuitionExtraction(BaseModel):
    is_correct_page: bool
    rejection_reason: str
    tuition_per_year: Optional[int] = None           # dollars
    total_program_cost: Optional[int] = None
    fees_per_year: Optional[int] = None
    data_year: Optional[str] = None


# --- Page fetching ---

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


# --- Claude validation + extraction ---

def validate_and_extract(client, url: str, school_name: str, degree_type: str, pipeline: str) -> dict:
    """Fetch page and ask Claude to validate + extract. Returns update dict."""
    cfg = PIPELINES[pipeline]
    degree_full = DEGREE_FULL.get(degree_type, degree_type)

    page_text, fetch_status = fetch_page_text(url)
    if not page_text:
        return {"validation_status": "fetch_failed", "rejection_reason": fetch_status}

    model_class = OutcomesExtraction if pipeline == "outcomes" else TuitionExtraction

    system = (
        f"You are validating whether a web page contains {pipeline} data for a specific "
        f"occupational therapy GRADUATE program. "
        f"Reject the page if it belongs to: {cfg['reject_desc']}."
    )
    user_msg = (
        f"School: {school_name}\n"
        f"Program: {degree_full} ({degree_type})\n"
        f"URL: {url}\n\n"
        f"Page content:\n{page_text}\n\n"
        f"Does this page contain {cfg['data_desc']} specifically for "
        f"{school_name}'s {degree_full} program? Extract the data if yes."
    )

    try:
        response = client.messages.parse(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            output_format=model_class,
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
    parser = argparse.ArgumentParser(description="Validate OT program URLs with Claude")
    parser.add_argument("--pipeline", required=True, choices=["outcomes", "tuition"])
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

    cfg = PIPELINES[args.pipeline]
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    df = load_csv(cfg["input_file"])
    if df.empty:
        print(f"ERROR: output/{cfg['input_file']} not found. Run earlier steps first.")
        sys.exit(1)

    url_col = cfg["url_col"]
    has_url = df[url_col].notna() & (df[url_col] != "")

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
    print(f"{cfg['label']}")
    print(f"{'='*60}")
    print(f"Processing {total} rows...\n")

    valid = rejected = failed = 0

    for i, (_, row) in enumerate(to_process.iterrows()):
        program_id = row["program_id"]
        school_name = row["school_name"]
        degree_type = row.get("degree_type", "OTD")
        url = row[url_col]

        print(f"[{i+1}/{total}] {school_name} ({degree_type})")
        print(f"  URL: {url[:80]}")

        result = validate_and_extract(client, url, school_name, degree_type, args.pipeline)
        result["program_id"] = program_id
        upsert_record(cfg["input_file"], result)

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
    print(f"  Rejected: {rejected}  -> review manually or supply URLs via 04_apply_manual.py")
    print(f"  Failed:   {failed}")


if __name__ == "__main__":
    main()
