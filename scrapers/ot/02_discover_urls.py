"""
02_discover_urls.py — Discover OT program URLs from the ACOTA accredited schools directory.

Auto-fetches all pages of https://acoteonline.org/schools/ by detecting the pagination URL
pattern from the first page, then uses Claude Haiku to extract program listings from each page.
Fuzzy-matches against our 271 MOT/OTD programs and stores results in:
  output/ot_program_urls.csv

Masters and Doctorate programs only. OTA (associate/certificate) programs are filtered out.

Usage:
  python 02_discover_urls.py                # process all pending programs
  python 02_discover_urls.py --limit 10     # test on first 10 pending
  python 02_discover_urls.py --force        # re-process already-matched rows
  python 02_discover_urls.py --retry-not-found  # retry url_not_found rows

If the directory is JavaScript-rendered (listings not in the HTML), the script will print
instructions to save pages manually as acota_directory_1.html, acota_directory_2.html, etc.
in this directory, then re-run. It reads all numbered files it finds automatically.
"""

import os
import re
import sys
import time
import random
import argparse
import difflib
from datetime import datetime, timezone
from typing import Optional, Literal
from urllib.parse import urlparse

import pandas as pd
import requests
import anthropic
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

sys.path.insert(0, os.path.dirname(__file__))
from csv_store import load_csv, upsert_batch

# --- Config ---
ACOTA_URL = "https://acoteonline.org/schools/"
INPUT_FILE = os.path.join(os.path.dirname(__file__), "input_financial.csv")
OUTPUT_FILE = "ot_program_urls.csv"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

MAX_HTML_CHARS = 60000   # ~15k tokens — enough for a full directory listing
MAX_PROFILE_CHARS = 20000

DELAY_MIN = 1.0
DELAY_MAX = 2.0

MATCH_HIGH = 0.85   # >= this: url_found (high confidence)
MATCH_LOW = 0.65    # >= this: url_found_low_confidence (flagged for review)

STOPWORDS = {
    "university", "college", "school", "institute", "the", "of", "and",
    "for", "at", "state", "health", "sciences", "science", "arts", "system",
}

OUTPUT_COLUMNS = [
    "program_id", "school_name", "city", "state", "degree_type",
    "acota_program_url", "acota_match_name", "acota_match_score",
    "url_status", "url_confidence", "discovery_notes", "last_updated",
]


# --- Pydantic schemas ---

class AcotaProgram(BaseModel):
    school_name: str
    degree_type: Literal["Masters", "Doctorate", "Associate", "Certificate", "Other"]
    program_url: Optional[str] = None        # external school OT program URL
    acota_profile_url: Optional[str] = None  # link to acoteonline.org profile page
    state: Optional[str] = None              # state if visible in listing


class AcotaListings(BaseModel):
    programs: list[AcotaProgram]


class ProfileExtraction(BaseModel):
    program_url: Optional[str] = None   # external school OT program URL
    notes: Optional[str] = None


# --- Helpers ---

def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for fuzzy matching."""
    name = name.lower()
    name = re.sub(r"[^\w\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def domain_check(school_name: str, url: str) -> Optional[str]:
    """
    Lightweight domain plausibility check. Returns 'DOMAIN_MISMATCH_WARN' if no
    non-stopword token from the school name appears anywhere in the URL domain.
    Returns None if the domain looks plausible.
    """
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return None

    tokens = [
        t for t in normalize_name(school_name).split()
        if len(t) > 3 and t not in STOPWORDS
    ]
    for token in tokens:
        if token in domain:
            return None  # at least one keyword matches
    return "DOMAIN_MISMATCH_WARN"


def best_match(
    our_name: str,
    our_state: str,
    our_degree: str,
    candidates: list[AcotaProgram],
) -> tuple[Optional[AcotaProgram], float]:
    """
    Find the best fuzzy match for our school against the ACOTA candidate list.
    Boosts score by +0.05 if state matches, +0.02 if degree type matches.
    Returns (best_candidate, score).
    """
    degree_map = {"MOT": "Masters", "OTD": "Doctorate"}
    our_acota_degree = degree_map.get(our_degree, "")
    norm_ours = normalize_name(our_name)

    best_candidate: Optional[AcotaProgram] = None
    best_score = 0.0

    for candidate in candidates:
        norm_theirs = normalize_name(candidate.school_name)
        score = difflib.SequenceMatcher(None, norm_ours, norm_theirs).ratio()

        # State match boost
        if candidate.state and our_state:
            cand_state = candidate.state.strip().upper()
            our_state_norm = our_state.strip().upper()
            if (
                cand_state == our_state_norm
                or our_state_norm in cand_state
                or cand_state in our_state_norm
            ):
                score = min(1.0, score + 0.05)

        # Same degree type boost (prefer MOT→Masters or OTD→Doctorate match)
        if candidate.degree_type == our_acota_degree:
            score = min(1.0, score + 0.02)

        if score > best_score:
            best_score = score
            best_candidate = candidate

    return best_candidate, best_score


# --- ACOTA page fetching ---

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

MANUAL_SAVE_INSTRUCTIONS = f"""
The ACOTA directory appears to be JavaScript-rendered — listings are not in the raw HTML.

To proceed, save each page manually:
  1. Open {ACOTA_URL} in Chrome or Edge
  2. Wait for school listings to load fully
  3. Press Ctrl+S -> "Webpage, HTML Only"
  4. Save as: acota_directory_1.html  (in this folder: {{}})
  5. Click to page 2, wait for it to load, save as: acota_directory_2.html
  6. Repeat through acota_directory_14.html
  7. Re-run this script

The script will automatically read all acota_directory_N.html files it finds.
"""


def fetch_with_retry(url: str, label: str = "") -> str:
    """Fetch a URL with up to 3 retries. Returns HTML or exits on total failure."""
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.RequestException as e:
            wait = 2 ** attempt
            tag = f" ({label})" if label else ""
            print(f"  Fetch attempt {attempt + 1}/3{tag} failed: {e}")
            if attempt < 2:
                time.sleep(wait)
    print(f"\nERROR: Could not fetch {url} after 3 attempts.")
    sys.exit(1)


def detect_pagination(html: str) -> Optional[str]:
    """
    Detect the pagination URL pattern from the first page's HTML.
    Returns a format string like 'https://acoteonline.org/schools/page/{n}/'
    or None if no pagination links are found.

    Checks for common WordPress patterns:
      /schools/page/2/
      /schools/?paged=2
      /schools/?page=2
    """
    # WordPress standard: /page/2/
    m = re.search(r'href=["\']([^"\']*schools/page/(\d+)/[^"\']*)["\']', html)
    if m:
        base = re.sub(r'/page/\d+/', '/page/{n}/', m.group(1))
        return base

    # Query string: ?paged=2 or ?page=2
    for param in ("paged", "page"):
        m = re.search(
            rf'href=["\']([^"\']*schools[^"\']*[?&]{param}=(\d+)[^"\']*)["\']', html
        )
        if m:
            base = re.sub(rf'([?&]{param}=)\d+', rf'\g<1>{{n}}', m.group(1))
            return base

    return None


def fetch_all_pages() -> list[str]:
    """
    Fetch all pages of the ACOTA schools directory.

    Strategy:
      1. Check for manually saved acota_directory_N.html files (user fallback)
      2. Otherwise fetch page 1, detect pagination pattern, fetch remaining pages

    Returns list of HTML strings.
    """
    # --- Check for manually saved pages first ---
    saved = sorted(
        [f for f in os.listdir(SCRIPT_DIR) if re.match(r"acota_directory_\d+\.html$", f)],
        key=lambda f: int(re.search(r"_(\d+)\.html$", f).group(1))
    )
    if not saved:
        single = os.path.join(SCRIPT_DIR, "acota_directory.html")
        if os.path.exists(single):
            saved = ["acota_directory.html"]

    if saved:
        pages = []
        print(f"Using {len(saved)} manually saved page(s):")
        for fname in saved:
            path = os.path.join(SCRIPT_DIR, fname)
            with open(path, encoding="utf-8", errors="replace") as f:
                html = f.read()
            pages.append(html)
            print(f"  {fname}  ({len(html):,} chars)")
        return pages

    # --- Auto-fetch: page 1 first ---
    print(f"Fetching {ACOTA_URL} ...")
    page1 = fetch_with_retry(ACOTA_URL, "page 1")
    print(f"  Page 1: {len(page1):,} chars")

    # --- Detect pagination ---
    pattern = detect_pagination(page1)
    if not pattern:
        print("  No pagination links detected — treating as single-page directory")
        return [page1]

    print(f"  Pagination pattern detected: {pattern.format(n='N')}")

    # Fetch pages 2..N until we get a duplicate or empty page
    pages = [page1]
    page_num = 2
    while True:
        url = pattern.format(n=page_num)
        print(f"  Fetching page {page_num}: {url}")
        html = fetch_with_retry(url, f"page {page_num}")

        # Stop if the page redirects back to page 1 (same content) or is tiny
        if len(html.strip()) < 500 or html.strip() == page1.strip():
            print(f"  Page {page_num} appears empty or duplicate — stopping")
            break

        pages.append(html)
        print(f"    {len(html):,} chars")
        page_num += 1
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print(f"  Fetched {len(pages)} page(s) total")
    return pages


# --- Claude extraction ---

def extract_listings(client: anthropic.Anthropic, html: str, page_label: str = "") -> list[AcotaProgram]:
    """Use Claude Haiku to extract structured program listings from one ACOTA directory page."""
    content = html[:MAX_HTML_CHARS]

    system = (
        "You are extracting structured data from an HTML page listing ACOTA-accredited "
        "occupational therapy programs. Extract EVERY program entry visible in the HTML. "
        "Do NOT invent entries that are not present.\n\n"
        "Degree type classification:\n"
        "- Masters: MOT, MSOT, OTM, or any Master of Occupational Therapy variant\n"
        "- Doctorate: OTD, Doctor of Occupational Therapy (entry-level or post-professional)\n"
        "- Associate: OTA, COTA, Occupational Therapy Assistant (2-year programs)\n"
        "- Certificate: certificate-level OT programs\n"
        "- Other: anything that doesn't fit the above\n\n"
        "URL rules:\n"
        "- program_url: the EXTERNAL school website URL (e.g. https://www.uab.edu/...)\n"
        "- acota_profile_url: any link pointing back to acoteonline.org\n"
        "- If no external URL is visible for a school, leave program_url null\n"
        "- If a school offers both MOT and OTD, emit two separate rows\n"
        "- Include state if it is visible in the listing"
    )
    user_msg = f"Extract all program listings from this ACOTA schools directory HTML:\n\n{content}"

    try:
        response = client.messages.parse(
            model="claude-haiku-4-5",
            max_tokens=8192,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            output_format=AcotaListings,
        )
        return response.parsed_output.programs
    except Exception as e:
        label = f" ({page_label})" if page_label else ""
        print(f"\nERROR: Claude failed to extract listings{label}: {e}")
        print("The page may be structured unexpectedly.")
        sys.exit(1)


def follow_profile_link(client: anthropic.Anthropic, profile_url: str) -> Optional[str]:
    """
    Fetch an ACOTA profile page and ask Claude to extract the school's external program URL.
    Returns the URL string or None if not found / fetch failed.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        resp = requests.get(profile_url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception:
        return None

    html = resp.text[:MAX_PROFILE_CHARS]
    try:
        response = client.messages.parse(
            model="claude-haiku-4-5",
            max_tokens=256,
            system=(
                "Extract the external OT program website URL from this ACOTA profile page. "
                "Return the school's own program website URL (not any acoteonline.org link). "
                "If no external URL is present, return null for program_url."
            ),
            messages=[{"role": "user", "content": html}],
            output_format=ProfileExtraction,
        )
        return response.parsed_output.program_url
    except Exception:
        return None


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="Discover OT program URLs from ACOTA accredited schools directory"
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="Process first N pending programs (for testing)")
    parser.add_argument("--force", action="store_true",
                        help="Re-process already-matched rows")
    parser.add_argument("--retry-not-found", action="store_true",
                        help="Retry only url_not_found rows")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        print("  Option 1: add ANTHROPIC_API_KEY=your_key to .env in this directory")
        print("  Option 2: export ANTHROPIC_API_KEY=your_key")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # --- Load our programs ---
    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: {INPUT_FILE} not found.")
        print("Run 01_load_programs.py first.")
        sys.exit(1)

    programs_df = pd.read_csv(INPUT_FILE, dtype=str, encoding="latin-1").fillna("")
    programs_df = programs_df[programs_df["degree_type"].isin(["MOT", "OTD"])]
    print(f"Loaded {len(programs_df)} MOT/OTD programs from input_financial.csv")

    # --- Initialize output CSV if needed ---
    existing = load_csv(OUTPUT_FILE)
    if existing.empty:
        init_records = []
        for _, row in programs_df.iterrows():
            init_records.append({
                "program_id": str(row["program_id"]),
                "school_name": row["school_name"],
                "city": row.get("city", ""),
                "state": row["state"],
                "degree_type": row["degree_type"],
                "url_status": "pending",
                "url_confidence": "",
                "acota_program_url": "",
                "acota_match_name": "",
                "acota_match_score": "",
                "discovery_notes": "",
                "last_updated": "",
            })
        upsert_batch(OUTPUT_FILE, init_records)
        existing = load_csv(OUTPUT_FILE)
        print(f"Initialized output/ot_program_urls.csv with {len(init_records)} pending rows")

    # --- Determine which programs to process ---
    done_statuses = {"url_found", "url_found_low_confidence", "url_not_found"}

    if args.force:
        to_process = programs_df
    elif args.retry_not_found:
        not_found_ids = set(
            existing[existing["url_status"] == "url_not_found"]["program_id"].tolist()
        )
        to_process = programs_df[programs_df["program_id"].astype(str).isin(not_found_ids)]
    else:
        done_ids = set(
            existing[existing["url_status"].isin(done_statuses)]["program_id"].tolist()
        )
        to_process = programs_df[~programs_df["program_id"].astype(str).isin(done_ids)]

    if args.limit:
        to_process = to_process.head(args.limit)

    if to_process.empty:
        print("Nothing to process. All programs already matched.")
        print("Use --force to re-match, or --retry-not-found to retry unmatched schools.")
        return

    print(f"Programs to process: {len(to_process)}")

    # --- Fetch all ACOTA directory pages ---
    print()
    pages = fetch_all_pages()

    # --- Claude extracts listings from each page ---
    print(f"\nExtracting listings from {len(pages)} page(s) with Claude Haiku...")
    all_listings: list[AcotaProgram] = []
    for i, html in enumerate(pages):
        label = f"page {i + 1}/{len(pages)}"
        page_listings = extract_listings(client, html, label)
        grad_on_page = [p for p in page_listings if p.degree_type in ("Masters", "Doctorate")]
        print(f"  {label}: {len(page_listings)} total, {len(grad_on_page)} graduate")
        all_listings.extend(page_listings)

    grad_listings = [p for p in all_listings if p.degree_type in ("Masters", "Doctorate")]
    ota_count = sum(1 for p in all_listings if p.degree_type in ("Associate", "Certificate"))

    print(f"\nAll pages combined:")
    print(f"  Total listings: {len(all_listings)}")
    print(f"  Graduate (MOT/OTD): {len(grad_listings)}   |   OTA filtered out: {ota_count}")

    if not grad_listings:
        print("\nERROR: No graduate program listings found across any page.")
        print("The directory may be JavaScript-rendered (listings loaded after page load).")
        print(MANUAL_SAVE_INSTRUCTIONS.format(SCRIPT_DIR))
        sys.exit(1)

    if len(grad_listings) < 50:
        print(f"\nWARNING: Only {len(grad_listings)} graduate listings found — expected ~271+.")
        print("Some pages may have loaded without content (JS-rendered).")
        print(MANUAL_SAVE_INSTRUCTIONS.format(SCRIPT_DIR))
        print("Continuing with what was found...\n")

    # --- Follow ACOTA profile links for any missing external URLs ---
    needs_profile = [
        p for p in grad_listings if not p.program_url and p.acota_profile_url
    ]
    if needs_profile:
        print(f"\nFollowing {len(needs_profile)} ACOTA profile links to find external URLs...")
        for i, listing in enumerate(needs_profile):
            print(f"  [{i + 1}/{len(needs_profile)}] {listing.school_name}")
            external_url = follow_profile_link(client, listing.acota_profile_url)
            if external_url:
                listing.program_url = external_url
                print(f"    Found: {external_url[:70]}")
            else:
                print(f"    [X] No external URL found on profile page")
            if i < len(needs_profile) - 1:
                time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    # --- Match our programs against ACOTA listings ---
    print(f"\nMatching {len(to_process)} programs against {len(grad_listings)} ACOTA listings...")
    print("-" * 60)

    records = []
    found_high = found_low = not_found = 0

    for _, row in to_process.iterrows():
        program_id = str(row["program_id"])
        school_name = row["school_name"]
        state = row["state"]
        degree_type = row["degree_type"]

        match, score = best_match(school_name, state, degree_type, grad_listings)

        notes = ""
        acota_url = ""
        acota_name = match.school_name if match else ""

        if match and score >= MATCH_HIGH:
            url_status = "url_found"
            url_confidence = "high"
            acota_url = match.program_url or ""
            found_high += 1
            icon = "[OK]"
        elif match and score >= MATCH_LOW:
            url_status = "url_found_low_confidence"
            url_confidence = "low"
            acota_url = match.program_url or ""
            found_low += 1
            icon = "[~]"
        else:
            url_status = "url_not_found"
            url_confidence = ""
            not_found += 1
            icon = "[X]"

        # Domain plausibility check
        if acota_url:
            warn = domain_check(school_name, acota_url)
            if warn:
                notes = warn

        # Matched but no URL available in ACOTA
        if url_status in ("url_found", "url_found_low_confidence") and not acota_url:
            notes = (notes + "; NO_URL_IN_ACOTA").lstrip("; ")
            url_status = "url_not_found"
            url_confidence = ""
            not_found += 1
            found_high -= 1 if icon == "[OK]" else 0
            found_low -= 1 if icon == "[~]" else 0
            icon = "[X]"

        print(f"  {icon} [{score:.2f}] {school_name} ({degree_type})")
        if acota_name and acota_name.lower() != school_name.lower():
            print(f"        ACOTA name: {acota_name}")
        if acota_url:
            print(f"        URL: {acota_url[:70]}")
        if notes:
            print(f"        NOTE: {notes}")

        records.append({
            "program_id": program_id,
            "acota_program_url": acota_url,
            "acota_match_name": acota_name,
            "acota_match_score": f"{score:.4f}",
            "url_status": url_status,
            "url_confidence": url_confidence,
            "discovery_notes": notes,
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    upsert_batch(OUTPUT_FILE, records)

    print("-" * 60)
    print(f"\nDone. Results written to output/{OUTPUT_FILE}")
    print(f"  High confidence (url_found):          {found_high}")
    print(f"  Low confidence (url_found_low):        {found_low}")
    print(f"  Not found:                             {not_found}")

    if found_low + not_found > 0:
        print(f"\n{found_low + not_found} programs need attention:")
        print("  - Run python 03_export_review.py to export them for manual review")
        print("  - Fill in manual_url in the review CSV, set url_status=manual_override")
        print("  - Run python 04_apply_manual.py to apply the corrections")

    if not_found > 0:
        print(f"\nFor url_not_found rows after manual fixes, re-run with:")
        print("  python 02_discover_urls.py --retry-not-found")


if __name__ == "__main__":
    main()
