import os
import re
from urllib.error import URLError
from urllib.request import urlopen

import pandas as pd
import streamlit as st
from pymongo import MongoClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError
from sklearn.preprocessing import LabelEncoder

DEFAULT_COLLECTIONS = {
    "games": ("cleaned_games_data", "games", "games_data", "cleaned_games"),
    "dlcs": ("cleaned_DLCS_data", "cleaned_dlcs_data", "dlcs", "dlc"),
    "reviews": ("reviews_data_cleaned", "reviews", "reviews_data", "cleaned_reviews"),
    "game_extra": (
        "Game_extra_Data",
        "game_extra_data",
        "games_extra_data",
        "extra_games_data",
    ),
}


def split_delimited_values(value):
    if value is None:
        return []
    if not isinstance(value, (list, tuple, set)) and pd.isna(value):
        return []
    if isinstance(value, (list, tuple, set)):
        raw_values = value
    else:
        raw_values = re.split(r"[;,]", str(value))

    cleaned_values = []
    for item in raw_values:
        text = str(item).strip().strip("[]'\"")
        if text and text.casefold() not in {"nan", "none"}:
            cleaned_values.append(text)
    return cleaned_values


def get_mongodb_config():
    """Read MongoDB settings from env vars first, then Streamlit secrets."""
    secrets = {}
    try:
        secrets = st.secrets.get("mongodb", {})
    except Exception:
        secrets = {}

    return {
        "uri": os.getenv("MONGODB_URI") or secrets.get("uri", ""),
        "database": os.getenv("MONGODB_DATABASE") or secrets.get("database", ""),
        "games_collection": os.getenv("MONGODB_GAMES_COLLECTION")
        or secrets.get("games_collection", ""),
        "dlcs_collection": os.getenv("MONGODB_DLCS_COLLECTION")
        or secrets.get("dlcs_collection", ""),
        "reviews_collection": os.getenv("MONGODB_REVIEWS_COLLECTION")
        or secrets.get("reviews_collection", ""),
        "game_extra_collection": os.getenv("MONGODB_GAME_EXTRA_COLLECTION")
        or secrets.get("game_extra_collection", ""),
    }


def normalize_name(name):
    return name.lower().replace("-", "_")


def resolve_database_name(client, configured_database):
    if configured_database:
        return configured_database

    database_names = [
        name
        for name in client.list_database_names()
        if name not in {"admin", "config", "local"}
    ]
    return database_names[0] if database_names else None


def resolve_collection_name(db, configured_collection, candidates):
    if configured_collection:
        return configured_collection

    collection_names = db.list_collection_names()
    collection_lookup = {normalize_name(name): name for name in collection_names}

    for candidate in candidates:
        match = collection_lookup.get(normalize_name(candidate))
        if match:
            return match

    for collection_name in collection_names:
        normalized = normalize_name(collection_name)
        if any(normalize_name(candidate) in normalized for candidate in candidates):
            return collection_name

    return None


def collection_to_dataframe(db, collection_name):
    if not collection_name:
        return None

    documents = list(db[collection_name].find({}, {"_id": 0}))
    return pd.DataFrame(documents)


def get_public_ip():
    try:
        with urlopen("https://api.ipify.org", timeout=3) as response:
            return response.read().decode("utf-8").strip()
    except (OSError, URLError):
        return None


@st.cache_data(show_spinner="Loading data from MongoDB...", ttl=600)
def load_mongodb_data(
    uri,
    database,
    games_collection,
    dlcs_collection,
    reviews_collection,
    game_extra_collection,
):
    if not uri:
        raise ValueError(
            "MongoDB URI is missing. Set MONGODB_URI, .streamlit/secrets.toml, "
            "or ~/.streamlit/secrets.toml."
        )

    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    client.admin.command("ping")

    database_name = resolve_database_name(client, database)
    if database_name is None:
        raise ValueError("No user databases were found in this MongoDB cluster.")

    db = client[database_name]
    resolved_games_collection = resolve_collection_name(
        db, games_collection, DEFAULT_COLLECTIONS["games"]
    )
    resolved_dlcs_collection = resolve_collection_name(
        db, dlcs_collection, DEFAULT_COLLECTIONS["dlcs"]
    )
    resolved_reviews_collection = resolve_collection_name(
        db, reviews_collection, DEFAULT_COLLECTIONS["reviews"]
    )
    resolved_game_extra_collection = resolve_collection_name(
        db, game_extra_collection, DEFAULT_COLLECTIONS["game_extra"]
    )

    games_data = collection_to_dataframe(db, resolved_games_collection)
    dlcs_data = collection_to_dataframe(db, resolved_dlcs_collection)
    reviews_data = collection_to_dataframe(db, resolved_reviews_collection)
    game_extra_data = collection_to_dataframe(db, resolved_game_extra_collection)

    if games_data is None or games_data.empty:
        raise ValueError(
            "Games collection was not found or is empty. Configure mongodb.games_collection."
        )
    if dlcs_data is not None and dlcs_data.empty:
        dlcs_data = None
    if reviews_data is not None and reviews_data.empty:
        reviews_data = None
    if game_extra_data is not None and game_extra_data.empty:
        game_extra_data = None

    return {
        "database": database_name,
        "collections": {
            "games": resolved_games_collection,
            "dlcs": resolved_dlcs_collection,
            "reviews": resolved_reviews_collection,
            "game_extra": resolved_game_extra_collection,
        },
        "games_data": games_data,
        "dlcs_data": dlcs_data,
        "reviews_data": reviews_data,
        "game_extra_data": game_extra_data,
    }


def load_dashboard_data():
    config = get_mongodb_config()

    try:
        result = load_mongodb_data(
            config["uri"],
            config["database"],
            config["games_collection"],
            config["dlcs_collection"],
            config["reviews_collection"],
            config["game_extra_collection"],
        )
    except ServerSelectionTimeoutError as e:
        public_ip = get_public_ip()
        st.error(
            "Could not connect to MongoDB Atlas. Atlas is rejecting the TLS handshake "
            "before authentication."
        )
        if public_ip:
            st.warning(
                "Add this machine's current IP to Atlas Network Access: "
                f"`{public_ip}/32`"
            )
        st.markdown(
            """
            In MongoDB Atlas, open **Security > Network Access > Add IP Address**,
            add the IP above, wait for the rule to become active, then click
            **Refresh MongoDB data** in the sidebar.
            """
        )
        with st.expander("Connection error details"):
            st.code(str(e))
        return None, None, None, None
    except (PyMongoError, ValueError) as e:
        st.error(f"Could not load MongoDB data: {e}")
        return None, None, None, None

    games_data = result["games_data"]
    dlcs_data = result["dlcs_data"]
    reviews_data = result["reviews_data"]
    game_extra_data = result["game_extra_data"]

    return games_data, dlcs_data, reviews_data, game_extra_data


def get_dataframe_summary(dataframe):
    """Return display-friendly schema details without writing to stdout."""
    return pd.DataFrame(
        {
            "Column": dataframe.columns,
            "Non-Null Count": dataframe.notna().sum().values,
            "Dtype": dataframe.dtypes.astype(str).values,
        }
    )


def preprocess_data(games_data, dlcs_data, reviews_data, game_extra_data=None):
    """Preprocess all datasets."""
    if games_data is None:
        return None, None

    cols_to_drop = [
        "total_english_reviews",
    ]
    games_clean = games_data.drop(
        [col for col in cols_to_drop if col in games_data.columns], axis=1
    ).copy()

    if game_extra_data is not None and {"app_id", "user_defined_tags"}.issubset(
        game_extra_data.columns
    ):
        user_tags = (
            game_extra_data[["app_id", "user_defined_tags"]]
            .drop_duplicates("app_id")
            .rename(columns={"user_defined_tags": "extra_user_defined_tags"})
        )
        games_clean = games_clean.merge(user_tags, on="app_id", how="left")
        if "user_defined_tags" in games_clean.columns:
            games_clean["user_defined_tags"] = games_clean[
                "user_defined_tags"
            ].combine_first(games_clean["extra_user_defined_tags"])
            games_clean = games_clean.drop(columns=["extra_user_defined_tags"])
        else:
            games_clean = games_clean.rename(
                columns={"extra_user_defined_tags": "user_defined_tags"}
            )
    elif game_extra_data is not None:
        st.warning(
            "Game_extra_Data collection was loaded but is missing app_id or user_defined_tags."
        )

    if "release_date" in games_clean.columns:
        games_clean["release_date"] = pd.to_datetime(
            games_clean["release_date"], format="%b %d, %Y", errors="coerce"
        )
        games_clean["year"] = games_clean["release_date"].dt.year

    review_cols = {"total_positive", "total_negative", "total_reviews"}
    if review_cols.issubset(games_clean.columns):
        total_reviews = games_clean["total_reviews"].where(
            games_clean["total_reviews"] != 0
        )
        games_clean["positive_pct"] = (
            games_clean["total_positive"].div(total_reviews).mul(100)
        )
        games_clean["negative_pct"] = (
            games_clean["total_negative"].div(total_reviews).mul(100)
        )

    if "tag" in games_clean.columns:
        games_clean["tag"] = games_clean["tag"].fillna("").astype(str)
        games_clean["primary_tag"] = (
            games_clean["tag"].apply(split_delimited_values).str[0]
        )
        games_clean.loc[games_clean["primary_tag"] == "", "primary_tag"] = None

    if "genres" in games_clean.columns:
        games_clean["genres"] = games_clean["genres"].apply(split_delimited_values)

    if "categories" in games_clean.columns:
        games_clean["categories"] = games_clean["categories"].apply(split_delimited_values)

    if "features" in games_clean.columns:
        games_clean["features"] = games_clean["features"].apply(split_delimited_values)
        if "categories" not in games_clean.columns:
            games_clean["categories"] = games_clean["features"].apply(list)

    if dlcs_data is not None and {"parent_app_id", "app_id", "price"}.issubset(
        dlcs_data.columns
    ):
        dlcs_agg = (
            dlcs_data.groupby("parent_app_id")
            .agg(dlc_count=("app_id", "count"), total_dlc_price=("price", "sum"))
            .reset_index()
        )
        games_clean = games_clean.merge(
            dlcs_agg, left_on="app_id", right_on="parent_app_id", how="left"
        )
    elif dlcs_data is not None:
        st.warning(
            "DLC collection was loaded but is missing parent_app_id, app_id, or price."
        )

    merged_data = None
    if reviews_data is not None and "parent_app_id" in reviews_data.columns:
        reviews_clean = reviews_data.drop(
            ["recommendationid", "review_text", "received_for_free"],
            axis=1,
            errors="ignore",
        ).copy()

        enc = LabelEncoder()
        for col in [
            "recommendation",
            "review_score",
            "steam_purchase",
            "written_during_early_access",
        ]:
            if col in reviews_clean.columns:
                reviews_clean[col] = enc.fit_transform(reviews_clean[col].astype(str))

        merged_data = reviews_clean.merge(
            games_clean,
            left_on="parent_app_id",
            right_on="app_id",
            how="left",
            suffixes=("_review", "_game"),
        )

        if (
            "parent_app_id" in merged_data.columns
            and "steam_purchase" in merged_data.columns
        ):
            purchased_data = (
                reviews_clean.groupby("parent_app_id")["steam_purchase"]
                .sum()
                .reset_index()
            )
            purchased_data.columns = ["parent_app_id", "total_steam_purchases"]
            merged_data = merged_data.merge(purchased_data, on="parent_app_id", how="left")

            games_clean = games_clean.merge(
                purchased_data.rename(
                    columns={"parent_app_id": "purchase_parent_app_id"}
                ),
                left_on="app_id",
                right_on="purchase_parent_app_id",
                how="left",
            )
            games_clean = games_clean.drop(
                columns=["purchase_parent_app_id"], errors="ignore"
            )
    elif reviews_data is not None:
        st.warning("Reviews collection was loaded but is missing parent_app_id.")

    if "total_reviews" in games_clean.columns:
        games_clean["total_steam_purchases"] = pd.to_numeric(
            games_clean["total_reviews"], errors="coerce"
        ).fillna(0)
    elif "total_steam_purchases" in games_clean.columns:
        games_clean["total_steam_purchases"] = pd.to_numeric(
            games_clean["total_steam_purchases"], errors="coerce"
        ).fillna(0)

    if review_cols.issubset(games_clean.columns):
        total_reviews = games_clean["total_reviews"].where(
            games_clean["total_reviews"] != 0
        )
        games_clean["positive_ratio"] = games_clean["total_positive"].div(total_reviews)

    if {"price", "total_steam_purchases"}.issubset(games_clean.columns):
        games_clean["Profit"] = (
            pd.to_numeric(games_clean["price"], errors="coerce").fillna(0)
            * games_clean["total_steam_purchases"]
            * 0.4
        )

    return games_clean, merged_data
