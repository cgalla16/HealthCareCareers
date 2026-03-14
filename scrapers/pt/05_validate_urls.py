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
import re
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

MAX_PAGE_CHARS = 12000
DELAY_MIN = 1.5
DELAY_MAX = 3.0


def ending_year(s):
    """Extract the last 4-digit year from a data_year string like '2022-2023' → 2023."""
    nums = re.findall(r'\d{4}', str(s))
    return int(nums[-1]) if nums else None


class FactSheetExtraction(BaseModel):
    is_correct_school: bool   # True if this page belongs to the correct school's DPT program
    is_correct_page: bool     # True if this page actually contains financial/outcome data
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
        "You are validating web pages for a DPT (Doctor of Physical Therapy) program data pipeline. "
        "For each page, set two flags independently:\n"
        "  is_correct_school: True if this page belongs to the correct school's DPT program "
        "(even if it's just a general overview/landing page with no financial data).\n"
        "  is_correct_page: True only if this page actually contains financial or outcome data "
        "(tuition, fees, total cost, graduation rate, board pass rate, employment rate).\n"
        "Set is_correct_school=False if: wrong school, PTA program, or completely unrelated page.\n"
        "Set is_correct_page=False if: correct school but data is absent or on a linked sub-page."
    )
    user_msg = (
        f"School: {school_name}\n"
        f"Program: Doctor of Physical Therapy (DPT)\n"
        f"URL: {url}\n\n"
        f"Page content:\n{page_text}\n\n"
        f"Is this page for {school_name}'s DPT program? Does it contain financial or outcome data? "
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
        if result.is_correct_page:
            status = "valid"
        elif result.is_correct_school:
            status = "confirmed_landing"  # right school/program, data on a sub-page
        else:
            status = "rejected"           # wrong school, PTA, or unrelated
        update = {
            "validation_status": status,
            "rejection_reason": result.rejection_reason,
        }
        for field, value in result.model_dump().items():
            if field not in ("is_correct_school", "is_correct_page", "rejection_reason") and value is not None:
                update[field] = str(value)
        return update

    except Exception as e:
        return {"validation_status": "llm_error", "rejection_reason": str(e)[:200]}


def main():
    parser = argparse.ArgumentParser(description="Validate PT fact sheet URLs with Claude Haiku")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="Re-validate already-processed rows")
    parser.add_argument("--retry-rejected", action="store_true", help="Re-process rejected/fetch_failed rows (skips valid and confirmed_landing)")
    parser.add_argument("--apta-only", action="store_true", help="Only try apta_program_url, skip fact_sheet_url (use when fact_sheet_url was already rejected)")
    parser.add_argument("--retry-stale", action="store_true", help="Re-check valid rows with data older than --stale-before against apta_program_url only; keeps existing data unless newer data found")
    parser.add_argument("--stale-before", type=int, default=2024, help="Ending year threshold for stale detection (default: 2024)")
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

    # Drop fact_sheet_url_2 — lower-confidence backup, superseded by apta_program_url
    if "fact_sheet_url_2" in df.columns:
        df = df.drop(columns=["fact_sheet_url_2"])
        from csv_store import save_csv
        save_csv(df, INPUT_FILE)
        print("Dropped fact_sheet_url_2 column from pt_programs.csv")

    for col in ("fact_sheet_url", "apta_program_url"):
        if col not in df.columns:
            df[col] = ""

    has_url = (df["fact_sheet_url"].notna() & (df["fact_sheet_url"] != "")) | \
              (df["apta_program_url"].notna() & (df["apta_program_url"] != ""))

    if "validation_status" not in df.columns:
        df["validation_status"] = ""

    done_statuses = ["valid", "confirmed_landing", "rejected", "fetch_failed", "llm_error"]
    if args.force:
        to_process = df[has_url]
    elif args.retry_stale:
        valid_rows = df[df["validation_status"] == "valid"]
        stale_mask = valid_rows["data_year"].apply(
            lambda dy: (ending_year(dy) or 9999) < args.stale_before
        ) if "data_year" in valid_rows.columns else valid_rows.index.map(lambda _: True)
        to_process = valid_rows[stale_mask]
        args.apta_only = True  # retry-stale always uses apta_program_url only
    elif args.retry_rejected:
        retry_statuses = ["rejected", "fetch_failed", "llm_error"]
        to_process = df[has_url & df["validation_status"].isin(retry_statuses)]
    else:
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

    STATUS_PRIORITY = {"valid": 4, "confirmed_landing": 3, "rejected": 2, "fetch_failed": 1, "llm_error": 0}
    valid = confirmed = rejected = failed = 0
    upgraded = flagged = kept_stale = 0

    for i, (_, row) in enumerate(to_process.iterrows()):
        program_id = row["program_id"]
        school_name = row["school_name"]

        # Build deduplicated candidate list
        candidates = []
        fsu = str(row.get("fact_sheet_url", "")).strip()
        apu = str(row.get("apta_program_url", "")).strip()
        if fsu and not args.apta_only:
            candidates.append(fsu)
        if apu and apu != fsu:
            candidates.append(apu)

        print(f"[{i+1}/{total}] {school_name} ({len(candidates)} URL(s) to try)")

        best_result = {"validation_status": "fetch_failed", "rejection_reason": "no_url"}
        apta_confirmed = False  # True if apta_program_url verified as correct school's DPT page

        for url in candidates:
            print(f"  Trying: {url[:80]}")
            result = validate_and_extract(client, url, school_name)
            cur_priority = STATUS_PRIORITY.get(result["validation_status"], 0)
            best_priority = STATUS_PRIORITY.get(best_result["validation_status"], 0)
            if cur_priority > best_priority:
                best_result = result
            if result["validation_status"] in ("valid", "confirmed_landing") and url == apu:
                apta_confirmed = True
            if result["validation_status"] == "valid":
                best_result["extracted_from_url"] = url
                break
            else:
                s = result.get("validation_status", "?").upper()
                reason = result.get("rejection_reason", "")
                suffix = " — trying next URL" if url != candidates[-1] else ""
                print(f"  [{s}] {reason}{suffix}")
            if url != candidates[-1]:
                time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        if best_result["validation_status"] != "valid":
            best_result["extracted_from_url"] = ""

        if args.retry_stale:
            # Protect existing valid data — only overwrite if we found genuinely newer data
            new_status = best_result.get("validation_status")
            new_year = ending_year(best_result.get("data_year", ""))
            old_year = ending_year(str(row.get("data_year", "")))

            if new_status == "valid" and (new_year or 0) > (old_year or 0):
                best_result["apta_landing_confirmed"] = "True"
                best_result["program_id"] = program_id
                upsert_record(INPUT_FILE, best_result)
                upgraded += 1
                print(f"  [UPGRADED] {old_year} -> {new_year}")
            elif apta_confirmed:
                upsert_record(INPUT_FILE, {"program_id": program_id, "apta_landing_confirmed": "True"})
                flagged += 1
                print(f"  [KEPT + FLAGGED] existing {old_year} data kept, APTA URL confirmed for sub-page crawl")
            else:
                kept_stale += 1
                print(f"  [KEPT] APTA URL rejected or failed, existing data unchanged")
        else:
            if apta_confirmed:
                best_result["apta_landing_confirmed"] = "True"
            best_result["program_id"] = program_id
            upsert_record(INPUT_FILE, best_result)

            status = best_result.get("validation_status", "?")
            if status == "valid":
                valid += 1
                print(f"  [VALID] from {best_result.get('extracted_from_url', '')[:60]}")
            elif status == "confirmed_landing":
                confirmed += 1
                print(f"  [CONFIRMED LANDING] correct school/program, data on sub-page")
            elif status == "rejected":
                rejected += 1
            else:
                failed += 1

        if i < total - 1:
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print(f"\n{'='*60}")
    print(f"Done.")
    if args.retry_stale:
        print(f"  Upgraded (newer data found):       {upgraded}")
        print(f"  Kept + flagged for sub-page crawl: {flagged}")
        print(f"  Kept (APTA URL unhelpful):         {kept_stale}")
    else:
        print(f"  Valid:              {valid}")
        print(f"  Confirmed landing:  {confirmed}  (correct program page, data on sub-page)")
        print(f"  Rejected:           {rejected}  (wrong school/PTA/unrelated)")
        print(f"  Failed:             {failed}")


if __name__ == "__main__":
    main()
