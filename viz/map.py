import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def setup_page() -> None:
    st.set_page_config(
        page_title="Healthcare Salaries",
        layout="wide",
    )
    st.title("Healthcare Occupation Salaries by State")
    st.caption("Annual mean wage data — BLS May 2024")


def build_map(df: pd.DataFrame, occupation: str) -> go.Figure:
    fig = px.choropleth(
        df,
        locations="state_abbrev",
        locationmode="USA-states",
        color="annual_mean_wage",
        scope="usa",
        color_continuous_scale="Blues",
        range_color=(df["annual_mean_wage"].min(), df["annual_mean_wage"].max()),
        hover_name="state_name",
        hover_data={
            "state_abbrev":        False,
            "annual_mean_wage":    False,
            "Annual Mean Wage":    True,
            "annual_median_wage":  ":$,.0f",
            "number_of_employees": ":,.0f",
        },
        labels={
            "annual_median_wage":  "Annual Median Wage",
            "number_of_employees": "Employees",
        },
        title=f"{occupation} — Annual Mean Wage by State",
    )

    fig.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        coloraxis_colorbar=dict(
            title="Annual Mean<br>Wage",
            tickprefix="$",
            tickformat=",",
        ),
    )

    return fig


def render_map(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch")


def show_missing_note(df: pd.DataFrame) -> None:
    missing = sorted(df[df["annual_mean_wage"].isna()]["state_name"].tolist())
    if missing:
        st.caption(f"Gray states have no available data: {', '.join(missing)}")
