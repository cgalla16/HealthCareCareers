"""
Tests for viz/map.py:
  - build_map
  - show_missing_note
"""

import pandas as pd
import plotly.graph_objects as go
import pytest
import streamlit as st   # resolves to the MagicMock set up in conftest.py

from viz.map import build_map, show_missing_note

# Representative DataFrame as load_data would produce
SAMPLE_DF = pd.DataFrame({
    "state_name":          ["Alabama", "California", "Wyoming"],
    "state_abbrev":        ["AL", "CA", "WY"],
    "annual_mean_wage":    [84000.0, 105000.0, None],
    "annual_median_wage":  [82000.0, 103000.0, None],
    "number_of_employees": [1200.0,  8500.0,   None],
    "Annual Mean Wage":    ["$84,000", "$105,000", "No Data"],
})

FULL_DF = pd.DataFrame({
    "state_name":          ["Alabama", "California", "Wyoming"],
    "state_abbrev":        ["AL", "CA", "WY"],
    "annual_mean_wage":    [84000.0, 105000.0, 95000.0],
    "annual_median_wage":  [82000.0, 103000.0, 92000.0],
    "number_of_employees": [1200.0,  8500.0,   800.0],
    "Annual Mean Wage":    ["$84,000", "$105,000", "$95,000"],
})


class TestBuildMap:
    def test_returns_plotly_figure(self):
        fig = build_map(SAMPLE_DF, "Physical Therapists")
        assert isinstance(fig, go.Figure)

    def test_title_contains_occupation_name(self):
        occupation = "Physical Therapists"
        fig = build_map(SAMPLE_DF, occupation)
        assert occupation in fig.layout.title.text

    def test_figure_has_choropleth_trace(self):
        fig = build_map(SAMPLE_DF, "Physical Therapists")
        trace_types = [type(t).__name__ for t in fig.data]
        assert "Choropleth" in trace_types

    def test_colorbar_tickprefix_is_dollar_sign(self):
        fig = build_map(SAMPLE_DF, "Physical Therapists")
        assert fig.layout.coloraxis.colorbar.tickprefix == "$"

    def test_colorbar_title_set(self):
        fig = build_map(SAMPLE_DF, "Physical Therapists")
        assert fig.layout.coloraxis.colorbar.title.text is not None

    def test_scope_is_usa(self):
        fig = build_map(SAMPLE_DF, "Physical Therapists")
        assert fig.layout.geo.scope == "usa"

    def test_different_occupations_produce_different_titles(self):
        fig_pt = build_map(SAMPLE_DF, "Physical Therapists")
        fig_ot = build_map(SAMPLE_DF, "Occupational Therapists")
        assert fig_pt.layout.title.text != fig_ot.layout.title.text

    def test_all_data_present_no_exception(self):
        """build_map should not raise even when all wages are present."""
        build_map(FULL_DF, "Speech-Language Pathologists")


class TestShowMissingNote:
    def setup_method(self):
        # Reset the mock between tests so call counts don't bleed across
        st.caption.reset_mock()

    def test_caption_called_when_states_missing(self):
        show_missing_note(SAMPLE_DF)
        st.caption.assert_called_once()

    def test_missing_state_name_appears_in_caption(self):
        show_missing_note(SAMPLE_DF)
        call_text = st.caption.call_args[0][0]
        assert "Wyoming" in call_text

    def test_no_caption_when_all_data_present(self):
        show_missing_note(FULL_DF)
        st.caption.assert_not_called()

    def test_multiple_missing_states_all_listed(self):
        df = pd.DataFrame({
            "state_name":       ["Alabama", "Texas", "Wyoming"],
            "state_abbrev":     ["AL", "TX", "WY"],
            "annual_mean_wage": [None, None, 95000.0],
            "annual_median_wage": [None, None, 92000.0],
            "number_of_employees": [None, None, 800.0],
            "Annual Mean Wage": ["No Data", "No Data", "$95,000"],
        })
        show_missing_note(df)
        call_text = st.caption.call_args[0][0]
        assert "Alabama" in call_text
        assert "Texas" in call_text

    def test_missing_states_listed_alphabetically(self):
        df = pd.DataFrame({
            "state_name":       ["Wyoming", "Alabama", "California"],
            "state_abbrev":     ["WY", "AL", "CA"],
            "annual_mean_wage": [None, None, 95000.0],
            "annual_median_wage": [None, None, 92000.0],
            "number_of_employees": [None, None, 800.0],
            "Annual Mean Wage": ["No Data", "No Data", "$95,000"],
        })
        show_missing_note(df)
        call_text = st.caption.call_args[0][0]
        # "Alabama" should appear before "Wyoming" in sorted output
        assert call_text.index("Alabama") < call_text.index("Wyoming")

    def test_empty_dataframe_no_caption(self):
        df = pd.DataFrame(columns=["state_name", "annual_mean_wage"])
        show_missing_note(df)
        st.caption.assert_not_called()
