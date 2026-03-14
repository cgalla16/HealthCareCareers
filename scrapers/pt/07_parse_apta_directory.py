"""
07_parse_apta_directory.py — Harvest PT program URLs from the APTA accredited schools directory.

Fetches https://aptaapps.apta.org/accreditedschoolsdirectory/AllPrograms.aspx in a single request
(server-rendered, no JavaScript needed), extracts all DPT program entries, and matches them against
pt_programs.csv.

Outputs:
  url_map.csv             — raw APTA harvest (~300 DPT rows) with match results
  url_map_unmatched.csv   — APTA rows that couldn't be matched to a program in pt_programs.csv
  output/pt_programs.csv  — updated: apta_program_url + outcomes_url always set;
                            program_url + validation_status updated conditionally

Match actions recorded in url_map.csv (match_action column):
  url_added      — program_url was missing; filled with APTA URL
  url_replaced   — validation_status was rejected/fetch_failed; APTA URL substituted, reset to pending
  skipped_valid  — existing valid URL kept; APTA URL stored in apta_program_url for reference
  no_match       — no match found in pt_programs.csv (check url_map_unmatched.csv)

Usage:
  python 07_parse_apta_directory.py
"""

import os
import re
import csv
import sys
import difflib
import requests

sys.path.insert(0, os.path.dirname(__file__))
from csv_store import load_csv, upsert_batch

APTA_URL = "https://aptaapps.apta.org/accreditedschoolsdirectory/AllPrograms.aspx"
OUTPUT_FILE = "pt_programs.csv"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
URL_MAP_FILE = os.path.join(SCRIPT_DIR, "url_map.csv")
UNMATCHED_FILE = os.path.join(SCRIPT_DIR, "url_map_unmatched.csv")

DPT_KEYWORDS = ["doctor of physical therapy", "dpt", "doctor in physical therapy"]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PT-Program-Harvester/1.0)"}


# ---------- Parsing ----------

def fetch_page():
    print(f"Fetching APTA directory...")
    r = requests.get(APTA_URL, timeout=30, headers=HEADERS)
    r.raise_for_status()
    print(f"  {len(r.text):,} bytes received")
    return r.text


def is_dpt(degree_text):
    d = degree_text.lower()
    return any(kw in d for kw in DPT_KEYWORDS)


def parse_address(leftcol_div):
    """Extract city and state from the address block (looks for 'City, ST ZIPCODE' pattern)."""
    text = leftcol_div.get_text(separator="\n")
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r'^([^,\d][^,]+),\s+([A-Z]{2})\b', line)
        if m:
            return m.group(1).strip(), m.group(2).strip()
    return "", ""


def extract_link_by_text(rightcol_div, link_text):
    """Find an <a target="_blank"> by its visible text within the rightcol block."""
    for a in rightcol_div.find_all("a", target="_blank"):
        if a.get_text(strip=True).lower() == link_text.lower():
            href = a.get("href", "").strip()
            return href if href and not href.startswith("#") else ""
    return ""


def extract_degree(rightcol_div):
    """Extract degree type from 'Degree Conferred: ...' text."""
    text = rightcol_div.get_text(separator="\n")
    m = re.search(r'Degree Conferred:\s*(.+)', text)
    return m.group(1).strip() if m else ""


def parse_programs(html):
    """Return list of dicts for all DPT programs on the page."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    programs = []

    for row in soup.find_all("div", class_="row"):
        name_span = row.find("span", style=lambda s: s and "font-weight:bold" in s)
        if not name_span:
            continue
        school_name = name_span.get_text(strip=True)
        if not school_name:
            continue

        leftcol = row.find("div", class_=lambda c: c and "leftcol" in c)
        rightcol = row.find("div", class_=lambda c: c and "rightcol" in c)
        if not leftcol or not rightcol:
            continue

        degree = extract_degree(rightcol)
        if not is_dpt(degree):
            continue

        city, state = parse_address(leftcol)
        program_url = extract_link_by_text(rightcol, "Website")
        outcomes_url = extract_link_by_text(rightcol, "Outcomes")

        programs.append({
            "school_name": school_name,
            "city": city,
            "state": state,
            "degree_type": degree,
            "program_url": program_url,
            "outcomes_url": outcomes_url,
        })

    return programs


# ---------- Matching ----------

def normalize(name):
    """Normalize a school name for fuzzy comparison."""
    # Remove parenthetical suffixes like "(Expansion 2)", "(Satellite)"
    n = re.sub(r'\s*\(.*?\)', '', name)
    # Remove trailing " - " (leftover after stripping parentheticals)
    n = re.sub(r'\s*-\s*$', '', n)
    n = n.lower().strip()
    # Remove non-word characters (punctuation, apostrophes, etc.)
    n = re.sub(r"[^\w\s]", " ", n)
    # Collapse whitespace
    return re.sub(r'\s+', ' ', n).strip()


def best_match(apta_name, apta_state, candidates):
    """
    candidates: list of (program_id, school_name, state)
    Returns (program_id, score) — (None, score) if below threshold.
    """
    norm_apta = normalize(apta_name)
    best_id, best_score = None, 0.0

    for pid, pname, pstate in candidates:
        norm_p = normalize(pname)
        score = difflib.SequenceMatcher(None, norm_apta, norm_p).ratio()
        # Small boost when states match (helps resolve same-name schools in different states)
        if pstate.strip().upper() == apta_state.strip().upper():
            score = min(1.0, score + 0.05)
        if score > best_score:
            best_score = score
            best_id = pid

    return (best_id, best_score) if best_score >= 0.85 else (None, best_score)


# ---------- Main ----------

def main():
    html = fetch_page()

    programs = parse_programs(html)
    print(f"Found {len(programs)} DPT programs in APTA directory")

    df = load_csv(OUTPUT_FILE)
    if df.empty:
        print("ERROR: output/pt_programs.csv not found. Run 01_load_programs.py first.")
        sys.exit(1)

    candidates = list(zip(
        df["program_id"].tolist(),
        df["school_name"].tolist(),
        df["state"].tolist(),
    ))

    # Ensure new columns exist in the dataframe before upsert
    for col in ("apta_program_url", "outcomes_url"):
        if col not in df.columns:
            df[col] = ""

    url_map_rows = []
    updates = []
    unmatched = []

    for p in programs:
        pid, score = best_match(p["school_name"], p["state"], candidates)

        row_entry = {**p, "matched_program_id": pid or "", "match_score": f"{score:.3f}", "match_action": ""}

        if pid is None:
            row_entry["match_action"] = "no_match"
            url_map_rows.append(row_entry)
            unmatched.append(p)
            continue

        existing = df[df["program_id"].astype(str) == str(pid)].iloc[0]
        existing_url = str(existing.get("program_url", "")).strip()
        existing_validation = str(existing.get("validation_status", "")).strip()

        update = {
            "program_id": str(pid),
            "apta_program_url": p["program_url"],
            "outcomes_url": p["outcomes_url"],
        }

        if not existing_url:
            update["program_url"] = p["program_url"]
            row_entry["match_action"] = "url_added"
        elif existing_validation in ("rejected", "fetch_failed"):
            update["program_url"] = p["program_url"]
            update["validation_status"] = ""
            row_entry["match_action"] = "url_replaced"
        else:
            row_entry["match_action"] = "skipped_valid"

        url_map_rows.append(row_entry)
        updates.append(update)

    # Write url_map.csv
    if url_map_rows:
        fieldnames = ["school_name", "city", "state", "degree_type", "program_url",
                      "outcomes_url", "matched_program_id", "match_score", "match_action"]
        with open(URL_MAP_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(url_map_rows)
        print(f"Wrote {len(url_map_rows)} rows to url_map.csv")

    # Write url_map_unmatched.csv
    if unmatched:
        fieldnames = ["school_name", "city", "state", "degree_type", "program_url", "outcomes_url"]
        with open(UNMATCHED_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(unmatched)
        print(f"WARNING: {len(unmatched)} APTA programs could not be matched — see url_map_unmatched.csv")
    else:
        print("All APTA programs matched successfully.")

    # Apply updates to pt_programs.csv
    if updates:
        upsert_batch(OUTPUT_FILE, updates)
        print(f"Updated {len(updates)} rows in output/pt_programs.csv")

    # Print summary
    actions: dict[str, int] = {}
    for r in url_map_rows:
        a = r["match_action"]
        actions[a] = actions.get(a, 0) + 1

    print("\nSummary:")
    for action, count in sorted(actions.items()):
        print(f"  {action:20s}: {count}")


if __name__ == "__main__":
    main()
