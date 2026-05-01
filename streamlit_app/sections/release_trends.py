import plotly.express as px
import streamlit as st

from ui import STRETCH_WIDTH


def render_release_trends(df):
    st.title("Release Trends Analysis")
    st.markdown("---")

    if "year" not in df.columns:
        st.warning("Release date data not available. Cannot compute release trends.")
        return

    games_per_year = df.groupby("year").size().reset_index(name="count")
    games_per_year = games_per_year.sort_values("year")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Games Released Per Year")
        fig_year = px.line(
            games_per_year,
            x="year",
            y="count",
            title="Number of Games Released Each Year",
            markers=True,
        )
        fig_year.update_layout(
            xaxis=dict(tickmode="linear"),
            yaxis_title="Number of Games",
            hovermode="x unified",
        )
        st.plotly_chart(fig_year, **STRETCH_WIDTH)

    with col2:
        st.subheader("Average Price Per Year")
        avg_price_year = df.groupby("year")["price"].mean().reset_index()
        avg_price_year.columns = ["year", "avg_price"]

        fig_price_year = px.line(
            avg_price_year,
            x="year",
            y="avg_price",
            title="Average Game Price Over Years",
            markers=True,
        )
        fig_price_year.update_layout(yaxis_title="Average Price ($)")
        st.plotly_chart(fig_price_year, **STRETCH_WIDTH)

    st.markdown("---")

    if "total_reviews" in df.columns:
        st.subheader("Reviews Over Time")
        reviews_per_year = df.groupby("year")["total_reviews"].sum().reset_index()

        fig_reviews_year = px.bar(
            reviews_per_year,
            x="year",
            y="total_reviews",
            title="Total Reviews Per Year",
            color="total_reviews",
            color_continuous_scale="Viridis",
        )
        fig_reviews_year.update_layout(xaxis_tickangle=45)
        st.plotly_chart(fig_reviews_year, **STRETCH_WIDTH)
