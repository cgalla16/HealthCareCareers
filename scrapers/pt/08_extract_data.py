"""
08_extract_data.py — Extract program cost and length for PT programs.

Priority targets:
  1. program_length_months  (new column — not previously extracted)
  2. total_program_cost     (refresh if stale; add if missing)

Staleness threshold: data_year ending year < 2025.

Strategy per row:
  Case A — fresh data_year (>=2025), length missing → re-fetch source URL, extract length only
  Case B — stale/missing + apta_program_url valid (direct) → fetch apta, extract cost+length
  Case C — stale/missing + apta_program_url is landing page → sub-page discovery
  Case D — no apta, fallback to fact_sheet_url

Sub-page discovery: heuristic keyword scoring of links (no API call),
fetch top 3 candidate pages, merge best cost + length found.

Usage:
  python 08_extract_data.py
  python 08_extract_data.py --limit 5
  python 08_extract_data.py --force
  python 08_extract_data.py --stale-only
  python 08_extract_data.py --landing-only
"""

import os
import sys
import io
import re
import time
import random
import argparse
from urllib.parse import urljoin, urlparse

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

MAX_PAGE_CHARS = 10000
DELAY_MIN = 1.0
DELAY_MAX = 2.5
MAX_SUBPAGES = 3

COST_KEYWORDS = ["tuition", "cost", "fee", "financial", "afford", "price", "expenses"]
LENGTH_KEYWORDS = ["curriculum", "length", "duration", "schedule", "overview", "program-info",
                   "program_info", "about", "admission", "years", "months"]


# ── helpers ──────────────────────────────────────────────────────────────────

def ending_year(s) -> Optional[int]:
    """Extract the last 4-digit year from a data_year string like '2022-2023' → 2023."""
    nums = re.findall(r'\d{4}', str(s))
    return int(nums[-1]) if nums else None


def is_stale(data_year: str) -> bool:
    yr = ending_year(data_year)
    return (yr is None) or (yr < 2025)


def url_slug(url: str) -> str:
    """Return short path slug for extraction_notes, e.g. '/financial-info'."""
    path = urlparse(url).path.rstrip("/")
    return path[-40:] if path else "/"


# ── fetch ─────────────────────────────────────────────────────────────────────

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


def extract_links(url: str) -> list:
    """Fetch page and return list of (abs_url, anchor_text) for all <a href> links."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    if not HAS_BS4:
        return []
    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        links = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#") or href.startswith("mailto:"):
                continue
            abs_url = urljoin(base, href)
            # Stay on same domain
            if urlparse(abs_url).netloc != urlparse(url).netloc:
                continue
            if abs_url == url or abs_url in seen:
                continue
            seen.add(abs_url)
            links.append((abs_url, a.get_text(strip=True).lower()))
        return links
    except Exception:
        return []


def score_links(links: list) -> list:
    """Score (url, anchor_text) pairs by keyword relevance. Returns sorted list of (score, url)."""
    results = []
    for abs_url, anchor in links:
        path = urlparse(abs_url).path.lower()
        combined = anchor + " " + path
        cost_score = sum(1 for kw in COST_KEYWORDS if kw in combined)
        len_score = sum(1 for kw in LENGTH_KEYWORDS if kw in combined)
        total = cost_score * 2 + len_score  # cost weighted slightly higher
        if total > 0:
            results.append((total, abs_url))
    results.sort(reverse=True)
    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for score, url in results:
        if url not in seen:
            seen.add(url)
            deduped.append((score, url))
    return deduped


# ── Claude extraction ─────────────────────────────────────────────────────────

class DataExtraction(BaseModel):
    program_length_months: Optional[int] = None   # total DPT program duration in months
    total_program_cost: Optional[int] = None      # always the full-program total (computed if needed)
    tuition_per_year: Optional[int] = None        # annual figure for cross-check
    cost_basis: Optional[str] = None              # "total" | "per_year" | "per_semester" | "per_credit"
    cost_components: Optional[str] = None         # raw figures used, max 60 chars e.g. "1150/cr x 126cr"
    data_year: Optional[str] = None               # e.g. "2024-2025"
    notes: Optional[str] = None                   # max 80 chars


SYSTEM_PROMPT = (
    "Extract DPT program cost and duration only.\n\n"
    "COST RULES — always populate total_program_cost as the full-program dollar total:\n"
    "- Explicit total on page: use it, set cost_basis='total'\n"
    "- Per year stated: multiply by program years, set cost_basis='per_year'\n"
    "- Per semester stated: multiply by number of semesters, set cost_basis='per_semester'\n"
    "- Per credit hour stated: multiply rate by total credits, set cost_basis='per_credit'\n"
    "- Multiple formats present: prefer explicit total, else compute\n"
    "- Set cost_components to the raw figures used (max 60 chars, e.g. '9500/sem x 9sem' or '1150/cr x 126cr')\n"
    "- Set tuition_per_year to annual figure if stated or derivable\n"
    "- Return null for total_program_cost only if no cost data present at all\n\n"
    "LENGTH: program_length_months = total program duration in months (DPT typically 30-36).\n"
    "DATA YEAR: academic year the figures apply to (e.g. 2024-2025).\n"
    "notes: max 80 chars, terse."
)


def extract_from_page(client, url: str, school_name: str, page_text: str) -> DataExtraction:
    """Call Claude Haiku to extract cost + length from pre-fetched page text."""
    user_msg = (
        f"School: {school_name} (DPT program)\n"
        f"URL: {url}\n\n"
        f"{page_text}"
    )
    response = client.messages.parse(
        model="claude-haiku-4-5",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        output_format=DataExtraction,
    )
    return response.parsed_output


# ── per-row strategies ────────────────────────────────────────────────────────

def try_direct(client, url: str, school_name: str) -> tuple:
    """Fetch url and extract. Returns (DataExtraction or None, fetch_status)."""
    text, status = fetch_page_text(url)
    if not text:
        return None, status
    try:
        result = extract_from_page(client, url, school_name, text)
        return result, "ok"
    except Exception as e:
        return None, f"llm_error:{str(e)[:60]}"


def try_subpages(client, landing_url: str, school_name: str) -> tuple:
    """
    Discover and fetch sub-pages from landing_url.
    Returns (merged DataExtraction or None, extraction_notes_suffix).
    """
    links = extract_links(landing_url)
    if not links:
        return None, "no_links"

    scored = score_links(links)
    candidates = [url for _, url in scored[:MAX_SUBPAGES]]

    if not candidates:
        return None, "no_scored_links"

    best_length = None
    best_cost = None
    best_tpy = None
    best_year = None
    length_src = ""
    cost_src = ""
    notes_parts = []

    for sub_url in candidates:
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
        text, status = fetch_page_text(sub_url)
        if not text:
            notes_parts.append(f"fetch_failed:{url_slug(sub_url)}")
            continue
        try:
            result = extract_from_page(client, sub_url, school_name, text)
        except Exception as e:
            notes_parts.append(f"llm_err:{url_slug(sub_url)}")
            continue

        slug = url_slug(sub_url)
        if result.program_length_months and best_length is None:
            best_length = result.program_length_months
            length_src = slug
        if result.total_program_cost and best_cost is None:
            best_cost = result.total_program_cost
            cost_src = slug
        if result.tuition_per_year and best_tpy is None:
            best_tpy = result.tuition_per_year
        if result.data_year and best_year is None:
            best_year = result.data_year

        if best_length and best_cost:
            break  # got everything we need

    if best_length is None and best_cost is None and best_tpy is None:
        return None, "subpages_no_data"

    merged = DataExtraction(
        program_length_months=best_length,
        total_program_cost=best_cost,
        tuition_per_year=best_tpy,
        data_year=best_year,
    )
    note = ""
    if best_cost:
        note += f"cost:sub{cost_src}"
    if best_length:
        note += ("|" if note else "") + f"len:sub{length_src}"
    return merged, note


# ── main ──────────────────────────────────────────────────────────────────────

def build_update(program_id, result: DataExtraction, note: str,
                 existing_year: str, force_cost: bool = False) -> dict:
    """
    Build upsert dict. Only overwrites cost/year fields if result is fresher (or force_cost=True).
    Always writes program_length_months if found.
    """
    update = {"program_id": program_id}

    # Program length — always take new value if found
    if result.program_length_months:
        update["program_length_months"] = str(result.program_length_months)

    # Cost fields — overwrite if new data is fresher, first time, or forced
    new_yr = ending_year(result.data_year or "")
    old_yr = ending_year(existing_year or "")
    is_fresher = (new_yr or 0) > (old_yr or 0)
    is_first = not old_yr  # no existing data at all

    if is_fresher or is_first or force_cost:
        if result.total_program_cost:
            update["total_program_cost"] = str(result.total_program_cost)
        if result.tuition_per_year:
            update["tuition_per_year"] = str(result.tuition_per_year)
        if result.data_year:
            update["data_year"] = result.data_year

    # Audit fields — always written (describe the extraction itself, not the data vintage)
    if result.cost_basis:
        update["cost_basis"] = result.cost_basis
    if result.cost_components:
        update["cost_components"] = result.cost_components

    update["extraction_notes"] = note[:100]
    return update


def main():
    parser = argparse.ArgumentParser(description="Extract PT program cost and length")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="Reprocess rows already extracted")
    parser.add_argument("--recalculate-cost", action="store_true",
                        help="Overwrite existing cost data regardless of data_year (use after prompt changes)")
    parser.add_argument("--stale-only", action="store_true", help="Only rows with stale/missing data")
    parser.add_argument("--landing-only", action="store_true", help="Only confirmed_landing rows")
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
        print(f"ERROR: output/{INPUT_FILE} not found.")
        sys.exit(1)

    # Ensure new columns exist
    for col in ("program_length_months", "extraction_notes"):
        if col not in df.columns:
            df[col] = ""

    def _row_needs_processing(row) -> bool:
        if args.force:
            return True
        has_length = str(row.get("program_length_months", "")).strip() not in ("", "None")
        data_yr = str(row.get("data_year", "")).strip()
        stale = is_stale(data_yr)
        if args.stale_only:
            return stale
        if args.landing_only:
            return row.get("validation_status", "") == "confirmed_landing"
        # Default: process if missing length OR data is stale
        return (not has_length) or stale

    def _has_viable_url(row) -> bool:
        apta = str(row.get("apta_program_url", "")).strip()
        fact = str(row.get("fact_sheet_url", "")).strip()
        return bool(apta or fact)

    to_process = df[df.apply(_row_needs_processing, axis=1) & df.apply(_has_viable_url, axis=1)]

    if args.limit:
        to_process = to_process.head(args.limit)

    total = len(to_process)
    if total == 0:
        print("Nothing to process. Use --force to reprocess all rows.")
        return

    print(f"\n{'='*60}")
    print(f"PT Data Extraction  ({total} rows)")
    print(f"{'='*60}\n")

    done = skipped = 0

    for i, (_, row) in enumerate(to_process.iterrows()):
        program_id = row["program_id"]
        school_name = row["school_name"]
        apta_url = str(row.get("apta_program_url", "")).strip()
        fact_url = str(row.get("fact_sheet_url", "")).strip()
        extracted_from = str(row.get("extracted_from_url", "")).strip()
        data_yr = str(row.get("data_year", "")).strip()
        vstatus = str(row.get("validation_status", "")).strip()
        apta_confirmed = str(row.get("apta_landing_confirmed", "")).strip().lower() == "true"
        has_length = str(row.get("program_length_months", "")).strip() not in ("", "None")
        stale = is_stale(data_yr)

        print(f"[{i+1}/{total}] {school_name}  status={vstatus}  stale={stale}  has_len={has_length}")

        result = None
        note = ""

        # ── Case A: fresh data, only need length ──────────────────────────────
        if not stale and not has_length:
            src = extracted_from or fact_url or apta_url
            if src:
                print(f"  Case A: re-fetch source for length  {src[:70]}")
                result, fstatus = try_direct(client, src, school_name)
                if result:
                    note = f"len:{url_slug(src)}"
                    # Don't overwrite fresh cost data — only take length
                    update = {"program_id": program_id}
                    if result.program_length_months:
                        update["program_length_months"] = str(result.program_length_months)
                    update["extraction_notes"] = note[:100]
                    upsert_record(INPUT_FILE, update)
                    print(f"  length={result.program_length_months}mo")
                    done += 1
                else:
                    print(f"  [FAILED] {fstatus}")
                    skipped += 1
            else:
                print("  [SKIP] no source URL")
                skipped += 1

        # ── Case B: stale/missing + apta direct (known valid from apta) ──────
        elif stale and apta_url and apta_confirmed and extracted_from == apta_url:
            print(f"  Case B: apta direct  {apta_url[:70]}")
            result, fstatus = try_direct(client, apta_url, school_name)
            if result:
                note = "cost+len:apta_direct"
                upsert_record(INPUT_FILE, build_update(program_id, result, note, data_yr, force_cost=args.recalculate_cost))
                print(f"  cost={result.total_program_cost}  length={result.program_length_months}mo  year={result.data_year}")
                done += 1
            else:
                print(f"  [FAILED] {fstatus} — falling through to sub-page")
                # Fall through to Case C if apta_url still available
                vstatus = "confirmed_landing"  # treat as landing for fallback
                result = None

        # ── Case C: stale/missing + apta landing page (sub-page discovery) ───
        if stale and apta_url and result is None and vstatus in ("confirmed_landing", "valid", ""):
            print(f"  Case C: sub-page discovery  {apta_url[:70]}")
            result, sub_note = try_subpages(client, apta_url, school_name)
            if result:
                note = sub_note
                upsert_record(INPUT_FILE, build_update(program_id, result, note, data_yr, force_cost=args.recalculate_cost))
                print(f"  cost={result.total_program_cost}  length={result.program_length_months}mo  year={result.data_year}")
                done += 1
            else:
                print(f"  [NO DATA from subpages: {sub_note}] — trying fact_sheet fallback")
                result = None

        # ── Case D: fallback to fact_sheet_url ────────────────────────────────
        if result is None and fact_url and (stale or not has_length):
            print(f"  Case D: fact_sheet fallback  {fact_url[:70]}")
            result, fstatus = try_direct(client, fact_url, school_name)
            if result:
                stale_tag = "_stale" if stale else ""
                note = f"cost+len:fact_sheet{stale_tag}"
                upsert_record(INPUT_FILE, build_update(program_id, result, note, data_yr, force_cost=args.recalculate_cost))
                print(f"  cost={result.total_program_cost}  length={result.program_length_months}mo  year={result.data_year}")
                done += 1
            else:
                print(f"  [FAILED] {fstatus}")
                skipped += 1

        elif result is None and not (stale or not has_length):
            pass  # already handled above (Case A or already complete)

        if i < total - 1:
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print(f"\n{'='*60}")
    print(f"Done.  Extracted: {done}  Skipped/failed: {skipped}")


if __name__ == "__main__":
    main()
