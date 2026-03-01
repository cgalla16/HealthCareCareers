import plotly.graph_objects as go


def build_salary_percentile_chart(ns: dict) -> go.Figure | None:
    """
    Horizontal salary range bar (Glassdoor/LinkedIn style).

    Outer light band = 10th–90th percentile
    Inner dark band  = 25th–75th (IQR)
    White line       = median
    """
    p10 = ns.get("annual_10th")
    p25 = ns.get("annual_25th")
    p50 = ns.get("annual_median")
    p75 = ns.get("annual_75th")
    p90 = ns.get("annual_90th")

    if not all([p10, p25, p50, p75, p90]):
        return None

    BAR_Y  = 0.50   # vertical center of the bar
    BAR_H  = 0.30   # half-height of the bar
    x_pad  = (p90 - p10) * 0.10

    fig = go.Figure()

    # Invisible trace so Plotly registers the x range
    fig.add_trace(go.Scatter(
        x=[p10 - x_pad, p90 + x_pad],
        y=[BAR_Y, BAR_Y],
        mode="markers",
        marker=dict(opacity=0),
        hoverinfo="skip",
        showlegend=False,
    ))

    # Outer band: 10th → 90th (light blue)
    fig.add_shape(
        type="rect",
        x0=p10, x1=p90,
        y0=BAR_Y - BAR_H, y1=BAR_Y + BAR_H,
        fillcolor="#BFDBFE",
        line_width=0,
    )

    # IQR band: 25th → 75th (medium blue)
    fig.add_shape(
        type="rect",
        x0=p25, x1=p75,
        y0=BAR_Y - BAR_H, y1=BAR_Y + BAR_H,
        fillcolor="#3B82F6",
        line_width=0,
    )

    # Median line (white, slightly taller than bar)
    fig.add_shape(
        type="line",
        x0=p50, x1=p50,
        y0=BAR_Y - BAR_H - 0.04, y1=BAR_Y + BAR_H + 0.04,
        line=dict(color="white", width=3),
    )

    # Dots + labels at each percentile
    percentiles = [
        (p10, "10th",   False),
        (p25, "25th",   False),
        (p50, "Median", True),   # highlighted
        (p75, "75th",   False),
        (p90, "90th",   False),
    ]

    for val, label, is_median in percentiles:
        # Dot on the bar
        fig.add_trace(go.Scatter(
            x=[val], y=[BAR_Y],
            mode="markers",
            marker=dict(
                size=11,
                color="white",
                line=dict(color="#1D4ED8" if not is_median else "#1E3A8A", width=2),
            ),
            hovertemplate=f"<b>{label}</b>: ${val:,.0f}<extra></extra>",
            showlegend=False,
        ))

        # Dollar label above the bar
        fig.add_annotation(
            x=val,
            y=BAR_Y + BAR_H + 0.08,
            text=f"${val / 1000:.0f}k",
            showarrow=False,
            font=dict(
                size=13,
                color="#111827" if is_median else "#374151",
                family="sans-serif",
            ),
            yanchor="bottom",
        )

        # Percentile label below the bar
        fig.add_annotation(
            x=val,
            y=BAR_Y - BAR_H - 0.08,
            text=f"<b>{label}</b>" if is_median else label,
            showarrow=False,
            font=dict(size=11, color="#6B7280"),
            yanchor="top",
        )

    fig.update_layout(
        height=160,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(
            range=[p10 - x_pad, p90 + x_pad],
            showgrid=False,
            zeroline=False,
            showticklabels=False,
        ),
        yaxis=dict(visible=False, range=[0, 1]),
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    return fig
