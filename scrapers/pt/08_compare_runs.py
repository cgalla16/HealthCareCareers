"""
08_compare_runs.py — Compare two pt_programs.csv snapshots after a full re-run.

Usage:
    python 08_compare_runs.py --old output/pt_programs_snapshot_20260318.csv
    python 08_compare_runs.py --old output/pt_programs_snapshot_20260318.csv --new output/pt_programs.csv

Outputs:
    output/comparison_report.csv   — flagged rows with before/after values
    stdout                         — summary counts
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

OUTPUT_DIR = Path(__file__).parent / "output"
DEFAULT_NEW = OUTPUT_DIR / "pt_programs.csv"
DEFAULT_OUT = OUTPUT_DIR / "comparison_report.csv"

COST_THRESHOLD = 0.05   # 5% change → flag
TUITION_THRESHOLD = 0.05


def _pct_change(old_val, new_val) -> float | None:
    """Return absolute fractional change, or None if comparison is not meaningful."""
    try:
        old = float(old_val)
        new = float(new_val)
    except (TypeError, ValueError):
        return None
    if old == 0:
        return None
    return abs(new - old) / old


def _to_float(val) -> float | None:
    try:
        v = float(val)
        return v if not pd.isna(v) else None
    except (TypeError, ValueError):
        return None


def _to_int(val) -> int | None:
    try:
        v = int(float(val))
        return v
    except (TypeError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser(description="Compare two pt_programs.csv snapshots")
    parser.add_argument("--old", required=True, help="Path to the old/snapshot CSV")
    parser.add_argument("--new", default=str(DEFAULT_NEW), help="Path to the new CSV (default: output/pt_programs.csv)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output report CSV path")
    args = parser.parse_args()

    old_path = Path(args.old)
    new_path = Path(args.new)

    if not old_path.exists():
        print(f"ERROR: --old file not found: {old_path}", file=sys.stderr)
        sys.exit(1)
    if not new_path.exists():
        print(f"ERROR: --new file not found: {new_path}", file=sys.stderr)
        sys.exit(1)

    old_df = pd.read_csv(old_path, dtype=str).set_index("program_id")
    new_df = pd.read_csv(new_path, dtype=str).set_index("program_id")

    all_ids = old_df.index.union(new_df.index)
    rows = []

    for pid in all_ids:
        old_row = old_df.loc[pid] if pid in old_df.index else None
        new_row = new_df.loc[pid] if pid in new_df.index else None

        if old_row is None or new_row is None:
            continue  # program added/removed entirely — skip

        school = new_row.get("school_name", "")
        state  = new_row.get("state", "")
        src_url = new_row.get("cost_source_url", "")

        old_cost   = _to_float(old_row.get("total_program_cost"))
        new_cost   = _to_float(new_row.get("total_program_cost"))
        old_tpy    = _to_float(old_row.get("tuition_per_year"))
        new_tpy    = _to_float(new_row.get("tuition_per_year"))
        old_len    = _to_int(old_row.get("program_length_months"))
        new_len    = _to_int(new_row.get("program_length_months"))

        change_types = []
        notes_parts  = []

        # Newly populated (was null, now has value)
        if old_cost is None and new_cost is not None:
            change_types.append("newly_populated_cost")
        if old_tpy is None and new_tpy is not None:
            change_types.append("newly_populated_tuition")
        if old_len is None and new_len is not None:
            change_types.append("newly_populated_length")

        # Newly nulled (had value, now null) — investigate
        if old_cost is not None and new_cost is None:
            change_types.append("newly_nulled_cost")
            notes_parts.append(f"cost was {old_cost}")
        if old_tpy is not None and new_tpy is None:
            change_types.append("newly_nulled_tuition")
            notes_parts.append(f"tuition was {old_tpy}")
        if old_len is not None and new_len is None:
            change_types.append("newly_nulled_length")
            notes_parts.append(f"length was {old_len}")

        # Value changed
        cost_pct = _pct_change(old_cost, new_cost)
        if cost_pct is not None and cost_pct > COST_THRESHOLD:
            change_types.append("cost_changed")
            notes_parts.append(f"cost {old_cost:.0f}→{new_cost:.0f} ({cost_pct*100:.1f}%)")

        tpy_pct = _pct_change(old_tpy, new_tpy)
        if tpy_pct is not None and tpy_pct > TUITION_THRESHOLD:
            change_types.append("tuition_changed")
            notes_parts.append(f"tuition {old_tpy:.0f}→{new_tpy:.0f} ({tpy_pct*100:.1f}%)")

        if old_len is not None and new_len is not None and old_len != new_len:
            change_types.append("length_changed")
            notes_parts.append(f"length {old_len}→{new_len}")

        if not change_types:
            continue  # no change — skip

        rows.append({
            "program_id":           pid,
            "school_name":          school,
            "state":                state,
            "cost_source_url":      src_url,
            "old_total_cost":       old_cost,
            "new_total_cost":       new_cost,
            "cost_pct_change":      f"{cost_pct*100:.1f}%" if cost_pct is not None else "",
            "old_tuition_per_year": old_tpy,
            "new_tuition_per_year": new_tpy,
            "tuition_pct_change":   f"{tpy_pct*100:.1f}%" if tpy_pct is not None else "",
            "old_length_months":    old_len,
            "new_length_months":    new_len,
            "change_type":          "|".join(change_types),
            "notes":                "; ".join(notes_parts),
        })

    report_df = pd.DataFrame(rows)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_df.to_csv(out_path, index=False)

    # ── summary ───────────────────────────────────────────────────────────────
    total = len(all_ids)
    old_cost_count = old_df["total_program_cost"].apply(_to_float).notna().sum()
    new_cost_count = new_df["total_program_cost"].apply(_to_float).notna().sum()
    old_len_count  = old_df["program_length_months"].apply(_to_int).notna().sum()
    new_len_count  = new_df["program_length_months"].apply(_to_int).notna().sum()

    def count_type(t):
        return report_df["change_type"].str.contains(t).sum() if len(report_df) else 0

    print(f"\n{'='*60}")
    print(f"Comparison: {old_path.name}  →  {new_path.name}")
    print(f"{'='*60}")
    print(f"Total programs compared : {total}")
    print(f"Coverage (total cost)   : {old_cost_count} → {new_cost_count}  ({new_cost_count-old_cost_count:+d})")
    print(f"Coverage (length)       : {old_len_count} → {new_len_count}  ({new_len_count-old_len_count:+d})")
    print(f"")
    print(f"Newly populated (cost)  : +{count_type('newly_populated_cost')}")
    print(f"Newly populated (length): +{count_type('newly_populated_length')}")
    print(f"Cost changed (>5%)      : {count_type('cost_changed')}")
    print(f"Tuition changed (>5%)   : {count_type('tuition_changed')}")
    print(f"Length changed          : {count_type('length_changed')}")
    print(f"Newly nulled (cost)     : {count_type('newly_nulled_cost')}  ← investigate")
    print(f"Newly nulled (length)   : {count_type('newly_nulled_length')}  ← investigate")
    print(f"")
    print(f"Report written to: {out_path}")

    if count_type("newly_nulled_cost") > 0 or count_type("newly_nulled_length") > 0:
        nulled = report_df[report_df["change_type"].str.contains("newly_nulled")]
        print(f"\nNEEDS INVESTIGATION — newly nulled rows:")
        for _, r in nulled.iterrows():
            print(f"  [{r['program_id']}] {r['school_name']} ({r['state']}) — {r['notes']}")


if __name__ == "__main__":
    main()
