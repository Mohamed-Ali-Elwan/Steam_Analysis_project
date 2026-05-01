import plotly.express as px
import streamlit as st

from sections.analytics_utils import (
    add_quadrant_guides,
    build_genre_metrics,
    explode_multivalue_frame,
    prepare_profit_frame,
)
from ui import STRETCH_WIDTH


def render_genre_analysis(df):
    st.title("Game Genres Analysis")
    st.markdown("---")

    if df is None or df.empty or "genres" not in df.columns:
        st.warning("Genres data is not available.")
        return

    distribution_tab, features_tab, competition_tab = st.tabs(
        ["Genre Distribution", "Features by Genre", "Competition"]
    )

    with distribution_tab:
        _render_genre_distribution(df)

    with features_tab:
        _render_genre_features(df)

    with competition_tab:
        _render_genre_competition(df)


def _render_genre_distribution(df):
    genre_exploded = explode_multivalue_frame(df, "genres", lowercase=True)
    genre_exploded = genre_exploded[genre_exploded["genres"] != "indie"].copy()
    if genre_exploded.empty:
        st.info("No exploded genre rows are available.")
        return

    genre_counts = (
        genre_exploded["genres"].value_counts().reset_index()
    )
    genre_counts.columns = ["genres", "count"]
    genre_positive_reviews = (
        genre_exploded.groupby("genres", dropna=False)["total_positive"]
        .sum()
        .reset_index()
        .sort_values("total_positive", ascending=False)
    )

    col1, col2 = st.columns(2)
    with col1:
        fig_genres = px.bar(
            genre_counts,
            x="genres",
            y="count",
            title="Genres by Number of Games",
            color="count",
            color_continuous_scale="Blues",
        )
        fig_genres.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_genres, **STRETCH_WIDTH)

    with col2:
        fig_positive = px.bar(
            genre_positive_reviews,
            x="total_positive",
            y="genres",
            orientation="h",
            title="Total Positive Reviews by Genre",
            color="total_positive",
            color_continuous_scale="Greens",
        )
        fig_positive.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_positive, **STRETCH_WIDTH)


def _render_genre_features(df):
    if "features" not in df.columns:
        st.info("Features data is not available for the genre breakdown.")
        return

    genre_feature_frame = explode_multivalue_frame(df, "genres", lowercase=True)
    genre_feature_frame = explode_multivalue_frame(genre_feature_frame, "features")
    if genre_feature_frame.empty:
        st.info("No genre-feature combinations are available.")
        return

    genre_options = sorted(genre_feature_frame["genres"].dropna().unique())
    selected_genre = st.selectbox("Genre", genre_options, key="genre_feature_selector")
    top_n = st.slider(
        "Top features to show",
        min_value=5,
        max_value=15,
        value=10,
        key="genre_feature_top_n",
    )

    top_features = (
        genre_feature_frame[genre_feature_frame["genres"] == selected_genre]
        .groupby("features", dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .head(top_n)
    )
    fig_features = px.bar(
        top_features,
        x="count",
        y="features",
        orientation="h",
        title=f"Top Features for Genre: {selected_genre.title()}",
        labels={"count": "Number of Games", "features": "Feature"},
        color="count",
        color_continuous_scale="Viridis",
    )
    fig_features.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_features, **STRETCH_WIDTH)


def _render_genre_competition(df):
    genre_metrics = build_genre_metrics(prepare_profit_frame(df))
    if genre_metrics.empty:
        st.info("Price and total review counts are required for genre competition analysis.")
        return

    min_games = st.slider(
        "Minimum games per genre",
        min_value=1,
        max_value=max(1, int(genre_metrics["game_count"].max())),
        value=min(3, int(genre_metrics["game_count"].max())),
        key="genre_competition_min_games",
    )
    filtered_metrics = genre_metrics[genre_metrics["game_count"] >= min_games].copy()
    if filtered_metrics.empty:
        st.info("No genres meet the minimum game-count threshold.")
        return

    median_count = filtered_metrics["game_count"].median()
    median_profit = filtered_metrics["avg_profit"].median()

    st.dataframe(
        filtered_metrics.style.format(
            {
                "avg_profit": "${:,.0f}",
                "avg_purchases": "{:,.0f}",
                "avg_positive_ratio": "{:.2%}",
            }
        ),
        **STRETCH_WIDTH,
    )

    fig_competition = px.scatter(
        filtered_metrics,
        x="game_count",
        y="avg_profit",
        color="avg_positive_ratio",
        size="avg_purchases",
        hover_name="genres",
        text="genres",
        color_continuous_scale="RdYlGn",
        title="Genre Competition vs. Profitability Quadrant Analysis",
        labels={
            "game_count": "Number of Games (Competition)",
            "avg_profit": "Average Profit ($)",
            "avg_positive_ratio": "Avg. Positive Ratio",
        },
    )
    add_quadrant_guides(
        fig_competition,
        filtered_metrics,
        "game_count",
        "avg_profit",
        median_count,
        median_profit,
    )
    fig_competition.update_traces(
        textposition="top center",
        textfont=dict(size=9),
        marker=dict(line=dict(width=1, color="DarkSlateGrey")),
    )
    fig_competition.update_layout(
        xaxis_title="Number of Games (Competition Level)",
        yaxis_title="Average Profit ($)",
    )
    st.plotly_chart(fig_competition, **STRETCH_WIDTH)
