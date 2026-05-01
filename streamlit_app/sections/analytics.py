import streamlit as st

from sections.dlc_impact import render_dlc_impact
from sections.genre_analysis import render_genre_analysis
from sections.language_categories import render_language_categories
from sections.ml_model_trainer import render_ml_model_trainer
from sections.overview import render_overview
from sections.profit_analysis import render_profit_analysis
from sections.release_trends import render_release_trends
from sections.tag_analysis import render_tag_analysis


ANALYTICS_OPTIONS = [
    "Overview & Summary",
    "Tag Analysis",
    "Profit Analysis",
    "Genre Analysis",
    "Release Trends",
    "Language & Categories",
    "DLC Impact",
    "ML Model Trainer",
]


def render_analytics(df, merged_data, reviews_data=None, dlcs_data=None):
    st.caption("Analytics page")
    selected_analysis = st.selectbox("Choose analytics type", ANALYTICS_OPTIONS)
    st.markdown("---")

    page_renderers = {
        "Overview & Summary": lambda: render_overview(df),
        "Tag Analysis": lambda: render_tag_analysis(
            df, merged_data, reviews_data, dlcs_data
        ),
        "Profit Analysis": lambda: render_profit_analysis(df, merged_data),
        "Genre Analysis": lambda: render_genre_analysis(df),
        "Release Trends": lambda: render_release_trends(df),
        "Language & Categories": lambda: render_language_categories(df, merged_data),
        "DLC Impact": lambda: render_dlc_impact(df),
        "ML Model Trainer": lambda: render_ml_model_trainer(merged_data),
    }
    page_renderers[selected_analysis]()
