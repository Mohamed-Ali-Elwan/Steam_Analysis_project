from inspect import signature

import streamlit as st

PAGE_OPTIONS = [
    "Game Listing",
    "Analytics",
]


def get_stretch_width_kwargs():
    """Prefer Streamlit's new width API while supporting older installs."""
    if "width" in signature(st.plotly_chart).parameters:
        return {"width": "stretch"}
    return {"use_container_width": True}


STRETCH_WIDTH = get_stretch_width_kwargs()


def apply_custom_css():
    st.markdown(
        """
        <style>
        .block-container {
            animation: pageFadeIn 180ms ease-out;
            max-width: 100% !important;
            overflow: visible;
            padding-left: clamp(1rem, 2vw, 2.5rem);
            padding-right: clamp(1rem, 2vw, 2.5rem);
        }

        [data-testid="stElementContainer"],
        [data-testid="stVerticalBlock"],
        [data-testid="stHorizontalBlock"],
        [data-testid="stPlotlyChart"] {
            overflow: visible;
        }

        [data-testid="stPlotlyChart"] > div {
            width: 100% !important;
        }

        @keyframes pageFadeIn {
            from {
                opacity: 0;
                transform: translateY(6px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        h1, h2, h3 {
            color: #1f77b4;
        }

        [data-testid="stSidebar"] {
            background-color: #262730;
        }

        [data-testid="stMetric"] {
            background-color: transparent;
            border: 0;
            padding: 0;
            border-radius: 0;
        }

        [data-testid="stMetricLabel"] {
            color: #c9d1d9;
        }

        [data-testid="stMetricValue"] {
            color: #fafafa;
        }
        </style>
    """,
        unsafe_allow_html=True,
    )


def render_sidebar():
    with st.sidebar:
        st.title("Steam Games Analytics")
        page = st.radio("Go to section:", PAGE_OPTIONS, index=0)

    return page


def show_data_load_message():
    st.warning("Could not load the games data from MongoDB.")
    st.markdown("""
    ### Check:
    1. Atlas Network Access allows this machine's current public IP address.
    2. `.streamlit/secrets.toml` or `~/.streamlit/secrets.toml` contains a valid MongoDB URI.
    3. Collection names are configured if auto-detection cannot find them.
    """)
