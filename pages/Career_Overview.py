import streamlit as st

from constants.occupations import OCCUPATIONS
from db.queries import load_occupation_national_stats, load_program_stats, load_work_settings
from viz.charts import build_salary_percentile_chart

st.set_page_config(page_title="Career Overview", layout="wide")

with st.sidebar:
    st.header("Filters")
    occupation = st.radio("Occupation", OCCUPATIONS)

st.title(occupation)
st.caption("Salary data — BLS OEWS May 2024")

ns = load_occupation_national_stats(occupation)
ps = load_program_stats(occupation)

# ── KPI row ──────────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)

with col1:
    val = f"{ns['employment']:,}" if ns.get("employment") else "N/A"
    st.metric("Total Employed", val)

with col2:
    val = f"${ns['annual_median']:,.0f}" if ns.get("annual_median") else "N/A"
    st.metric("Median Salary", val)

with col3:
    growth = f"{ns['bls_growth_pct']:.0f}%" if ns.get("bls_growth_pct") is not None else "N/A"
    st.metric("Projected 10-Year Growth", growth)

with col4:
    num_prog = ps.get("num_programs") or 0
    st.metric("Accredited Programs", num_prog if num_prog else "N/A")

st.divider()

# ── Salary percentiles ────────────────────────────────────────────────────────

st.subheader("Salary Percentiles")
st.caption("Annual wages across all work settings nationally — BLS May 2024")

fig = build_salary_percentile_chart(ns)
if fig is None:
    st.info("No percentile data available for this occupation.")
else:
    st.plotly_chart(fig, width="stretch")

st.divider()

# ── Salary by work setting ────────────────────────────────────────────────────

st.subheader("Salary by Work Setting")

ws_df = load_work_settings(occupation)
if ws_df.empty:
    st.info("No work setting data available for this occupation.")
else:
    st.dataframe(
        ws_df,
        column_config={
            "Work Setting":    st.column_config.TextColumn("Work Setting"),
            "% of Employment": st.column_config.NumberColumn("% of Employment", format="%.1f%%"),
            "Mean Salary":     st.column_config.TextColumn("Mean Salary"),
            "Median Salary":   st.column_config.TextColumn("Median Salary"),
        },
        hide_index=True,
        use_container_width=True,
    )

st.divider()

# ── Program statistics ────────────────────────────────────────────────────────

st.subheader("Programs")

q1, q2, q3 = st.columns(3)

with q1:
    val = f"{ps['total_graduates']:,}" if ps.get("total_graduates") is not None else "N/A"
    st.metric("Graduates Tested Annually", val)

with q2:
    val = str(ps["avg_size"]) if ps.get("avg_size") is not None else "N/A"
    st.metric("Avg Program Size", val)

with q3:
    st.metric("Programs Available to Apply", "N/A")
