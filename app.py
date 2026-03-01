import streamlit as st

from constants.occupations import OCCUPATIONS
from db.queries import load_data
from viz.map import build_map, render_map, setup_page, show_missing_note

setup_page()

with st.sidebar:
    st.header("Filters")
    occupation = st.radio("Occupation", OCCUPATIONS)

df = load_data(occupation)

fig = build_map(df, occupation)
render_map(fig)
show_missing_note(df)
