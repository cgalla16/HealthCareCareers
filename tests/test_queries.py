"""
Tests for db/queries.py:
  - load_data (patched DB_PATH so tests never touch the real healthcare.db)
"""

import pandas as pd
import pytest

import db.queries as queries_mod

# Eight states loaded into the test DB (matches conftest.SAMPLE_STATES)
SAMPLE_STATES = [
    "Alabama", "Alaska", "Arizona", "California",
    "Florida", "New York", "Texas", "Wyoming",
]


@pytest.fixture(autouse=True)
def patch_db_path(test_db_path, monkeypatch):
    """Redirect all load_data calls to the temporary test database."""
    monkeypatch.setattr(queries_mod, "DB_PATH", test_db_path)


class TestLoadData:
    def test_returns_dataframe(self):
        df = queries_mod.load_data("Physical Therapists")
        assert isinstance(df, pd.DataFrame)

    def test_expected_columns_present(self):
        df = queries_mod.load_data("Physical Therapists")
        required = {
            "state_name", "annual_mean_wage", "annual_median_wage",
            "number_of_employees", "state_abbrev", "Annual Mean Wage",
        }
        assert required.issubset(set(df.columns))

    def test_all_db_states_returned(self):
        """LEFT JOIN ensures every state stored in the DB appears in the result."""
        df = queries_mod.load_data("Physical Therapists")
        returned_states = set(df["state_name"].tolist())
        for state in SAMPLE_STATES:
            assert state in returned_states

    def test_row_count_equals_state_count(self):
        df = queries_mod.load_data("Physical Therapists")
        assert len(df) == len(SAMPLE_STATES)

    def test_annual_mean_wage_formatted_with_dollar_sign(self):
        df = queries_mod.load_data("Physical Therapists")
        # All rows in the test DB have non-null annual_mean_wage
        assert df["Annual Mean Wage"].str.startswith("$").all()

    def test_annual_mean_wage_formatted_with_comma_separator(self):
        df = queries_mod.load_data("Physical Therapists")
        # e.g. "$80,000" — comma present
        assert df["Annual Mean Wage"].str.contains(",").all()

    def test_missing_wage_shows_no_data_label(self):
        """Querying a nonexistent occupation triggers the LEFT JOIN NULL path."""
        df = queries_mod.load_data("Nonexistent Occupation")
        assert (df["Annual Mean Wage"] == "No Data").all()

    def test_unknown_occupation_returns_nan_wages(self):
        df = queries_mod.load_data("Nonexistent Occupation")
        assert df["annual_mean_wage"].isna().all()

    def test_unknown_occupation_still_returns_all_states(self):
        """Even with no matching occupation, all states must appear (LEFT JOIN)."""
        df = queries_mod.load_data("Nonexistent Occupation")
        assert len(df) == len(SAMPLE_STATES)

    def test_state_abbrev_populated_for_known_states(self):
        df = queries_mod.load_data("Physical Therapists")
        alabama = df[df["state_name"] == "Alabama"]
        assert not alabama.empty
        assert alabama["state_abbrev"].iloc[0] == "AL"

    def test_state_abbrev_california(self):
        df = queries_mod.load_data("Physical Therapists")
        ca = df[df["state_name"] == "California"]
        assert ca["state_abbrev"].iloc[0] == "CA"

    def test_different_occupations_return_independent_data(self):
        """Physical and Occupational Therapists are separate queries."""
        df_pt = queries_mod.load_data("Physical Therapists")
        df_ot = queries_mod.load_data("Occupational Therapists")
        # Both should return the same states (same sample data loaded for both)
        assert set(df_pt["state_name"]) == set(df_ot["state_name"])

    def test_wage_values_match_source_data(self):
        """Alabama (index 0) has annual_mean_wage = 80000 in sample_clean_df."""
        df = queries_mod.load_data("Physical Therapists")
        alabama = df[df["state_name"] == "Alabama"]
        assert alabama["annual_mean_wage"].iloc[0] == pytest.approx(80000)
