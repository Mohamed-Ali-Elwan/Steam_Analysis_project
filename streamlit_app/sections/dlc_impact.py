import plotly.express as px
import streamlit as st

from sections.analytics_utils import prepare_profit_frame
from ui import STRETCH_WIDTH


def render_dlc_impact(df):
    st.title("DLC Impact Analysis")
    st.markdown("---")

    analysis_df = prepare_profit_frame(df)
    if analysis_df.empty or "dlc_count" not in analysis_df.columns:
        st.warning("DLC data is not available for this analysis.")
        return

    games_with_dlcs = analysis_df[analysis_df["dlc_count"].fillna(0) > 0].copy()
    if games_with_dlcs.empty:
        st.info("No games with DLC counts are available.")
        return

    metrics = st.columns(4)
    metrics[0].metric("Games with DLC", f"{len(games_with_dlcs):,}")
    metrics[1].metric("Avg DLC Count", f"{games_with_dlcs['dlc_count'].mean():.1f}")
    avg_dlc_price = (
        games_with_dlcs["total_dlc_price"].fillna(0).mean()
        if "total_dlc_price" in games_with_dlcs.columns
        else 0
    )
    metrics[2].metric(
        "Avg DLC Price",
        f"${avg_dlc_price:.2f}",
    )
    if "Profit" in games_with_dlcs.columns:
        metrics[3].metric(
            "Avg Estimated Profit",
            f"${games_with_dlcs['Profit'].fillna(0).mean():,.0f}",
        )

    fig_reviews = px.scatter(
        games_with_dlcs,
        x="dlc_count",
        y="total_positive",
        title="Number of DLCs vs. Total Positive Reviews",
        labels={
            "dlc_count": "Number of DLCs",
            "total_positive": "Total Positive Reviews",
        },
        hover_name="name",
        color="price",
        size="price",
        color_continuous_scale="Viridis",
    )
    fig_reviews.update_xaxes(type="log")
    fig_reviews.update_yaxes(type="log")
    st.plotly_chart(fig_reviews, **STRETCH_WIDTH)

    if "Profit" in games_with_dlcs.columns:
        fig_profit = px.scatter(
            games_with_dlcs,
            x="dlc_count",
            y="Profit",
            title="Number of DLCs vs. Estimated Profit",
            labels={"dlc_count": "Number of DLCs", "Profit": "Estimated Profit ($)"},
            hover_name="name",
            color="positive_ratio",
            size="total_dlc_price",
            color_continuous_scale="RdYlGn",
        )
        fig_profit.update_xaxes(type="log")
        st.plotly_chart(fig_profit, **STRETCH_WIDTH)

    summary_aggs = {
        "avg_positive": ("total_positive", "mean"),
        "total_positive": ("total_positive", "sum"),
        "avg_negative": ("total_negative", "mean"),
        "avg_price": ("price", "mean"),
        "game_count": ("app_id", "count"),
    }
    if "Profit" in games_with_dlcs.columns:
        summary_aggs["avg_profit"] = ("Profit", "mean")

    summary = (
        games_with_dlcs.groupby("dlc_count", dropna=False)
        .agg(**summary_aggs)
        .reset_index()
        .sort_values("dlc_count")
    )
    formatters = {
        "avg_positive": "{:,.0f}",
        "total_positive": "{:,.0f}",
        "avg_negative": "{:,.0f}",
        "avg_price": "${:.2f}",
    }
    if "avg_profit" in summary.columns:
        formatters["avg_profit"] = "${:,.0f}"
    st.dataframe(
        summary.style.format(formatters),
        **STRETCH_WIDTH,
    )
