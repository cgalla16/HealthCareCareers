"""
07_audit_clean.py — Null known-bad data identified in post-run audit (~60 rows).

WARNING: This script replays ALL CLEANUPS entries every run. Do NOT re-run after rows have
been successfully re-extracted — it will re-null them and trigger a 130+ row reprocessing cycle.
For new one-off nulls, use a targeted inline Python command instead (see Groups R/S comments).

Root causes found:
  1. Wrong-school fact_sheet_url — Serper matched wrong institution's PDF.
     Popular PDFs (UNLV, Idaho State, U Montana, U Mary) were returned as top
     Google results for dozens of unrelated DPT searches.
  2. Residency/fellowship PDF used instead of DPT program fact sheet.
  3. Calculation errors (Claude summed in-state + out-of-state rates together).

Note: rows where cost was extracted from the correct APTA URL (not the bad fact_sheet)
have null_cost=False — only the bad fact_sheet_url is cleared for those.

Run once, then re-run 06_extract_data.py to re-extract via APTA URLs.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from csv_store import load_csv, save_csv

INPUT_FILE = "pt_programs.csv"

COST_FIELDS = [
    "total_program_cost", "tuition_per_year", "fees_per_year",
    "cost_basis", "cost_components", "extraction_notes", "data_year",
]
LENGTH_FIELD = "program_length_months"

# (program_id, null_cost, null_length, clear_fact_sheet_url, reason)
CLEANUPS = [
    # Group A: ISU URL used for wrong schools
    (3,   True,  False, True,  "fact_sheet is Idaho State University, not Shenandoah"),
    (21,  True,  False, True,  "fact_sheet is Idaho State University, not SUNY Upstate"),
    (78,  True,  False, True,  "fact_sheet is Idaho State University, not U Connecticut"),
    (117, True,  False, True,  "fact_sheet is Idaho State University, not Governors State"),
    (278, True,  False, True,  "fact_sheet is Idaho State University, not U Utah"),
    # Group B: UMT (U Montana) URL used for wrong schools
    (43,  True,  False, True,  "fact_sheet is Univ of Montana, not Tufts"),
    (81,  True,  False, True,  "fact_sheet is Univ of Montana, not U Delaware"),
    (91,  True,  False, True,  "fact_sheet is Univ of Montana, not UST Augustine FL"),
    (103, True,  False, True,  "fact_sheet is Univ of Montana, not U North Georgia"),
    (158, False, False, True,  "fact_sheet is UMT but cost extracted from stkate.edu (correct); keep cost"),
    (182, True,  False, True,  "fact_sheet is Univ of Montana, not U New Mexico"),
    (222, True,  False, True,  "fact_sheet is Univ of Montana, not Drexel"),
    (249, True,  False, True,  "fact_sheet is Univ of Montana, not U South Dakota"),
    (257, True,  False, True,  "fact_sheet is Univ of Montana, not Lincoln Memorial"),
    # Group C: U Mary ND URL used for wrong schools
    (134, True,  False, True,  "fact_sheet is Univ of Mary ND, not U Saint Mary KS"),
    (144, True,  False, True,  "fact_sheet is Univ of Mary ND, not U Maryland Baltimore"),
    (145, True,  False, True,  "fact_sheet is Univ of Mary ND, not U Maryland Eastern Shore"),
    # Group D: BU URL used for wrong schools
    (34,  True,  False, True,  "fact_sheet is Boston University, not Marist College"),
    (155, True,  False, True,  "fact_sheet is Boston University, not St Scholastica"),
    # Group E: UNLV 2023 URL used for wrong schools
    (1,   True,  False, True,  "fact_sheet is UNLV, not Old Dominion"),
    (9,   True,  False, True,  "fact_sheet is UNLV, not Mary Baldwin"),
    (126, True,  False, True,  "fact_sheet is UNLV, not U Iowa"),
    (164, True,  False, True,  "fact_sheet is UNLV, not Saint Louis University"),
    (218, False, False, True,  "fact_sheet is UNLV but cost from georgefox.edu (correct); keep cost"),
    (239, False, False, True,  "fact_sheet is UNLV but cost from messiah.edu (correct); keep cost"),
    (273, False, False, True,  "fact_sheet is UNLV; cost from APTA sub-page; no reliable cost anyway"),
    (281, False, False, True,  "fact_sheet is UNLV but extracted from uvm.edu (correct); no reliable cost"),
    # Group F: UNLV 2022 URL used for wrong schools
    (197, True,  False, True,  "fact_sheet is UNLV 2022, not Methodist University"),
    (227, True,  False, True,  "fact_sheet is UNLV 2022, not U Scranton"),
    # Group G: UIIndy URL used for wrong school
    (208, True,  False, True,  "fact_sheet is U Indianapolis, not Mt St Joseph"),
    # Group H: Other wrong-school or wrong-campus URLs
    (15,  True,  False, True,  "fact_sheet is Andrews University, not LIU Brooklyn"),
    (22,  True,  True,  True,  "fact_sheet is Touro Nevada, not Touro NY; length 11mo wrong"),
    (26,  True,  False, True,  "fact_sheet is NYIT (nyit.edu), not NY Medical College"),
    (32,  True,  True,  True,  "fact_sheet is Touro Nevada; length 49mo wrong"),
    (65,  True,  False, True,  "fact_sheet is West Coast University, not USC"),
    (82,  True,  True,  True,  "fact_sheet is Howard Community College PTA, not Howard Univ DPT"),
    (88,  True,  False, True,  "fact_sheet is UNC Chapel Hill, not U North Florida"),
    (92,  True,  False, True,  "fact_sheet is Univ of Florida (phhp.ufl.edu), not FGCU"),
    (119, True,  False, True,  "fact_sheet is Indiana State Univ, not Indiana University"),
    (133, True,  False, True,  "fact_sheet is Franklin Pierce Univ, not Wichita State"),
    (163, True,  False, True,  "fact_sheet is LSUHSC, not Rockhurst University"),
    (176, True,  False, True,  "fact_sheet is FPU AZ campus, not FPU NH campus"),
    (236, True,  False, True,  "fact_sheet is Bellin College WI, not Lebanon Valley PA"),
    (245, True,  False, True,  "fact_sheet is UNC Chapel Hill, not MUSC"),
    (258, True,  False, True,  "fact_sheet is Texas Tech HSC, not Texas State University"),
    (261, True,  False, True,  "fact_sheet is Texas Tech HSC, not UT Health SA"),
    (287, True,  True,  True,  "fact_sheet is Virginia Western CC PTA, not WVU DPT"),
    (290, True,  False, True,  "fact_sheet is UW Madison, not Concordia WI Expansion"),
    # Group I: Residency/fellowship PDF used instead of DPT
    (211, True,  False, True,  "fact_sheet is sports PT residency fees, not DPT tuition"),
    (284, True,  False, False, "cost=$334,884 wrong: Claude summed WA+OOS rates together"),
    # Group J: Calculation errors
    (105, True,  False, False, "cost=$419,022 impossible calculation error"),
    (289, True,  False, False, "cost=$113,583 overcounted; year components sum to ~$72k"),
    # Group K: Length anomalies only
    (44,  False, True,  False, "length=24mo wrong; NAU DPT ~30mo; only Y1+Y2 data captured"),
    (229, False, True,  False, "length=66mo wrong from APTA page; standard DPT is 30-33mo"),
    (275, False, True,  False, "length=21mo wrong; Army-Baylor sheet only has 2yr data"),
    # Group L: Fees-only / single-year mislabeled as total
    (36,  True,  False, False, "cost=$1,130 is admin fees only, not DPT tuition"),
    (101, True,  False, False, "cost=$19,005 is single academic year, not full program total"),
    # Group M: Wrong source document (residency/fellowship sheets used for DPT)
    (191, True,  False, False, "cost=$633 from neuro-residency fact sheet, not DPT tuition"),
    # Group N: Length anomaly confirmed post-audit
    (25,  False, True,  False, "length=12mo impossible for DPT; cost already null"),
    # Group O: LLM grabbed wrong sub-page (grad fees page vs DPT fact sheet)
    # True FPTA form values: Yr1=$39,480 Yr2=$37,260 Yr3=$33,200 Total=$109,940
    (129, True,  False, False, "cost=$102k wrong; LLM used grad-fees page not FPTA form; re-extract after prompt hardening"),
    # Group P: Residency/fellowship programs mistakenly extracted (spot-check 2026-03-16)
    (128, True,  False, True,  "St Ambrose: residency/fellowship fact sheet, not DPT; malformed APTA URL"),
    (141, True,  False, True,  "Franciscan U LA: SLU pt-residency fact sheet extracted, not DPT"),
    (162, True,  False, True,  "Maryville U MO: pt-residency fact sheet, not DPT"),
    (172, True,  False, True,  "Creighton NE: geriatric residency (Geri-Res) fact sheet, not DPT"),
    (202, True,  False, True,  "U Toledo OH: sports PT residency fact sheet, not DPT"),
    (264, True,  False, True,  "UT Southwestern TX: neuro PT residency fact sheet, not DPT"),
    (272, True,  False, True,  "UTMB Galveston TX: neuro PT residency fact sheet, not DPT"),
    (276, True,  False, True,  "UT Southwestern variant: neuro PT residency, not DPT"),
    (277, True,  False, True,  "UT Southwestern variant: neuro PT residency, not DPT"),
    (297, True,  True,  True,  "Carroll WI: residency financial fact sheet, not DPT; wrong length too"),
    # Group Q: Length anomaly confirmed via spot-check 2026-03-16
    (187, False, True,  False, "Faulkner AL: 28mo wrong; website shows 8 semesters (~48mo DPT)"),
    # Group R: x12 multiplication bug (2026-03-17) — nulled via targeted one-off command, not here.
    # Re-running this script would re-null 39 rows that were already successfully re-extracted.
    # Use the inline null command from the plan instead.
    # (106, True, False, False, "Brenau GA: total=$180k = tuition x12, not x3yr"),
    # (129, True, False, False, "Clarke IA: total=$306k = tuition x12; known actual=$109,940 from FPTA PDF"),
    # (211, True, False, False, "U Dayton OH: total=$479k = tuition x12, not x3yr"),
    # (231, True, False, False, "Misericordia PA: total=$207k = tuition x12; components show $146k"),
    # (181, True, False, False, "Kean NJ: total=$396k implausible; re-extract"),
    # Group S: Residual bad values (2026-03-17) — same note, use targeted null command
    # (25,  True, False, False, "Mercy NY: $550 total re-extracted from residency page"),
    # (264, False, True, False, "UT Southwestern TX: length=31mo from HEERF page, not program page"),
]


def main():
    df = load_csv(INPUT_FILE)
    if df.empty:
        print(f"ERROR: output/{INPUT_FILE} not found.")
        return

    nulled = 0
    for (pid, null_cost, null_length, clear_fact, reason) in CLEANUPS:
        mask = df["program_id"].astype(str) == str(pid)
        if not mask.any():
            print(f"  WARNING: program_id {pid} not found — skipping")
            continue

        school = df.loc[mask, "school_name"].values[0]

        if null_cost:
            for f in COST_FIELDS:
                if f in df.columns:
                    df.loc[mask, f] = ""

        if null_length and LENGTH_FIELD in df.columns:
            df.loc[mask, LENGTH_FIELD] = ""

        if clear_fact and "fact_sheet_url" in df.columns:
            df.loc[mask, "fact_sheet_url"] = ""

        df.loc[mask, "extraction_notes"] = f"AUDIT_CLEARED: {reason}"
        nulled += 1

        tags = []
        if null_cost:
            tags.append("cost")
        if null_length:
            tags.append("length")
        if clear_fact:
            tags.append("fact_sheet_url")
        print(f"  [{pid}] {school}  nulled: {', '.join(tags)}")

    save_csv(df, INPUT_FILE)
    print(f"\nDone. Cleaned {nulled} rows.")
    print("Next step: python 06_extract_data.py")


if __name__ == "__main__":
    main()
