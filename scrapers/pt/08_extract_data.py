"""
08_extract_data.py — Extract program cost and length for PT programs.

Priority targets:
  1. program_length_months  (new column — not previously extracted)
  2. total_program_cost     (refresh if stale; add if missing)

Staleness threshold: data_year ending year < 2025.

Strategy per row:
  Fresh  — data_year >=2025, length or cost missing → re-fetch source, fall through to subpages
  Stale  — try apta_url direct → subpages (apta + outcomes_url) → trusted fact_sheet fallback

Sub-page discovery: keyword-scored links from apta_url + outcomes_url merged,
fetch top MAX_SUBPAGES candidates, merge best cost + length found.

Usage:
  python 08_extract_data.py
  python 08_extract_data.py --limit 5
  python 08_extract_data.py --force
  python 08_extract_data.py --stale-only
  python 08_extract_data.py --landing-only
  python 08_extract_data.py --recalculate-cost
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
from typing import Optional, Literal

VALID_COST_BASIS = {"total", "per_year", "per_semester", "per_credit"}
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

MAX_PAGE_CHARS = 20000
DELAY_MIN = 1.0
DELAY_MAX = 2.5
MAX_SUBPAGES = 5

COST_KEYWORDS = ["tuition", "cost", "fee", "financial", "afford", "price", "expenses",
                 "fact-sheet", "factsheet", "fact_sheet"]
LENGTH_KEYWORDS = ["curriculum", "length", "duration", "schedule", "overview", "program-info",
                   "program_info", "about", "admission", "years", "months"]
SKIP_PATH_FRAGMENTS = ["netpricecalculator", "net-price-calculator", "netprice",
                       "concerned-about", "student-wellness", "counseling"]


# ── helpers ──────────────────────────────────────────────────────────────────

def same_domain(url1: str, url2: str) -> bool:
    """Return True if both URLs share the same registered domain (last 2 parts of hostname)."""
    def root(u):
        host = urlparse(u).netloc.lower().split(":")[0]
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host
    return bool(url1 and url2 and root(url1) == root(url2))


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
                    # Extract fillable form field values (e.g. FPTA financial fact sheets)
                    field_lines = []
                    for annot in page.annots:
                        data = annot.get("data", {})
                        title = data.get("T", b"")
                        value = data.get("V", None)
                        if isinstance(title, bytes):
                            title = title.decode("latin-1", errors="replace")
                        if isinstance(value, bytes):
                            value = value.decode("latin-1", errors="replace")
                        elif value is not None:
                            value = str(value)
                        skip_defaults = {"Choose Response", "Choose Program", ""}
                        if value and value.strip() and value not in skip_defaults:
                            field_lines.append(f"[FORM FIELD] {title}: {value}")
                    if field_lines:
                        parts.append("\n".join(field_lines))
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
        # Skip .docx (unreadable) and .pdf when pdfplumber unavailable
        if path.endswith(".docx"):
            continue
        if path.endswith(".pdf") and not HAS_PDFPLUMBER:
            continue
        # Skip pages that won't have fixed cost figures
        if any(frag in path for frag in SKIP_PATH_FRAGMENTS):
            continue
        combined = anchor + " " + path
        cost_score = sum(1 for kw in COST_KEYWORDS if kw in combined)
        len_score = sum(1 for kw in LENGTH_KEYWORDS if kw in combined)
        fact_sheet_boost = 2 if any(p in combined for p in ["fact sheet", "financial fact", "fact-sheet", "factsheet"]) else 0
        total = cost_score * 2 + len_score + fact_sheet_boost
        if total > 0:
            results.append((total, abs_url))
    results.sort(reverse=True)
    seen = set()
    deduped = []
    for score, url in results:
        if url not in seen:
            seen.add(url)
            deduped.append((score, url))
    return deduped


# ── Claude extraction ─────────────────────────────────────────────────────────

class DataExtraction(BaseModel):
    program_length_months: Optional[int] = None
    total_program_cost: Optional[int] = None      # always the full-program total (computed if needed)
    tuition_per_year: Optional[int] = None        # annual OOS rate for public schools; only rate for private
    tuition_instate: Optional[int] = None         # in-state annual rate (public schools only)
    tuition_is_oos: Optional[bool] = None         # True if tuition_per_year is the out-of-state rate
    cost_basis: Optional[Literal["total", "per_year", "per_semester", "per_credit"]] = None
    cost_components: Optional[str] = None         # raw figures used, max 60 chars e.g. "1150/cr x 126cr"
    data_year: Optional[str] = None               # e.g. "2024-2025"
    notes: Optional[str] = None                   # max 80 chars


SYSTEM_PROMPT = (
    "RESIDENCY GUARD: If the page is clearly about a postgraduate residency or fellowship program "
    "(not an entry-level DPT degree), return ALL fields as null and set "
    "notes='RESIDENCY_SKIP: not entry-level DPT'. Indicators: page title or headings contain "
    "'Residency', 'Fellowship', 'post-professional', or 'post-graduate residency'.\n\n"
    "Extract DPT program cost and duration only.\n\n"
    "COST RULES — always populate total_program_cost as the full-program dollar total:\n"
    "- Explicit total on page: use it, set cost_basis='total'\n"
    "- Per year stated: multiply by program_length_YEARS from the length hint (the X.X years value, "
    "NOT the months value; DPT is typically 3 years if no hint), set cost_basis='per_year'\n"
    "- Per semester stated: multiply by number of semesters from the length hint "
    "(the X.X semesters value; DPT is typically 6 semesters if no hint), set cost_basis='per_semester'\n"
    "- Per credit hour stated: multiply rate by total credits, set cost_basis='per_credit'\n"
    "- Multiple formats present: prefer explicit total, else compute\n"
    "- cost_basis MUST be exactly one of: total, per_year, per_semester, per_credit\n"
    "- Set cost_components to the raw figures used (max 60 chars, e.g. '9500/sem x 9sem' or '1150/cr x 126cr')\n"
    "- Set tuition_per_year to annual figure if stated or derivable\n"
    "- Return null for total_program_cost only if no cost data present at all\n\n"
    "CALC CHECK: After computing total_program_cost, verify: "
    "total_program_cost / tuition_per_year must approximately equal program years (typically 2-5). "
    "If the ratio exceeds 6, you have a calculation error — recheck and correct before returning.\n\n"
    "RESIDENCY RULES:\n"
    "- If BOTH in-state AND out-of-state tuition rates are visible, extract BOTH separately:\n"
    "  * tuition_per_year = out-of-state rate, tuition_instate = in-state rate, tuition_is_oos=true\n"
    "  * NEVER add them together — they are two separate rates, not addends\n"
    "- If only one rate is shown and it is unusually low (e.g. under $12,000/yr), set tuition_is_oos=false\n"
    "- For private institutions (no in-state/out-of-state distinction): set tuition_is_oos=false\n"
    "- Leave tuition_is_oos=null only when residency cannot be determined\n\n"
    "RANGE SANITY (flag but still extract):\n"
    "- Per-year tuition outside $8,000-$85,000: set notes to 'RANGE_WARN: {value}/yr'\n"
    "- Total program cost outside $50,000-$280,000: set notes to 'RANGE_WARN: {value} total'\n"
    "- Per-credit rate outside $500-$2,500: flag similarly in notes\n\n"
    "LENGTH: program_length_months = total program duration in months (DPT typically 30-36).\n"
    "DATA YEAR: academic year the figures apply to (e.g. 2024-2025).\n"
    "notes: max 80 chars, terse. Use for RANGE_WARN or other anomalies only."
)


def extract_from_page(client, url: str, school_name: str, page_text: str,
                      known_length_months: Optional[int] = None) -> DataExtraction:
    """Call Claude Haiku to extract cost + length from pre-fetched page text."""
    length_hint = (
        f"\nKnown program length: {known_length_months / 12:.1f} YEARS ({known_length_months} months). "
        f"Per-year costs: multiply by {known_length_months / 12:.1f}. "
        f"Per-semester costs: multiply by {known_length_months / 6:.1f} semesters."
        if known_length_months else ""
    )
    user_msg = (
        f"School: {school_name} (DPT program){length_hint}\n"
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


# ── extraction primitives ─────────────────────────────────────────────────────

def try_direct(client, url: str, school_name: str,
               known_length_months: Optional[int] = None) -> tuple:
    """Fetch url and extract. Returns (DataExtraction or None, fetch_status)."""
    text, status = fetch_page_text(url)
    if not text:
        return None, status
    try:
        result = extract_from_page(client, url, school_name, text, known_length_months)
        return result, "ok"
    except Exception as e:
        return None, f"llm_error:{str(e)[:60]}"


def try_subpages(client, landing_url: str, school_name: str,
                 known_length_months: Optional[int] = None,
                 extra_url: Optional[str] = None) -> tuple:
    """
    Discover and fetch sub-pages from landing_url (and optionally extra_url).
    Returns (merged DataExtraction or None, extraction_notes_suffix).
    """
    links = extract_links(landing_url)
    if extra_url and extra_url != landing_url:
        extra_links = extract_links(extra_url)
        seen_urls = {url for url, _ in links}
        for link in extra_links:
            if link[0] not in seen_urls:
                links.append(link)
                seen_urls.add(link[0])
    if not links:
        return None, "no_links"

    scored = score_links(links)
    candidates = [url for _, url in scored[:MAX_SUBPAGES]]
    if not candidates:
        return None, "no_scored_links"

    best_length = None
    best_cost = None
    best_tpy = None
    best_tpy_instate = None
    best_is_oos = None
    best_year = None
    length_src = ""
    cost_src = ""

    for sub_url in candidates:
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
        text, status = fetch_page_text(sub_url)
        if not text:
            continue
        try:
            result = extract_from_page(client, sub_url, school_name, text, known_length_months)
        except Exception:
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
        if result.tuition_instate and best_tpy_instate is None:
            best_tpy_instate = result.tuition_instate
        if result.tuition_is_oos is not None and best_is_oos is None:
            best_is_oos = result.tuition_is_oos
        if result.data_year and best_year is None:
            best_year = result.data_year
        if best_length and best_cost:
            break

    if best_length is None and best_cost is None and best_tpy is None:
        return None, "subpages_no_data"

    merged = DataExtraction(
        program_length_months=best_length,
        total_program_cost=best_cost,
        tuition_per_year=best_tpy,
        tuition_instate=best_tpy_instate,
        tuition_is_oos=best_is_oos,
        data_year=best_year,
    )
    note = ""
    if best_cost:
        note += f"cost:sub{cost_src}"
    if best_length:
        note += ("|" if note else "") + f"len:sub{length_src}"
    return merged, note


def _merge_cost(base: DataExtraction, src: DataExtraction):
    """Merge cost fields from src into base in-place."""
    base.total_program_cost = src.total_program_cost
    base.tuition_per_year = src.tuition_per_year or base.tuition_per_year
    base.data_year = src.data_year or base.data_year
    base.cost_basis = src.cost_basis
    base.cost_components = src.cost_components


# ── per-row strategy ──────────────────────────────────────────────────────────

def _extract_for_row(client, args, *, school_name, apta_url, fact_url, outcomes_url,
                     extracted_from, vstatus, stale, known_len, has_reliable_cost):
    """
    Try sources in priority order. Returns (DataExtraction | None, note, force_cost).

    Fresh path  — data current (>=2025): re-fetch known source, fall through to subpages if cost null.
    Stale path  — try apta direct → subpages (apta + outcomes) → trusted fact_sheet fallback.
    """
    trusted_fact = fact_url if same_domain(fact_url, apta_url) else ""
    if fact_url and not trusted_fact:
        print(f"  [domain mismatch] fact_sheet_url ignored — different school")

    # ── Fresh path ────────────────────────────────────────────────────────────
    if not stale:
        src = extracted_from or trusted_fact or apta_url
        if not src:
            return None, "no_url", False
        label = "len+cost" if not has_reliable_cost else "len"
        print(f"  fresh: {label}  {src[:70]}")
        result, _ = try_direct(client, src, school_name, known_len)
        if result and not result.total_program_cost and apta_url:
            print(f"  fresh→subpages: cost null, discovering")
            sub, sub_note = try_subpages(client, apta_url, school_name,
                                         known_len or result.program_length_months,
                                         extra_url=outcomes_url)
            if sub and sub.total_program_cost:
                _merge_cost(result, sub)
                return result, f"{label}:{url_slug(src)}+{sub_note}", False
        if result:
            return result, f"{label}:{url_slug(src)}", False
        return None, "fetch_failed", False

    # ── Stale path ────────────────────────────────────────────────────────────
    if apta_url and vstatus in ("confirmed_landing", "valid", ""):
        # Step 1: try apta_url directly — many pages now embed cost in HTML
        print(f"  stale→apta direct  {apta_url[:70]}")
        result, _ = try_direct(client, apta_url, school_name, known_len)
        if result and result.total_program_cost:
            return result, "cost+len:apta_direct", True

        # Step 2: apta direct had no cost — discover sub-pages (apta + outcomes)
        print(f"  stale→subpages")
        length_hint = known_len or (result.program_length_months if result else None)
        sub, sub_note = try_subpages(client, apta_url, school_name, length_hint,
                                     extra_url=outcomes_url)
        if sub:
            if result and sub.total_program_cost:
                _merge_cost(result, sub)
                return result, f"cost+len:apta_direct+{sub_note}", True
            return sub, sub_note, True

    # Step 3: fallback to fact_sheet_url (only same-domain, not superseded)
    fact_superseded = bool(extracted_from and extracted_from != fact_url)
    if trusted_fact and not fact_superseded:
        print(f"  stale→fact_sheet  {trusted_fact[:70]}")
        result, _ = try_direct(client, trusted_fact, school_name, known_len)
        if result:
            return result, "cost+len:fact_sheet_stale", True

    return None, "all_sources_failed", False


# ── main ──────────────────────────────────────────────────────────────────────

def build_update(program_id, result: DataExtraction, note: str,
                 existing_year: str, force_cost: bool = False) -> dict:
    """
    Build upsert dict. Only overwrites cost/year fields if result is fresher (or force_cost=True).
    Always writes program_length_months if found.
    """
    update = {"program_id": program_id}

    if result.program_length_months:
        update["program_length_months"] = str(result.program_length_months)

    new_yr = ending_year(result.data_year or "")
    old_yr = ending_year(existing_year or "")
    is_fresher = (new_yr or 0) > (old_yr or 0)
    is_first = not old_yr

    if is_fresher or is_first or force_cost:
        if result.total_program_cost:
            update["total_program_cost"] = str(result.total_program_cost)
        if result.tuition_per_year:
            update["tuition_per_year"] = str(result.tuition_per_year)
        if result.tuition_instate:
            update["tuition_instate"] = str(result.tuition_instate)
        if result.tuition_is_oos is not None:
            update["tuition_is_oos"] = "yes" if result.tuition_is_oos else "no"
        if result.data_year:
            update["data_year"] = result.data_year

    if result.cost_basis:
        update["cost_basis"] = result.cost_basis
    if result.cost_components:
        update["cost_components"] = result.cost_components

    llm_notes = getattr(result, "notes", None) or ""
    combined = f"{note}|{llm_notes}" if llm_notes else note
    update["extraction_notes"] = combined[:120]
    return update


def main():
    parser = argparse.ArgumentParser(description="Extract PT program cost and length")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="Reprocess rows already extracted")
    parser.add_argument("--recalculate-cost", action="store_true",
                        help="Overwrite existing cost data regardless of data_year (use after prompt changes)")
    parser.add_argument("--stale-only", action="store_true", help="Only rows with stale/missing data")
    parser.add_argument("--landing-only", action="store_true", help="Only confirmed_landing rows")
    parser.add_argument("--program-ids", type=str, default=None,
                        help="Comma-separated program IDs to force-reprocess (e.g. 19,192,170)")
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

    for col in ("program_length_months", "extraction_notes"):
        if col not in df.columns:
            df[col] = ""

    target_ids = set(x.strip() for x in args.program_ids.split(",")) if args.program_ids else None

    def _row_needs_processing(row) -> bool:
        pid = str(row.get("program_id", "")).strip()
        if target_ids is not None:
            return pid in target_ids
        if args.force:
            return True
        has_length = str(row.get("program_length_months", "")).strip() not in ("", "None")
        has_reliable_cost = str(row.get("cost_basis", "")).strip() in VALID_COST_BASIS
        data_yr = str(row.get("data_year", "")).strip()
        stale = is_stale(data_yr)
        if args.stale_only:
            return stale
        if args.landing_only:
            return row.get("validation_status", "") == "confirmed_landing"
        return (not has_length) or (not has_reliable_cost)

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
        outcomes_url = str(row.get("outcomes_url", "")).strip() or None
        extracted_from = str(row.get("extracted_from_url", "")).strip()
        data_yr = str(row.get("data_year", "")).strip()
        vstatus = str(row.get("validation_status", "")).strip()
        has_length = str(row.get("program_length_months", "")).strip() not in ("", "None")
        has_reliable_cost = str(row.get("cost_basis", "")).strip() in VALID_COST_BASIS
        stale = is_stale(data_yr)
        known_len = int(row.get("program_length_months", "") or 0) if has_length else None

        print(f"[{i+1}/{total}] {school_name}  stale={stale}  has_len={has_length}  reliable_cost={has_reliable_cost}")

        result, note, force_cost = _extract_for_row(
            client, args,
            school_name=school_name,
            apta_url=apta_url,
            fact_url=fact_url,
            outcomes_url=outcomes_url,
            extracted_from=extracted_from,
            vstatus=vstatus,
            stale=stale,
            known_len=known_len,
            has_reliable_cost=has_reliable_cost,
        )

        if result:
            if args.recalculate_cost:
                force_cost = True
            upsert_record(INPUT_FILE, build_update(program_id, result, note, data_yr, force_cost))
            oos_tag = ""
            if result.tuition_instate:
                oos_tag = f"  instate={result.tuition_instate}  oos={result.tuition_per_year}"
            elif result.tuition_per_year:
                oos_tag = f"  tpy={result.tuition_per_year}  oos={result.tuition_is_oos}"
            print(f"  => cost={result.total_program_cost}  len={result.program_length_months}mo  year={result.data_year}{oos_tag}")
            done += 1
        else:
            print(f"  => [NO DATA] {note}")
            skipped += 1

        if i < total - 1:
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print(f"\n{'='*60}")
    print(f"Done.  Extracted: {done}  Skipped/failed: {skipped}")


if __name__ == "__main__":
    main()
