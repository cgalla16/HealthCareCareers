"""
csv_store.py — Atomic CSV read/write with upsert support.
All writes go to .tmp then rename to prevent corruption on crash.
"""

import os
import csv
import shutil
import tempfile
import pandas as pd
from typing import Optional

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_path(filename: str) -> str:
    return os.path.join(OUTPUT_DIR, filename)


def load_csv(filename: str) -> pd.DataFrame:
    path = get_path(filename)
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def save_csv(df: pd.DataFrame, filename: str):
    """Atomic write: write to .tmp then rename."""
    ensure_output_dir()
    path = get_path(filename)
    tmp_path = path + ".tmp"
    df.to_csv(tmp_path, index=False)
    shutil.move(tmp_path, path)


def upsert_record(filename: str, record: dict, key_col: str = "program_id"):
    """
    Update a single record in the CSV by key_col.
    Only updates fields present in `record` — preserves all other fields.
    Safe to call repeatedly; creates file if it doesn't exist.
    """
    ensure_output_dir()
    df = load_csv(filename)

    key_val = str(record[key_col])

    if df.empty or key_col not in df.columns:
        # Brand new file — just create it with this record
        df = pd.DataFrame([record])
        save_csv(df, filename)
        return

    # Add any new columns from record that don't exist yet
    for col in record:
        if col not in df.columns:
            df[col] = ""

    mask = df[key_col].astype(str) == key_val

    if mask.any():
        # Update only the fields present in record
        for col, val in record.items():
            df.loc[mask, col] = val
    else:
        # New row — append
        new_row = {col: "" for col in df.columns}
        new_row.update(record)
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    save_csv(df, filename)


def upsert_batch(filename: str, records: list, key_col: str = "program_id"):
    """Batch upsert — more efficient than calling upsert_record in a loop."""
    if not records:
        return

    ensure_output_dir()
    df = load_csv(filename)

    if df.empty:
        df = pd.DataFrame(records)
        save_csv(df, filename)
        return

    # Add any new columns
    all_cols = set(df.columns)
    for r in records:
        all_cols.update(r.keys())
    for col in all_cols:
        if col not in df.columns:
            df[col] = ""

    df = df.set_index(key_col)

    for record in records:
        key_val = str(record[key_col])
        rec_copy = {k: v for k, v in record.items() if k != key_col}
        if key_val in df.index:
            for col, val in rec_copy.items():
                df.loc[key_val, col] = val
        else:
            new_row = {col: "" for col in df.columns}
            new_row.update(rec_copy)
            df.loc[key_val] = new_row

    df = df.reset_index()
    save_csv(df, filename)
