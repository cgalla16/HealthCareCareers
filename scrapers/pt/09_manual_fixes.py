"""
09_manual_fixes.py — One-time targeted nulls for rows with confirmed bad data.

Run ONCE after the 2026-03-18 full re-extraction. Documents the reason for each fix.
Safe to re-run (idempotent — just sets the same fields to empty again).

DO NOT use this to re-null rows that have since been correctly re-extracted.
Each entry here should be evaluated before re-running.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from csv_store import upsert_batch

INPUT_FILE = "pt_programs.csv"

COST_FIELDS = [
    "total_program_cost", "tuition_per_year", "tuition_instate",
    "tuition_is_oos", "cost_basis", "cost_components",
    "data_year", "cost_source_url",
]

def null_cost(program_id: str, note: str, also_null_fact_sheet: bool = False) -> dict:
    d = {"program_id": program_id, **{f: "" for f in COST_FIELDS},
         "extraction_notes": f"AUDIT_CLEARED:{note}"}
    if also_null_fact_sheet:
        d["fact_sheet_url"] = ""
    return d

def null_total_only(program_id: str, note: str) -> dict:
    return {"program_id": program_id, "total_program_cost": "",
            "extraction_notes": f"AUDIT_CLEARED:{note}"}

def set_manual(program_id: str, note: str, **fields) -> dict:
    return {"program_id": program_id,
            "extraction_notes": f"MANUAL:{note}",
            **fields}


fixes = [
    # ── CAPTE template contamination ──────────────────────────────────────────
    # Source URL was capteonline.org (generic CAPTE template with placeholder
    # values, not school-specific data). Also null fact_sheet_url so re-extraction
    # cannot fall back to the same bad URL (these programs have no apta_program_url).
    null_cost("148", "capte_template", also_null_fact_sheet=True),   # Oakland University MI
    null_cost("200", "capte_template", also_null_fact_sheet=True),   # University of Jamestown ND
    null_cost("271", "capte_template", also_null_fact_sheet=True),   # St Augustine Austin TX

    # Wrong school domain: extracted from phhp.ufl.edu (University of Florida),
    # not St Augustine's own domain. Null fact_sheet_url to prevent re-use.
    null_cost("95", "wrong_school_domain_ufl", also_null_fact_sheet=True),  # St Augustine ONLINE FLEX FL

    # ── Wrong total (persistent LLM math error) ───────────────────────────────
    # Wingate: page states $13,600/sem × 9 semesters = $122,400 total.
    # LLM consistently computes $408,000 (multiplies by 30 instead of 9).
    # cost_components confirmed formula — set manually from known-correct data.
    set_manual("195", "13600_per_sem_x9",
               total_program_cost="122400",
               tuition_per_year="40800",      # $13,600/sem × 3 sem/yr
               tuition_is_oos="no",           # flat rate (private school)
               cost_basis="per_semester",
               cost_components="$13,600/sem x 9 semesters",
               data_year="2025-2026",
               cost_source_url="https://www.wingate.edu/academics/graduate/physical-therapy"),

    # Kean: $198,552 re-extracted consistently from subpages — may include
    # room+board. Cannot verify further without JS rendering. Leave nulled,
    # mark as needing manual review.
    null_cost("181", "unverifiable_inflated"),  # Kean University NJ

    # University of Washington: $278,004 total doesn't match $43,668/yr × 3yr = $131k.
    # Keep tuition_per_year ($43,668 OOS is plausible) — null total only.
    null_total_only("284", "math_broken_total"),   # University of Washington

    # Alabama State: source page (alasu.edu/financial-aid/tuition-costs.php) only
    # shows generic undergrad/grad rates — no DPT-specific pricing. Both old and
    # new values are wrong. Do NOT re-extract (no valid DPT source URL).
    null_cost("185", "no_dpt_data_on_page"),       # Alabama State University AL

    # ── Computed totals from known-correct cost_components ────────────────────
    # Kentucky: total was null (in-state/OOS mismatch). cost_components confirms:
    # "OOS: $47,595/yr + fees $1,574/yr + other $500/yr" → $49,669/yr × 3yr = $149,007.
    set_manual("135", "computed_from_cost_components",
               total_program_cost="149007",
               data_year="2023-2024"),              # University of Kentucky

    # University of Washington: total was null (math broken on prior extraction).
    # cost_components: "$9,269/qtr (WA) & $14,487/qtr (non-WA) x 11 qtrs"
    # OOS total: $14,487 × 11 = $159,357
    # OOS annual: $14,487/qtr × 4 qtrs/yr = $57,948/yr
    # In-state annual: $9,269/qtr × 4 = $37,076/yr
    set_manual("284", "computed_from_cost_components",
               total_program_cost="159357",
               tuition_per_year="57948",
               tuition_instate="37076"),            # University of Washington

    # ── Restored from snapshot (old source was more reliable) ────────────────
    # Brenau: new extraction ($180k/$60k) came from a generic tuition subpage
    # ("No cost data found on page" in notes). Old snapshot had $139,054/$40,240/yr
    # from a school-specific DPT fact sheet PDF (2023dptstudentfinancialfactsheet).
    # Restoring old values as more trustworthy source.
    set_manual("106", "restored_from_2023_fact_sheet",
               total_program_cost="139054",
               tuition_per_year="40240",
               tuition_is_oos="no",
               cost_basis="total",
               data_year="2023-2024"),               # Brenau University GA
]


def main():
    print(f"Applying {len(fixes)} targeted fixes to {INPUT_FILE}...")
    upsert_batch(INPUT_FILE, fixes)
    print("Done.")
    print("Do NOT re-extract: 95, 148, 200, 271 (fact_sheet_url cleared — no valid URL)")
    print("Do NOT re-extract: 185 (no DPT data), 195 (manually set), 181 (leave null)")
    print("Computed from cost_components: 135 (Kentucky $149,007), 284 (UW $159,357)")
    print("Restored from old snapshot:    106 (Brenau $139,054 from 2023 fact sheet)")


if __name__ == "__main__":
    main()
