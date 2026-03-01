"""
Tests for db/pipeline.py:
  - strip_footnote_markers
  - clean_xlsx
  - build_db
"""

import sqlite3

import pandas as pd
import pytest
from openpyxl import Workbook

import db.pipelines.occupations as pipeline_mod
from db.pipelines.occupations import build_db, clean_xlsx, strip_footnote_markers


# ── strip_footnote_markers ────────────────────────────────────────────────────

class TestStripFootnoteMarkers:
    def test_clean_name_unchanged(self):
        assert strip_footnote_markers("Annual mean wage") == "Annual mean wage"

    def test_strips_single_digit_marker(self):
        assert strip_footnote_markers("Annual mean wage (2)") == "Annual mean wage"

    def test_strips_multi_digit_marker(self):
        assert strip_footnote_markers("Hourly median wage (12)") == "Hourly median wage"

    def test_strips_marker_with_extra_whitespace(self):
        assert strip_footnote_markers("Location Quotient  (3)") == "Location Quotient"

    def test_empty_string_returns_empty(self):
        assert strip_footnote_markers("") == ""

    def test_marker_only_returns_empty(self):
        # A column that is purely a marker — rare but handled
        assert strip_footnote_markers("(8)") == ""

    def test_non_string_coerced_to_string(self):
        # Function calls str() on its argument
        assert strip_footnote_markers(42) == "42"

    def test_marker_in_middle_not_stripped(self):
        # Only trailing markers are removed
        result = strip_footnote_markers("Wage (2) estimate")
        assert result == "Wage (2) estimate"


# ── clean_xlsx ────────────────────────────────────────────────────────────────

class TestCleanXlsx:
    def test_returns_dataframe(self, sample_xlsx_path):
        df = clean_xlsx(sample_xlsx_path)
        assert isinstance(df, pd.DataFrame)

    def test_only_known_states_retained(self, sample_xlsx_path):
        df = clean_xlsx(sample_xlsx_path)
        assert set(df["States"]) == {"Alabama", "California", "Wyoming"}

    def test_non_state_rows_dropped(self, sample_xlsx_path):
        df = clean_xlsx(sample_xlsx_path)
        assert "United States" not in df["States"].values

    def test_footnote_rows_dropped(self, sample_xlsx_path):
        df = clean_xlsx(sample_xlsx_path)
        # "Footnote text" is not a known state
        assert "Footnote text" not in df["States"].values

    def test_state_codes_stripped_from_names(self, sample_xlsx_path):
        df = clean_xlsx(sample_xlsx_path)
        # No state name should contain parentheses
        assert not df["States"].str.contains(r"\(", na=False).any()

    def test_rse_columns_dropped(self, sample_xlsx_path):
        df = clean_xlsx(sample_xlsx_path)
        rse_cols = [c for c in df.columns if "relative standard error" in c.lower()]
        assert rse_cols == []

    def test_suppressed_values_become_nan(self, sample_xlsx_path):
        df = clean_xlsx(sample_xlsx_path)
        wyoming = df[df["States"] == "Wyoming"]
        assert not wyoming.empty
        assert wyoming["Annual mean wage"].isna().all()

    def test_employment_column_renamed_to_number_of_employees(self, sample_xlsx_path):
        df = clean_xlsx(sample_xlsx_path)
        assert "Number of Employees" in df.columns
        assert "Employment" not in df.columns

    def test_known_wage_values_parsed_correctly(self, sample_xlsx_path):
        df = clean_xlsx(sample_xlsx_path)
        alabama = df[df["States"] == "Alabama"]
        assert not alabama.empty
        assert alabama["Annual mean wage"].iloc[0] == pytest.approx(84300)

    def test_data_columns_are_numeric(self, sample_xlsx_path):
        df = clean_xlsx(sample_xlsx_path)
        assert pd.api.types.is_float_dtype(df["Annual mean wage"])

    def test_asterisk_becomes_nan(self, tmp_path):
        """A cell containing '*' should be converted to NaN."""
        wb = Workbook()
        ws = wb.active
        for _ in range(5):
            ws.append(["meta"] + [""] * 4)
        ws.append(["State (code)", "Employment", "Annual mean wage", "Annual median wage", "Location Quotient"])
        ws.append(["Texas (48-00000)", "*", 95000, 92000, 1.0])

        path = tmp_path / "asterisk_test.xlsx"
        wb.save(path)

        df = clean_xlsx(path)
        texas = df[df["States"] == "Texas"]
        assert not texas.empty
        assert texas["Number of Employees"].isna().all()

    def test_footnote_marker_stripped_from_column_names(self, tmp_path):
        """Column names like 'Annual mean wage (2)' are normalized to 'Annual mean wage'."""
        wb = Workbook()
        ws = wb.active
        for _ in range(5):
            ws.append(["meta"] + [""] * 2)
        ws.append(["State (code)", "Employment", "Annual mean wage (2)"])
        ws.append(["Florida (12-00000)", 5000, 97000])

        path = tmp_path / "footnote_col_test.xlsx"
        wb.save(path)

        df = clean_xlsx(path)
        assert "Annual mean wage" in df.columns
        assert "Annual mean wage (2)" not in df.columns


# ── build_db ──────────────────────────────────────────────────────────────────

class TestBuildDb:
    def test_creates_all_three_tables(self, test_db_path):
        con = sqlite3.connect(test_db_path)
        tables = {
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        con.close()
        assert tables == {"states", "occupations", "employment_stats"}

    def test_state_count_matches_input(self, test_db_path):
        con = sqlite3.connect(test_db_path)
        count = con.execute("SELECT COUNT(*) FROM states").fetchone()[0]
        con.close()
        assert count == 8   # sample_clean_df has 8 unique states

    def test_occupation_count_matches_input(self, test_db_path):
        con = sqlite3.connect(test_db_path)
        count = con.execute("SELECT COUNT(*) FROM occupations").fetchone()[0]
        con.close()
        assert count == 2   # Physical Therapists + Occupational Therapists

    def test_employment_stats_row_count(self, test_db_path):
        con = sqlite3.connect(test_db_path)
        count = con.execute("SELECT COUNT(*) FROM employment_stats").fetchone()[0]
        con.close()
        assert count == 16  # 8 states × 2 occupations

    def test_nan_stored_as_sql_null(self, tmp_path, sample_clean_df):
        """NaN values in the source DataFrame are stored as NULL in the DB."""
        db_file = tmp_path / "nan_test.db"
        df_with_nan = sample_clean_df.copy()
        df_with_nan.loc[0, "Annual mean wage"] = float("nan")

        original = pipeline_mod.DB_PATH
        pipeline_mod.DB_PATH = db_file
        try:
            build_db({"Physical Therapists": df_with_nan})
        finally:
            pipeline_mod.DB_PATH = original

        con = sqlite3.connect(db_file)
        null_count = con.execute(
            "SELECT COUNT(*) FROM employment_stats WHERE annual_mean_wage IS NULL"
        ).fetchone()[0]
        con.close()
        assert null_count == 1

    def test_unique_constraint_on_state_occupation(self, test_db_path):
        """Inserting a duplicate (state_id, occupation_id) pair raises IntegrityError."""
        con = sqlite3.connect(test_db_path)
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO employment_stats (state_id, occupation_id) VALUES (1, 1)"
            )
        con.close()

    def test_overwrites_existing_db(self, tmp_path, sample_clean_df):
        """Running build_db when a DB already exists replaces it cleanly."""
        db_file = tmp_path / "overwrite_test.db"
        original = pipeline_mod.DB_PATH
        pipeline_mod.DB_PATH = db_file
        try:
            build_db({"Physical Therapists": sample_clean_df})
            # Second call with a different occupation — DB should be replaced entirely
            build_db({"Occupational Therapists": sample_clean_df})
            con = sqlite3.connect(db_file)
            occ_names = {r[0] for r in con.execute("SELECT name FROM occupations").fetchall()}
            con.close()
        finally:
            pipeline_mod.DB_PATH = original

        assert occ_names == {"Occupational Therapists"}

    def test_foreign_key_references_valid_state(self, test_db_path):
        """Every employment_stats row references a state that exists in the states table."""
        con = sqlite3.connect(test_db_path)
        orphan_count = con.execute("""
            SELECT COUNT(*) FROM employment_stats e
            WHERE NOT EXISTS (SELECT 1 FROM states s WHERE s.id = e.state_id)
        """).fetchone()[0]
        con.close()
        assert orphan_count == 0

    def test_wage_values_stored_correctly(self, test_db_path):
        """Spot-check that a wage value round-trips through the DB without corruption."""
        con = sqlite3.connect(test_db_path)
        # Alabama (index 0) has annual_mean_wage = 80000
        row = con.execute("""
            SELECT e.annual_mean_wage
            FROM employment_stats e
            JOIN states s ON s.id = e.state_id
            JOIN occupations o ON o.id = e.occupation_id
            WHERE s.name = 'Alabama' AND o.name = 'Physical Therapists'
        """).fetchone()
        con.close()
        assert row is not None
        assert row[0] == pytest.approx(80000)
