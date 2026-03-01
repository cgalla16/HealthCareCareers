import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from constants.states import STATE_ABBREVS

DB_PATH = Path(__file__).parent.parent / "healthcare.db"


@st.cache_data
def load_data(occupation_name: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT
            s.name               AS state_name,
            e.annual_mean_wage,
            e.annual_median_wage,
            e.number_of_employees
        FROM states s
        LEFT JOIN employment_stats e
            ON  e.state_id      = s.id
            AND e.occupation_id = (SELECT id FROM occupations WHERE name = ?)
    """
    df = pd.read_sql_query(query, conn, params=(occupation_name,))
    conn.close()
    df["state_abbrev"] = df["state_name"].map(STATE_ABBREVS)
    df["Annual Mean Wage"] = df["annual_mean_wage"].apply(
        lambda x: f"${x:,.0f}" if pd.notna(x) else "No Data"
    )
    return df


@st.cache_data
def load_occupation_national_stats(occupation_name: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        """
        SELECT ns.employment, ns.annual_mean, ns.annual_10th, ns.annual_25th,
               ns.annual_median, ns.annual_75th, ns.annual_90th, ns.bls_growth_pct
        FROM occupation_national_stats ns
        JOIN occupations o ON o.id = ns.occupation_id
        WHERE o.name = ?
        """,
        (occupation_name,),
    ).fetchone()
    conn.close()
    if row is None:
        return {}
    keys = ["employment", "annual_mean", "annual_10th", "annual_25th",
            "annual_median", "annual_75th", "annual_90th", "bls_growth_pct"]
    return dict(zip(keys, row))


@st.cache_data
def load_program_stats(occupation_name: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        """
        SELECT
            COUNT(*)                      AS num_programs,
            SUM(p.graduates_tested)       AS total_graduates,
            ROUND(AVG(p.graduates_tested)) AS avg_size
        FROM programs p
        JOIN occupations o ON o.id = p.occupation_id
        WHERE o.name = ?
        """,
        (occupation_name,),
    ).fetchone()
    conn.close()
    if row is None:
        return {}
    return {
        "num_programs":      row[0] or 0,
        "total_graduates":   int(row[1]) if row[1] is not None else None,
        "avg_size":          int(row[2]) if row[2] is not None else None,
    }


@st.cache_data
def load_work_settings(occupation_name: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT
            ws.setting_name       AS "Work Setting",
            ws.pct_of_total       AS "% of Employment",
            ws.annual_mean_wage   AS "Mean Salary",
            ws.annual_median_wage AS "Median Salary"
        FROM work_setting_salaries ws
        JOIN occupations o ON o.id = ws.occupation_id
        WHERE o.name = ?
        ORDER BY ws.pct_of_total DESC
    """
    df = pd.read_sql_query(query, conn, params=(occupation_name,))
    conn.close()
    df["Mean Salary"]   = df["Mean Salary"].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "—")
    df["Median Salary"] = df["Median Salary"].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "—")
    return df
