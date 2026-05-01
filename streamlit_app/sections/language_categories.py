from collections import Counter

import pandas as pd
import plotly.express as px
import streamlit as st

from sections.analytics_utils import explode_multivalue_frame
from ui import STRETCH_WIDTH


def render_language_categories(df, merged_data):
    st.title("Languages & Features Analysis")
    st.markdown("---")

    language_tab, feature_tab = st.tabs(["Languages", "Features"])

    with language_tab:
        _render_language_analysis(df)

    with feature_tab:
        _render_feature_analysis(df)


def _render_language_analysis(df):
    if df is None or df.empty or "supported_languages" not in df.columns:
        st.info("Supported languages data is not available.")
        return

    all_languages = []
    for language_string in df["supported_languages"].dropna():
        all_languages.extend(
            [language.strip() for language in str(language_string).split(",")]
        )

    language_counts = Counter(all_languages)
    top_languages = pd.DataFrame(
        {
            "language": list(dict(language_counts.most_common(10)).keys()),
            "count": list(dict(language_counts.most_common(10)).values()),
        }
    )

    fig_languages = px.bar(
        top_languages,
        x="count",
        y="language",
        orientation="h",
        title="Top 10 Most Used Languages",
        labels={"count": "Number of Games", "language": "Language"},
        color="count",
        color_continuous_scale="Viridis",
    )
    fig_languages.update_layout(yaxis={"categoryorder": "total ascending"})
    fig_languages.update_traces(texttemplate="%{x}", textposition="outside")
    st.plotly_chart(fig_languages, **STRETCH_WIDTH)


def _render_feature_analysis(df):
    feature_column = None
    for candidate in ["features", "categories"]:
        if candidate in df.columns:
            feature_column = candidate
            break

    if feature_column is None:
        st.info("Features/categories data is not available.")
        return

    exploded_features = explode_multivalue_frame(df, feature_column)
    if exploded_features.empty:
        st.info("No feature rows are available.")
        return

    feature_counts = (
        exploded_features[feature_column]
        .value_counts()
        .reset_index()
    )
    feature_counts.columns = ["feature", "count"]

    col1, col2 = st.columns(2)
    with col1:
        fig_features = px.bar(
            feature_counts.head(10),
            x="feature",
            y="count",
            title="Top 10 Game Features",
            labels={"feature": "Feature", "count": "Number of Games"},
            color="count",
            color_continuous_scale="Reds",
        )
        fig_features.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_features, **STRETCH_WIDTH)

    with col2:
        fig_treemap = px.treemap(
            feature_counts.head(20),
            path=[px.Constant("All Features"), "feature"],
            values="count",
            title="Game Features Treemap",
            color="count",
            color_continuous_scale="Blues",
        )
        fig_treemap.update_layout(margin=dict(t=50, l=25, r=25, b=25))
        st.plotly_chart(fig_treemap, **STRETCH_WIDTH)
