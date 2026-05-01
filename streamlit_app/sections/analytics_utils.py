import re

import pandas as pd

REVENUE_SHARE = 0.4


def has_columns(dataframe, columns):
    return set(columns).issubset(getattr(dataframe, "columns", []))


def split_multi_value(value, lowercase=False):
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
        if lowercase:
            text = text.lower()
        if text and text.casefold() not in {"nan", "none"}:
            cleaned_values.append(text)
    return cleaned_values


def explode_multivalue_frame(dataframe, column, lowercase=False):
    if dataframe is None or dataframe.empty or column not in dataframe.columns:
        return pd.DataFrame(columns=getattr(dataframe, "columns", []))

    exploded = dataframe.copy()
    exploded[column] = exploded[column].apply(
        lambda value: split_multi_value(value, lowercase=lowercase)
    )
    exploded = exploded.explode(column)
    exploded = exploded[exploded[column].notna()]
    exploded[column] = exploded[column].astype(str).str.strip()
    return exploded[exploded[column] != ""]


def prepare_profit_frame(dataframe):
    if dataframe is None or dataframe.empty:
        return pd.DataFrame()

    profit_frame = dataframe.copy()
    for column in [
        "price",
        "total_reviews",
        "total_positive",
        "total_negative",
        "total_steam_purchases",
        "Profit",
        "positive_pct",
        "negative_pct",
        "positive_ratio",
        "dlc_count",
        "total_dlc_price",
    ]:
        if column in profit_frame.columns:
            profit_frame[column] = pd.to_numeric(
                profit_frame[column], errors="coerce"
            )

    if "total_reviews" in profit_frame.columns:
        profit_frame["total_steam_purchases"] = profit_frame["total_reviews"].fillna(0)

    if "primary_tag" not in profit_frame.columns and "tag" in profit_frame.columns:
        def get_primary_tag(value):
            tags = split_multi_value(value)
            return tags[0] if tags else None

        profit_frame["primary_tag"] = profit_frame["tag"].apply(get_primary_tag)

    if {"total_positive", "total_reviews"}.issubset(profit_frame.columns):
        total_reviews = profit_frame["total_reviews"].where(
            profit_frame["total_reviews"] != 0
        )
        if "positive_ratio" not in profit_frame.columns:
            profit_frame["positive_ratio"] = profit_frame["total_positive"].div(
                total_reviews
            )
        if "positive_pct" not in profit_frame.columns:
            profit_frame["positive_pct"] = profit_frame["positive_ratio"] * 100
        if (
            "negative_pct" not in profit_frame.columns
            and "total_negative" in profit_frame.columns
        ):
            profit_frame["negative_pct"] = (
                profit_frame["total_negative"].div(total_reviews).mul(100)
            )

    if {"price", "total_steam_purchases"}.issubset(profit_frame.columns):
        profit_frame["Profit"] = (
            profit_frame["price"].fillna(0)
            * profit_frame["total_steam_purchases"].fillna(0)
            * REVENUE_SHARE
        )

    return profit_frame


def build_tag_profit_table(dataframe):
    exploded_tags = explode_multivalue_frame(prepare_profit_frame(dataframe), "tag")
    if exploded_tags.empty:
        return pd.DataFrame()

    tag_df = (
        exploded_tags.groupby("tag", dropna=False)
        .agg(
            positive_pct=("positive_pct", "mean"),
            negative_pct=("negative_pct", "mean"),
            avg_price=("price", "mean"),
            total_reviews=("total_reviews", "sum"),
            game_count=("tag", "size"),
        )
        .reset_index()
        .rename(
            columns={
                "positive_pct": "positive%",
                "negative_pct": "negative%",
                "total_reviews": "Total Reviews",
                "game_count": "Game Count",
            }
        )
    )

    tag_df["Average Profit (M)"] = (
        tag_df["avg_price"].fillna(0) * tag_df["Total Reviews"].fillna(0) * REVENUE_SHARE
    ) / 1_000_000
    tag_df["Average Profit per game (M)"] = tag_df["Average Profit (M)"].div(
        tag_df["Game Count"].replace(0, pd.NA)
    )

    metric_columns = [
        "positive%",
        "negative%",
        "avg_price",
        "Average Profit (M)",
        "Average Profit per game (M)",
    ]
    tag_df[metric_columns] = tag_df[metric_columns].round(2)
    tag_df["Total Reviews"] = tag_df["Total Reviews"].fillna(0)
    tag_df["Game Count"] = tag_df["Game Count"].fillna(0).astype(int)

    return tag_df.sort_values("Total Reviews", ascending=False).reset_index(drop=True)


def build_tag_competition_metrics(dataframe):
    profit_frame = prepare_profit_frame(dataframe)
    required_columns = [
        "primary_tag",
        "Profit",
        "total_steam_purchases",
        "app_id",
        "positive_ratio",
    ]
    if profit_frame.empty or not has_columns(profit_frame, required_columns):
        return pd.DataFrame()

    metrics = (
        profit_frame.dropna(subset=["primary_tag"])
        .groupby("primary_tag", dropna=False)
        .agg(
            avg_profit=("Profit", "mean"),
            avg_purchases=("total_steam_purchases", "mean"),
            game_count=("app_id", "count"),
            avg_positive_ratio=("positive_ratio", "mean"),
        )
        .reset_index()
    )
    return metrics.sort_values("avg_profit", ascending=False).reset_index(drop=True)


def build_genre_metrics(dataframe):
    exploded_genres = explode_multivalue_frame(
        prepare_profit_frame(dataframe), "genres", lowercase=True
    )
    required_columns = [
        "genres",
        "Profit",
        "total_steam_purchases",
        "app_id",
        "positive_ratio",
    ]
    if exploded_genres.empty or not has_columns(exploded_genres, required_columns):
        return pd.DataFrame()

    metrics = (
        exploded_genres.groupby("genres", dropna=False)
        .agg(
            avg_profit=("Profit", "mean"),
            avg_purchases=("total_steam_purchases", "mean"),
            game_count=("app_id", "count"),
            avg_positive_ratio=("positive_ratio", "mean"),
        )
        .reset_index()
    )
    return metrics.sort_values("avg_profit", ascending=False).reset_index(drop=True)


def build_top_games_per_tag(dataframe, n=3):
    profit_frame = prepare_profit_frame(dataframe)
    if profit_frame.empty or not has_columns(profit_frame, ["primary_tag", "Profit"]):
        return pd.DataFrame()

    filtered = profit_frame.dropna(subset=["primary_tag"]).copy()
    filtered = filtered[filtered["Profit"].fillna(0) > 0]
    if filtered.empty:
        return pd.DataFrame()

    top_groups = []
    for _, group in filtered.groupby("primary_tag", dropna=False):
        top_groups.append(group.nlargest(n, "Profit"))

    if not top_groups:
        return pd.DataFrame()

    return pd.concat(top_groups, ignore_index=True)


def add_quadrant_guides(fig, dataframe, x_column, y_column, median_x, median_y):
    if dataframe is None or dataframe.empty:
        return fig
    if not has_columns(dataframe, [x_column, y_column]):
        return fig

    x_values = pd.to_numeric(dataframe[x_column], errors="coerce").dropna()
    y_values = pd.to_numeric(dataframe[y_column], errors="coerce").dropna()
    if x_values.empty or y_values.empty or pd.isna(median_x) or pd.isna(median_y):
        return fig

    max_x = max(float(x_values.max()), float(median_x), 1)
    max_y = max(float(y_values.max()), float(median_y), 1)
    x_limit = max_x * 1.1
    y_limit = max_y * 1.1

    fig.add_shape(
        type="line",
        line=dict(color="#9ca3af", dash="dash", width=1),
        x0=float(median_x),
        y0=0,
        x1=float(median_x),
        y1=y_limit,
    )
    fig.add_shape(
        type="line",
        line=dict(color="#9ca3af", dash="dash", width=1),
        x0=0,
        y0=float(median_y),
        x1=x_limit,
        y1=float(median_y),
    )

    annotation_font = dict(size=14)
    fig.add_annotation(
        x=float(median_x) / 2,
        y=max_y * 0.9,
        text="Low Competition<br>High Profit",
        showarrow=False,
        font=annotation_font,
    )
    fig.add_annotation(
        x=max_x * 0.75,
        y=max_y * 0.9,
        text="High Competition<br>High Profit",
        showarrow=False,
        font=annotation_font,
    )
    fig.add_annotation(
        x=float(median_x) / 2,
        y=float(median_y) / 2,
        text="Low Competition<br>Low Profit",
        showarrow=False,
        font=annotation_font,
    )
    fig.add_annotation(
        x=max_x * 0.75,
        y=float(median_y) / 2,
        text="High Competition<br>Low Profit",
        showarrow=False,
        font=annotation_font,
    )
    fig.update_xaxes(range=[0, x_limit])
    fig.update_yaxes(range=[0, y_limit])
    return fig


def filter_profit_scope(tag_df, scope):
    if tag_df is None or tag_df.empty:
        return pd.DataFrame()
    if scope == "AAA":
        return tag_df[tag_df["tag"].str.contains("AAA_", na=False)].copy()
    if scope == "Indie":
        return tag_df[tag_df["tag"].str.contains("Indie_", na=False)].copy()
    return tag_df.copy()
