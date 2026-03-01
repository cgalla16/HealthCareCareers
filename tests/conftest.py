"""
Shared fixtures and setup for the healthcare dashboard test suite.

Streamlit is mocked here — before any project imports — so that
@st.cache_data becomes a no-op passthrough and viz/db modules can be
imported without a running Streamlit server.
"""

import sys
from unittest.mock import MagicMock

# ── Streamlit mock (must happen before project imports) ──────────────────────
_mock_st = MagicMock()
_mock_st.cache_data = lambda func: func      # passthrough — no caching in tests
sys.modules["streamlit"] = _mock_st

# ── Standard imports (safe now that streamlit is mocked) ─────────────────────
import io
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

# Eight states used as representative sample data throughout the test suite
SAMPLE_STATES = [
    "Alabama", "Alaska", "Arizona", "California",
    "Florida", "New York", "Texas", "Wyoming",
]


def _make_sample_row(state: str, idx: int) -> dict:
    """Return one fully-populated wage row for a given state."""
    return {
        "States":                        state,
        "Number of Employees":           1000 + idx * 100,
        "Hourly mean wage":              40.0 + idx,
        "Annual mean wage":              80000 + idx * 1000,
        "Hourly 10th percentile wage":   25.0,
        "Hourly 25th percentile wage":   30.0,
        "Hourly median wage":            38.0,
        "Hourly 75th percentile wage":   48.0,
        "Hourly 90th percentile wage":   55.0,
        "Annual 10th percentile wage":   52000,
        "Annual 25th percentile wage":   62000,
        "Annual median wage":            79000 + idx * 500,
        "Annual 75th percentile wage":  100000,
        "Annual 90th percentile wage":  115000,
        "Employment per 1,000 jobs":     2.5,
        "Location Quotient":             1.1,
    }


@pytest.fixture
def sample_clean_df():
    """DataFrame matching clean_xlsx output — 8 states, all wage columns present."""
    return pd.DataFrame([_make_sample_row(s, i) for i, s in enumerate(SAMPLE_STATES)])


@pytest.fixture
def sample_xlsx_path(tmp_path):
    """Write a minimal BLS-style xlsx to a temp file and return its Path.

    Structure mirrors real BLS OES files:
      - Rows 1-5: metadata (skipped by clean_xlsx via skiprows=5)
      - Row 6:    column headers
      - Rows 7+:  state data rows
    """
    wb = Workbook()
    ws = wb.active

    # Rows 1-5: BLS metadata
    for _ in range(5):
        ws.append(["Bureau of Labor Statistics OES Data"] + [""] * 7)

    # Row 6: column headers (raw BLS format; one RSE column included)
    ws.append([
        "State (code)",
        "Employment",
        "Hourly mean wage",
        "Annual mean wage",
        "Relative standard error for annual mean wage (1)",   # RSE — must be dropped
        "Annual median wage",
        "Employment per 1,000 jobs",
        "Location Quotient",
    ])

    # Known state rows
    ws.append(["Alabama (01-00000)",    1200,    40.5, 84300,  1.2, 82000,  2.3, 1.05])
    ws.append(["California (06-00000)", 8500,    52.0, 108100, 0.8, 105000, 3.1, 1.42])
    # Wyoming: all data suppressed with BLS "(8)" marker
    ws.append(["Wyoming (56-00000)",    "(8)", "(8)", "(8)",   "",  "(8)",  "(8)", "(8)"])

    # Non-state rows (should be filtered out by clean_xlsx)
    ws.append(["United States (00-00000)", 95000, 48.0, 99800, 0.5, 97500, 2.9, 1.33])
    ws.append(["Footnote text", "", "", "", "", "", "", ""])

    xlsx_path = tmp_path / "TestOccupation.xlsx"
    wb.save(xlsx_path)
    return xlsx_path


@pytest.fixture
def test_db_path(tmp_path, sample_clean_df):
    """Build a temporary healthcare.db with two occupations and return its Path."""
    import db.pipelines.occupations as pipeline_mod
    from db.pipelines.occupations import build_db

    db_file = tmp_path / "healthcare.db"
    original_db_path = pipeline_mod.DB_PATH
    pipeline_mod.DB_PATH = db_file

    try:
        build_db({
            "Physical Therapists":    sample_clean_df,
            "Occupational Therapists": sample_clean_df.copy(),
        })
    finally:
        pipeline_mod.DB_PATH = original_db_path

    return db_file
