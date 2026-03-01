"""
Tests for constants/states.py:
  - STATE_ABBREVS completeness, format, and uniqueness
"""

from constants.states import STATE_ABBREVS

ALL_50_STATES = {
    "Alabama", "Alaska", "Arizona", "Arkansas", "California",
    "Colorado", "Connecticut", "Delaware", "Florida", "Georgia",
    "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas",
    "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts",
    "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana",
    "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico",
    "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma",
    "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
    "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
}


class TestStateAbbrevs:
    def test_all_50_states_present(self):
        missing = ALL_50_STATES - set(STATE_ABBREVS.keys())
        assert missing == set(), f"Missing states: {missing}"

    def test_district_of_columbia_present(self):
        assert "District of Columbia" in STATE_ABBREVS
        assert STATE_ABBREVS["District of Columbia"] == "DC"

    def test_puerto_rico_present(self):
        assert "Puerto Rico" in STATE_ABBREVS
        assert STATE_ABBREVS["Puerto Rico"] == "PR"

    def test_total_entry_count_is_52(self):
        # 50 states + DC + Puerto Rico
        assert len(STATE_ABBREVS) == 52

    def test_all_abbreviations_are_two_uppercase_letters(self):
        invalid = {k: v for k, v in STATE_ABBREVS.items()
                   if not (len(v) == 2 and v.isupper())}
        assert invalid == {}, f"Invalid abbreviations: {invalid}"

    def test_no_duplicate_abbreviations(self):
        abbrevs = list(STATE_ABBREVS.values())
        assert len(abbrevs) == len(set(abbrevs)), "Duplicate abbreviations found"

    def test_no_duplicate_state_names(self):
        names = list(STATE_ABBREVS.keys())
        assert len(names) == len(set(names)), "Duplicate state names found"

    def test_known_state_mappings(self):
        known = {
            "California":  "CA",
            "New York":    "NY",
            "Texas":       "TX",
            "Florida":     "FL",
            "Alabama":     "AL",
            "Wyoming":     "WY",
        }
        for state, expected_abbrev in known.items():
            assert STATE_ABBREVS[state] == expected_abbrev, (
                f"{state}: expected {expected_abbrev}, got {STATE_ABBREVS[state]}"
            )

    def test_no_state_name_is_empty(self):
        assert all(len(k.strip()) > 0 for k in STATE_ABBREVS.keys())

    def test_no_abbreviation_is_empty(self):
        assert all(len(v.strip()) > 0 for v in STATE_ABBREVS.values())
