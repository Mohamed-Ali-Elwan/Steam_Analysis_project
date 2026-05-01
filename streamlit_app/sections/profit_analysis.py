import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from sections.analytics_utils import (
    build_tag_profit_table,
    build_top_games_per_tag,
    filter_profit_scope,
    prepare_profit_frame,
)
from ui import STRETCH_WIDTH


def render_profit_analysis(df, merged_data):
    st.title("Profit Analysis")
    st.markdown("---")

    profit_frame = prepare_profit_frame(df)
    if (
        profit_frame.empty
        or "Profit" not in profit_frame.columns
        or "total_steam_purchases" not in profit_frame.columns
    ):
        st.warning("Price and total review counts are required for profit analysis.")
        return

    tag_tab, games_tab, drivers_tab = st.tabs(
        ["Tag Profit", "Top Games", "Sales & Review Drivers"]
    )

    with tag_tab:
        _render_tag_profit_tab(profit_frame)

    with games_tab:
        _render_top_games_tab(profit_frame)

    with drivers_tab:
        _render_profit_driver_tab(profit_frame)


def _render_tag_profit_tab(profit_frame):
    tag_profit_df = build_tag_profit_table(profit_frame)
    if tag_profit_df.empty:
        st.info("No tag-level profit data is available.")
        return

    scope = st.radio(
        "Tag segment",
        ["All", "AAA", "Indie"],
        horizontal=True,
        key="profit_scope",
    )
    scoped_df = filter_profit_scope(tag_profit_df, scope)
    if scoped_df.empty:
        st.info(f"No {scope.lower()} rows are available.")
        return

    st.dataframe(
        scoped_df.style.format(
            {
                "positive%": "{:.2f}",
                "negative%": "{:.2f}",
                "avg_price": "${:.2f}",
                "Average Profit (M)": "${:.2f}M",
                "Average Profit per game (M)": "${:.2f}M",
            }
        ),
        **STRETCH_WIDTH,
    )

    top_n = st.slider(
        "Tags in notebook charts",
        min_value=1,
        max_value=max(1, min(25, len(scoped_df))),
        value=min(15, len(scoped_df)),
        key="profit_tag_top_n",
    )
    sorted_df = scoped_df.sort_values("Average Profit (M)", ascending=False).head(top_n)
    chart_title = {
        "All": "Game Tag Performance Analysis",
        "AAA": "AAA Game Tag Performance Analysis",
        "Indie": "Indie Game Tag Performance Analysis",
    }[scope]
    st.plotly_chart(_build_tag_profit_figure(sorted_df, chart_title), **STRETCH_WIDTH)


def _render_top_games_tab(profit_frame):
    top_n = st.slider(
        "Top games to rank",
        min_value=1,
        max_value=max(1, min(25, len(profit_frame))),
        value=min(15, len(profit_frame)),
        key="profit_game_top_n",
    )
    top_profit = profit_frame.sort_values("Profit", ascending=False).head(top_n)

    fig_top = px.bar(
        top_profit,
        x="Profit",
        y="name",
        color="primary_tag",
        hover_data=["price", "total_reviews", "positive_ratio"],
        title="Top Games by Estimated Profit",
        labels={"name": "Game Name", "Profit": "Profit ($)"},
    )
    fig_top.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_top, **STRETCH_WIDTH)

    top_per_tag = build_top_games_per_tag(profit_frame, n=3)
    if top_per_tag.empty:
        return

    fig_treemap = px.treemap(
        top_per_tag,
        path=[px.Constant("All Tags"), "primary_tag", "name"],
        values="Profit",
        color="Profit",
        color_continuous_scale="Viridis",
        title="Top 3 Games by Profit within Each Tag",
        hover_data=["Profit", "price", "total_reviews", "positive_ratio"],
    )
    fig_treemap.update_layout(margin=dict(t=50, l=25, r=25, b=25))
    st.plotly_chart(fig_treemap, **STRETCH_WIDTH)


def _render_profit_driver_tab(profit_frame):
    sales_frame = profit_frame[profit_frame["Profit"].fillna(0) > 0].copy()
    if sales_frame.empty:
        st.info("No positive-profit game rows are available.")
        return

    fig_reviews = px.scatter(
        sales_frame,
        x="total_reviews",
        y="Profit",
        color="positive_ratio",
        size="price",
        hover_name="name",
        hover_data=["primary_tag", "total_positive", "total_negative"],
        color_continuous_scale="RdYlGn",
        title="Profit vs. Total Reviews",
        labels={
            "total_reviews": "Total Reviews",
            "positive_ratio": "Positive Review Ratio",
        },
    )
    fig_reviews.update_layout(coloraxis_colorbar=dict(title="Positive Ratio"))
    fig_reviews.update_xaxes(type="log")
    st.plotly_chart(fig_reviews, **STRETCH_WIDTH)

    fig_correlation = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=("Positive Reviews vs. Profit", "Negative Reviews vs. Profit"),
    )
    fig_correlation.add_trace(
        go.Scatter(
            x=sales_frame["total_positive"],
            y=sales_frame["Profit"],
            mode="markers",
            marker=dict(
                size=8,
                color=sales_frame["positive_ratio"],
                colorscale="RdYlGn",
                showscale=True,
                colorbar=dict(title="Positive Ratio"),
            ),
            text=sales_frame["name"],
            hovertemplate="<b>%{text}</b><br>X=%{x}<br>Profit=$%{y:,.0f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig_correlation.add_trace(
        go.Scatter(
            x=sales_frame["total_negative"],
            y=sales_frame["Profit"],
            mode="markers",
            marker=dict(
                size=8,
                color=sales_frame["positive_ratio"],
                colorscale="RdYlGn",
                showscale=False,
            ),
            text=sales_frame["name"],
            hovertemplate="<b>%{text}</b><br>X=%{x}<br>Profit=$%{y:,.0f}<extra></extra>",
        ),
        row=1,
        col=2,
    )
    fig_correlation.update_layout(
        height=500,
        title_text="Correlation Between Reviews and Profit",
    )
    fig_correlation.update_xaxes(title_text="Total Positive Reviews", row=1, col=1)
    fig_correlation.update_xaxes(title_text="Total Negative Reviews", row=1, col=2)
    fig_correlation.update_yaxes(title_text="Profit ($)", row=1, col=1)
    fig_correlation.update_yaxes(title_text="Profit ($)", row=1, col=2)
    st.plotly_chart(fig_correlation, **STRETCH_WIDTH)

    fig_price = px.scatter(
        sales_frame,
        x="price",
        y="total_steam_purchases",
        color="primary_tag",
        hover_name="name",
        title="Price vs. Estimated Purchases from Reviews",
        labels={
            "price": "Price ($)",
            "total_steam_purchases": "Estimated Purchases (Total Reviews)",
        },
    )
    st.plotly_chart(fig_price, **STRETCH_WIDTH)


def _build_tag_profit_figure(sorted_df, title):
    fig = make_subplots(
        rows=2,
        cols=2,
        specs=[[{"type": "bar"}, {"type": "scatter"}], [{"type": "bar", "colspan": 2}, None]],
        subplot_titles=(
            "Average Profit by Tag (Millions $)",
            "Profit vs. Review Sentiment",
            "Average Profit per Game by Tag (Millions $)",
        ),
        vertical_spacing=0.18,
        horizontal_spacing=0.08,
    )

    fig.add_trace(
        go.Bar(
            x=sorted_df["tag"],
            y=sorted_df["Average Profit (M)"],
            marker_color=sorted_df["positive%"],
            marker_showscale=False,
            marker_colorscale="RdYlGn",
            text=sorted_df["Average Profit (M)"].apply(lambda value: f"${value:.1f}M"),
            textposition="auto",
            name="Total Profit",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=sorted_df["positive%"],
            y=sorted_df["Average Profit (M)"],
            mode="markers",
            marker=dict(
                size=sorted_df["Total Reviews"].apply(
                    lambda value: min(max(value / 10000, 10), 50)
                ),
                color=sorted_df["avg_price"],
                colorscale="Viridis",
                colorbar=dict(title="Avg Price ($)", x=1.04, len=0.42, y=0.78),
                showscale=True,
            ),
            text=sorted_df["tag"],
            hovertemplate=(
                "<b>%{text}</b><br>Positive: %{x:.1f}%<br>Profit: $%{y:.1f}M"
                "<br>Avg Price: $%{marker.color:.2f}<extra></extra>"
            ),
            name="Tag Performance",
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Bar(
            x=sorted_df["tag"],
            y=sorted_df["Average Profit per game (M)"],
            marker_color=sorted_df["Game Count"],
            marker_colorscale="Blues",
            marker_showscale=False,
            text=sorted_df["Average Profit per game (M)"].apply(
                lambda value: f"${value:.2f}M"
            ),
            textposition="auto",
            name="Profit per Game",
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title_text=title,
        height=900,
        margin=dict(r=110),
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(tickangle=45, row=1, col=1)
    fig.update_xaxes(tickangle=45, row=2, col=1)
    fig.update_xaxes(title_text="Positive Reviews (%)", row=1, col=2)
    fig.update_yaxes(title_text="Average Profit (Millions $)", row=1, col=1)
    fig.update_yaxes(title_text="Average Profit (Millions $)", row=1, col=2)
    fig.update_yaxes(title_text="Average Profit per Game (Millions $)", row=2, col=1)
    return fig
