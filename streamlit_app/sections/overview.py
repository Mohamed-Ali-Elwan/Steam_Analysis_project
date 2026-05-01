import pandas as pd
import plotly.express as px
import streamlit as st

from data_processing import get_dataframe_summary
from ui import STRETCH_WIDTH


def render_overview(df):
    st.title("Steam Games Overview & Summary")
    st.markdown("---")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Games", f"{len(df):,}")
    with col2:
        avg_price = df["price"].mean() if "price" in df.columns else 0
        st.metric("Avg Price", f"${avg_price:.2f}")
    with col3:
        avg_reviews = df["total_reviews"].mean() if "total_reviews" in df.columns else 0
        st.metric("Avg Reviews", f"{avg_reviews:,.0f}")
    with col4:
        avg_positive = (
            df["total_positive"].mean() if "total_positive" in df.columns else 0
        )
        st.metric("Avg Positive", f"{avg_positive:,.0f}")

    st.markdown("---")

    with st.expander("Dataset Information"):
        st.dataframe(get_dataframe_summary(df), **STRETCH_WIDTH)
        st.dataframe(df.head(10), **STRETCH_WIDTH)

    st.markdown("---")

    st.subheader("Price Distribution")
    if "price" in df.columns:
        fig_price = px.histogram(
            df,
            x="price",
            nbins=50,
            title="Distribution of Game Prices",
            color_discrete_sequence=px.colors.sequential.Blues,
        )
        fig_price.update_layout(xaxis_title="Price ($)", yaxis_title="Count")
        st.plotly_chart(fig_price, **STRETCH_WIDTH)

    st.subheader("Review Distribution")
    col1, col2 = st.columns(2)
    with col1:
        if "total_reviews" in df.columns:
            fig_reviews = px.histogram(
                df,
                x="total_reviews",
                nbins=50,
                title="Distribution of Total Reviews",
                color_discrete_sequence=px.colors.sequential.Plasma,
            )
            fig_reviews.update_layout(xaxis_title="Total Reviews", yaxis_title="Count")
            st.plotly_chart(fig_reviews, **STRETCH_WIDTH)

    with col2:
        if "total_positive" in df.columns:
            fig_positive = px.histogram(
                df,
                x="total_positive",
                nbins=50,
                title="Distribution of Positive Reviews",
                color_discrete_sequence=px.colors.sequential.Greens,
            )
            fig_positive.update_layout(
                xaxis_title="Positive Reviews", yaxis_title="Count"
            )
            st.plotly_chart(fig_positive, **STRETCH_WIDTH)
