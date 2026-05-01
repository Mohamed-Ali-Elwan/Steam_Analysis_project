import math
import re
from html import escape
from urllib.parse import quote

import pandas as pd
import streamlit as st

SORT_OPTIONS = {
    "Most reviewed": ("total_reviews", False),
    "Highest positive score": ("positive_pct", False),
    "Newest releases": ("release_date", False),
    "Oldest releases": ("release_date", True),
    "Price: low to high": ("price", True),
    "Price: high to low": ("price", False),
    "Name: A to Z": ("name", True),
}

DETAIL_QUERY_PARAM = "game"
DLC_DETAIL_QUERY_PARAM = "dlc"


def render_game_listing(df, reviews_data=None, dlcs_data=None):
    st.title("Steam Game Storefront")
    st.markdown(
        "Browse every game as a product card, then narrow the catalog with filters."
    )

    if df is None or df.empty:
        st.info("No games are available to display.")
        return

    _inject_listing_css()

    games = _prepare_listing_dataframe(df)
    selected_dlc_id = _get_selected_dlc_id()
    if selected_dlc_id:
        selected_dlc = _find_dlc_by_id(dlcs_data, selected_dlc_id)
        if selected_dlc is None:
            st.warning("That DLC could not be found.")
            st.button("Back to game listing", on_click=_clear_selected_dlc)
            return

        _render_dlc_details(selected_dlc, games, reviews_data)
        return

    selected_game_id = _get_selected_game_id()
    if selected_game_id:
        selected_game = _find_game_by_listing_id(games, selected_game_id)
        if selected_game is None:
            st.warning("That game could not be found.")
            st.button("Back to game listing", on_click=_clear_selected_game)
            return

        _render_game_details(selected_game, reviews_data, dlcs_data)
        return

    filters = _render_filters(games)
    filtered_games = _filter_games(games, filters)
    filtered_games = _sort_games(filtered_games, filters["sort_by"])

    _render_listing_summary(games, filtered_games)

    if filtered_games.empty:
        st.warning("No games match the current filters.")
        return

    page_size = filters["page_size"]
    total_pages = max(1, math.ceil(len(filtered_games) / page_size))
    if total_pages == 1:
        page_number = 1
    else:
        page_number = st.slider("Page", 1, total_pages, 1)

    start = (page_number - 1) * page_size
    end = start + page_size
    page_games = filtered_games.iloc[start:end]

    st.caption(
        f"Showing {start + 1:,}-{min(end, len(filtered_games)):,} "
        f"of {len(filtered_games):,} matching games"
    )
    _render_game_cards(page_games)


def _prepare_listing_dataframe(df):
    games = df.copy()
    listing_ids = []
    for index, row in games.iterrows():
        listing_id = _normalize_listing_id(row.get("app_id"))
        listing_ids.append(listing_id or _normalize_listing_id(index))
    games["_listing_id"] = listing_ids

    if "price" in games.columns:
        games["price_numeric"] = pd.to_numeric(games["price"], errors="coerce").fillna(
            0
        )
    else:
        games["price_numeric"] = 0

    if "total_reviews" in games.columns:
        games["reviews_numeric"] = pd.to_numeric(
            games["total_reviews"], errors="coerce"
        ).fillna(0)
    else:
        games["reviews_numeric"] = 0

    if "positive_pct" in games.columns:
        games["positive_pct_numeric"] = pd.to_numeric(
            games["positive_pct"], errors="coerce"
        ).fillna(0)
    else:
        games["positive_pct_numeric"] = 0

    if "year" in games.columns:
        games["year_numeric"] = pd.to_numeric(games["year"], errors="coerce")
    elif "release_date" in games.columns:
        games["year_numeric"] = pd.to_datetime(
            games["release_date"], errors="coerce"
        ).dt.year
    else:
        games["year_numeric"] = pd.NA

    return games


def _render_filters(games):
    st.markdown("---")
    st.subheader("Filters")

    genre_options = _unique_values(games, "genres")
    tag_options = _unique_values(games, "tag")
    category_options = _unique_values(games, "categories")
    year_values = games["year_numeric"].dropna()
    max_price = float(games["price_numeric"].max())

    row1 = st.columns([2, 1, 1])
    with row1[0]:
        search = st.text_input(
            "Search",
            placeholder="Search by title, description, developer, or publisher",
        )
    with row1[1]:
        sort_by = st.selectbox("Sort by", list(SORT_OPTIONS), index=0)
    with row1[2]:
        page_size = st.selectbox("Cards per page", [12, 24, 48, 96], index=1)

    row2 = st.columns(3)
    with row2[0]:
        selected_genres = st.multiselect("Genres", genre_options)
    with row2[1]:
        selected_tags = st.multiselect("Tags", tag_options)
    with row2[2]:
        selected_categories = st.multiselect("Categories", category_options)

    row3 = st.columns(4)
    with row3[0]:
        if max_price > 0:
            price_range = st.slider(
                "Price range",
                0.0,
                max_price,
                (0.0, max_price),
                step=1.0,
                format="$%.0f",
            )
        else:
            price_range = (0.0, 0.0)
            st.caption("All listed games are free or missing price data.")
    with row3[1]:
        if year_values.empty:
            year_range = None
            st.caption("Release year data is unavailable.")
        else:
            min_year = int(year_values.min())
            max_year = int(year_values.max())
            if min_year == max_year:
                year_range = (min_year, max_year)
                st.caption(f"Release year: {min_year}")
            else:
                year_range = st.slider(
                    "Release years",
                    min_year,
                    max_year,
                    (min_year, max_year),
                )
    with row3[2]:
        min_positive = st.slider("Minimum positive score", 0, 100, 0, format="%d%%")
    with row3[3]:
        free_only = st.checkbox("Free games only")
        has_dlc_only = st.checkbox(
            "Has DLC only", disabled="dlc_count" not in games.columns
        )

    return {
        "search": search.strip(),
        "sort_by": sort_by,
        "page_size": page_size,
        "genres": selected_genres,
        "tags": selected_tags,
        "categories": selected_categories,
        "price_range": price_range,
        "year_range": year_range,
        "min_positive": min_positive,
        "free_only": free_only,
        "has_dlc_only": has_dlc_only,
    }


def _filter_games(games, filters):
    filtered = games.copy()

    if filters["search"]:
        search_columns = [
            column
            for column in [
                "name",
                "short_description",
                "description",
                "developers",
                "publishers",
            ]
            if column in filtered.columns
        ]
        if search_columns:
            query = filters["search"].casefold()
            search_text = (
                filtered[search_columns]
                .fillna("")
                .astype(str)
                .agg(" ".join, axis=1)
                .str.casefold()
            )
            filtered = filtered[search_text.str.contains(query, regex=False)]

    if filters["genres"]:
        filtered = filtered[
            filtered["genres"].apply(
                lambda value: _contains_any(value, filters["genres"])
            )
        ]

    if filters["tags"]:
        filtered = filtered[
            filtered["tag"].apply(lambda value: _contains_any(value, filters["tags"]))
        ]

    if filters["categories"]:
        filtered = filtered[
            filtered["categories"].apply(
                lambda value: _contains_any(value, filters["categories"])
            )
        ]

    price_min, price_max = filters["price_range"]
    filtered = filtered[
        filtered["price_numeric"].between(price_min, price_max, inclusive="both")
    ]

    if filters["free_only"]:
        filtered = filtered[filtered["price_numeric"] == 0]

    if filters["year_range"] is not None:
        year_min, year_max = filters["year_range"]
        filtered = filtered[
            filtered["year_numeric"].between(year_min, year_max, inclusive="both")
        ]

    if filters["min_positive"] > 0:
        filtered = filtered[filtered["positive_pct_numeric"] >= filters["min_positive"]]

    if filters["has_dlc_only"] and "dlc_count" in filtered.columns:
        dlc_count = pd.to_numeric(filtered["dlc_count"], errors="coerce").fillna(0)
        filtered = filtered[dlc_count > 0]

    return filtered


def _sort_games(games, sort_by):
    column, ascending = SORT_OPTIONS[sort_by]

    if column == "price":
        return games.sort_values("price_numeric", ascending=ascending)
    if column == "total_reviews":
        return games.sort_values("reviews_numeric", ascending=ascending)
    if column == "positive_pct":
        return games.sort_values("positive_pct_numeric", ascending=ascending)
    if column in games.columns:
        return games.sort_values(column, ascending=ascending, na_position="last")

    return games


def _render_listing_summary(games, filtered_games):
    st.markdown("---")
    total_games = len(games)
    filtered_total = len(filtered_games)
    free_games = int((filtered_games["price_numeric"] == 0).sum())
    avg_price = filtered_games["price_numeric"].mean() if filtered_total else 0
    avg_score = filtered_games["positive_pct_numeric"].mean() if filtered_total else 0

    cols = st.columns(4)
    cols[0].metric("Matching Games", f"{filtered_total:,}", f"of {total_games:,}")
    cols[1].metric("Free Games", f"{free_games:,}")
    cols[2].metric("Average Price", _format_price(avg_price))
    cols[3].metric("Average Positive", f"{avg_score:.1f}%")


def _render_game_cards(games):
    for start in range(0, len(games), 3):
        columns = st.columns(3)
        for column, (_, game) in zip(columns, games.iloc[start : start + 3].iterrows()):
            with column:
                st.markdown(_build_card_html(game), unsafe_allow_html=True)


def _build_card_html(game):
    name = _safe_text(game.get("name", "Untitled game"))
    description = _safe_text(
        _truncate_text(game.get("short_description", ""), max_length=150)
    )
    image = _safe_url(game.get("header_image", ""))
    details_url = _build_details_url(game)
    release = _format_release(game)
    price = _format_price(game.get("price_numeric", game.get("price")))
    reviews = _format_count(game.get("reviews_numeric", game.get("total_reviews")))
    positive_score = _format_percent(
        game.get("positive_pct_numeric", game.get("positive_pct"))
    )
    developer = _safe_text(_first_value(game.get("developers", "")))
    publisher = _safe_text(_first_value(game.get("publishers", "")))
    primary_genre = _safe_text(_first_value(game.get("genres", "")))
    primary_tag = _safe_text(_first_value(game.get("tag", "")))
    review_summary = _safe_text(game.get("review_summary", ""))

    image_html = (
        f'<img class="game-card__image" src="{image}" alt="{name} cover">'
        if image
        else '<div class="game-card__image game-card__image--empty">No image</div>'
    )
    genre_chip = (
        f'<span class="game-card__chip">{primary_genre}</span>' if primary_genre else ""
    )
    tag_chip = (
        f'<span class="game-card__chip">{primary_tag}</span>' if primary_tag else ""
    )
    developer_html = (
        f'<p class="game-card__maker">Developer: <strong>{developer}</strong></p>'
        if developer
        else ""
    )
    publisher_html = (
        f'<p class="game-card__maker">Publisher: <strong>{publisher}</strong></p>'
        if publisher
        else ""
    )
    review_html = (
        f'<div class="game-card__summary">{review_summary}</div>'
        if review_summary
        else ""
    )
    action_html = f'<a class="game-card__action" href="{details_url}">Open Details</a>'

    return f"""
    <article class="game-card">
        <div class="game-card__media">{image_html}</div>
        <div class="game-card__body">
            <div class="game-card__chips">{genre_chip}{tag_chip}</div>
            <h3>{name}</h3>
            <p class="game-card__description">{description or "No description available."}</p>
            {review_html}
            <div class="game-card__price-row">
                <span>Price</span>
                <strong>{price}</strong>
            </div>
            <div class="game-card__stats">
                <span><strong>{positive_score}</strong> positive</span>
                <span><strong>{reviews}</strong> reviews</span>
                <span><strong>{release}</strong></span>
            </div>
            {developer_html}
            {publisher_html}
            {action_html}
        </div>
    </article>
    """


def _render_game_details(game, reviews_data=None, dlcs_data=None):
    st.button(
        "Back to game listing",
        key="back_to_game_listing",
        on_click=_clear_selected_game,
    )

    name = _safe_text(game.get("name", "Untitled game"))
    image = _safe_url(game.get("header_image", ""))
    price = _format_price(game.get("price_numeric", game.get("price")))
    reviews = _format_count(game.get("reviews_numeric", game.get("total_reviews")))
    positive_score = _format_percent(
        game.get("positive_pct_numeric", game.get("positive_pct"))
    )
    release = _format_full_release(game)
    review_summary = _safe_text(game.get("review_summary", ""))
    app_id = _safe_text(_clean_display_value(game.get("app_id", "")))
    developer = _safe_text(_first_value(game.get("developers", "")) or "Unknown")
    publisher = _safe_text(_first_value(game.get("publishers", "")) or "Unknown")
    primary_genre = _safe_text(_first_value(game.get("genres", "")) or "Game")
    primary_tag = _safe_text(_first_value(game.get("tag", "")) or "Steam catalog")
    short_description_value = game.get("short_description", "")
    description_value = game.get("description", "")
    if not _has_display_value(description_value):
        description_value = short_description_value
    hero_description_value = (
        short_description_value
        if _has_display_value(short_description_value)
        else _truncate_text(_plain_text(description_value), max_length=220)
    )
    hero_description = _safe_text(_plain_text(hero_description_value))
    description = _safe_text(_plain_text(description_value))
    if not hero_description:
        hero_description = "Product details, reviews, tags, and external links."
    if not description:
        description = "No product description is available for this game."

    image_html = (
        f'<img class="game-detail__image" src="{image}" alt="{name} cover">'
        if image
        else '<div class="game-detail__image game-detail__image--empty">No image</div>'
    )
    review_html = (
        f'<div class="game-detail__review">{review_summary}</div>'
        if review_summary
        else ""
    )

    st.markdown(
        f"""
        <section class="game-detail">
            <div class="game-detail__visual">{image_html}</div>
            <div class="game-detail__content">
                <div class="game-detail__eyebrow">{primary_genre} / {primary_tag}</div>
                <h1>{name}</h1>
                <p>{hero_description}</p>
                {review_html}
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    metrics = st.columns(4)
    metrics[0].metric("Price", price)
    metrics[1].metric("Positive Score", positive_score)
    metrics[2].metric("Reviews", reviews)
    metrics[3].metric("Release", release)

    detail_cols = st.columns([1.5, 1])
    with detail_cols[0]:
        st.subheader("About this game")
        st.markdown(
            f"""
            <div class="game-detail__panel">
                <p>{description}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _render_detail_chips("Genres", _as_list(game.get("genres", "")))
        _render_detail_chips(
            "Tags",
            _unique_ordered_values(
                _as_list(game.get("tag", ""))
                + _as_list(game.get("user_defined_tags", ""))
            ),
        )
        _render_detail_chips("Categories", _as_list(game.get("categories", "")))

    with detail_cols[1]:
        st.subheader("Product details")
        fact_html = _build_fact_list(
            [
                ("App ID", app_id or "N/A"),
                ("Developer", developer),
                ("Publisher", publisher),
                ("Released", release),
                ("Total Positive", _format_count(game.get("total_positive"))),
                ("Total Negative", _format_count(game.get("total_negative"))),
                ("DLC Count", _format_count(game.get("dlc_count"))),
                ("DLC Value", _format_price(game.get("total_dlc_price"))),
            ]
        )
        st.markdown(
            f'<div class="game-detail__panel">{fact_html}</div>',
            unsafe_allow_html=True,
        )
        _render_dlc_list(game, dlcs_data)
        _render_external_links(game)

    _render_detail_chips(
        "Supported languages",
        _as_list(game.get("supported_languages", "")),
        max_items=16,
    )
    _render_game_reviews(game, reviews_data)


def _render_dlc_details(dlc, games, reviews_data=None):
    parent_id = _normalize_listing_id(dlc.get("parent_app_id"))
    parent_game = _find_game_by_listing_id(games, parent_id) if parent_id else None
    parent_name = (
        _safe_text(parent_game.get("name", "Parent game"))
        if parent_game is not None
        else "Parent game"
    )
    parent_listing_id = (
        _normalize_listing_id(parent_game.get("_listing_id"))
        if parent_game is not None
        else ""
    )
    st.button(
        f"Back to {parent_name}",
        key="back_to_parent_game",
        on_click=_open_parent_game_from_dlc,
        args=(parent_listing_id,),
    )

    name = _safe_text(_clean_display_value(dlc.get("name", "")) or "Untitled DLC")
    image = _safe_url(dlc.get("header_image", ""))
    price = _format_price(dlc.get("price"))
    release = _format_value_release(dlc.get("release_date"))
    app_id = _safe_text(_clean_display_value(dlc.get("app_id", "")))
    description_value = dlc.get("description", "")
    if not _has_display_value(description_value):
        description_value = dlc.get("short_description", "")
    description = _safe_text(_plain_text(description_value))
    if not description:
        description = "No DLC description is available."

    image_html = (
        f'<img class="game-detail__image" src="{image}" alt="{name} DLC cover">'
        if image
        else '<div class="game-detail__image game-detail__image--empty">DLC</div>'
    )

    st.markdown(
        f"""
        <section class="game-detail game-detail--dlc">
            <div class="game-detail__visual">{image_html}</div>
            <div class="game-detail__content">
                <div class="game-detail__eyebrow">DLC / Add-on content</div>
                <h1>{name}</h1>
                <div class="game-detail__dlc-badge">This page is for DLC, not the base game</div>
                <p>{description}</p>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    metrics = st.columns(4)
    metrics[0].metric("Content Type", "DLC")
    metrics[1].metric("Price", price)
    metrics[2].metric("Release", release)
    metrics[3].metric("Parent Game", parent_name)

    detail_cols = st.columns([1.5, 1])
    with detail_cols[0]:
        st.subheader("About this DLC")
        st.markdown(
            f"""
            <div class="game-detail__panel">
                <p>{description}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _render_detail_chips("Genres", _as_list(dlc.get("genres", "")))
        _render_detail_chips("Tags", _as_list(dlc.get("tag", "")))
        _render_detail_chips("Categories", _as_list(dlc.get("categories", "")))

    with detail_cols[1]:
        st.subheader("DLC details")
        fact_html = _build_fact_list(
            [
                ("Type", "DLC"),
                ("DLC App ID", app_id or "N/A"),
                ("Parent Game", parent_name),
                ("Parent App ID", _safe_text(parent_id) or "N/A"),
                ("Released", release),
                ("Price", price),
            ]
        )
        st.markdown(
            f'<div class="game-detail__panel">{fact_html}</div>',
            unsafe_allow_html=True,
        )
        _render_external_links(dlc)

    _render_game_reviews(dlc, reviews_data, content_type="DLC")


def _render_game_reviews(game, reviews_data, content_type="game"):
    st.markdown("---")
    st.subheader(f"{content_type.title()} reviews")

    reviews = _get_reviews_for_game(game, reviews_data)
    if reviews.empty:
        st.info(f"No review rows are available for this {content_type.lower()}.")
        return

    reviews = _prepare_reviews_for_display(reviews)
    positive_count = int(reviews["is_positive_review"].sum())
    negative_count = int(reviews["is_negative_review"].sum())
    unknown_count = int(len(reviews) - positive_count - negative_count)

    cols = st.columns(4)
    cols[0].metric("Loaded Reviews", f"{len(reviews):,}")
    cols[1].metric("Recommended", f"{positive_count:,}")
    cols[2].metric("Not Recommended", f"{negative_count:,}")
    cols[3].metric("Unknown", f"{unknown_count:,}")

    game_key = _normalize_listing_id(
        game.get("_listing_id") or game.get("app_id") or game.get("parent_app_id")
    )
    key_prefix = content_type.lower().replace(" ", "_")
    controls = st.columns([1, 1, 2])
    with controls[0]:
        recommendation_filter = st.selectbox(
            "Review filter",
            ["All", "Recommended", "Not Recommended", "Unknown"],
            key=f"{key_prefix}_review_filter_{game_key}",
        )
    with controls[1]:
        review_limit = st.selectbox(
            "Show reviews",
            [5, 10, 20, 50],
            index=1,
            key=f"{key_prefix}_review_limit_{game_key}",
        )
    with controls[2]:
        search_text = st.text_input(
            "Search reviews",
            placeholder="Search review text",
            key=f"{key_prefix}_review_search_{game_key}",
        )

    visible_reviews = reviews.copy()
    if recommendation_filter == "Recommended":
        visible_reviews = visible_reviews[visible_reviews["is_positive_review"]]
    elif recommendation_filter == "Not Recommended":
        visible_reviews = visible_reviews[visible_reviews["is_negative_review"]]
    elif recommendation_filter == "Unknown":
        visible_reviews = visible_reviews[
            ~visible_reviews["is_positive_review"]
            & ~visible_reviews["is_negative_review"]
        ]

    if search_text.strip() and "review_text" in visible_reviews.columns:
        query = search_text.strip().casefold()
        visible_reviews = visible_reviews[
            visible_reviews["review_text"]
            .fillna("")
            .astype(str)
            .str.casefold()
            .str.contains(query, regex=False)
        ]

    if visible_reviews.empty:
        st.warning("No reviews match the selected review filters.")
        return

    for _, review in visible_reviews.head(review_limit).iterrows():
        st.markdown(_build_review_card_html(review), unsafe_allow_html=True)

    remaining = len(visible_reviews) - min(review_limit, len(visible_reviews))
    if remaining > 0:
        st.caption(f"{remaining:,} more matching reviews are available.")


def _render_detail_chips(title, values, max_items=None):
    if not values:
        return

    shown_values = values[:max_items] if max_items else values
    chips = "".join(
        f'<span class="game-detail__chip">{_safe_text(value)}</span>'
        for value in shown_values
    )
    overflow = ""
    if max_items and len(values) > max_items:
        overflow = (
            f'<span class="game-detail__chip">+{len(values) - max_items} more</span>'
        )

    st.markdown(
        f"""
        <div class="game-detail__chip-group">
            <h4>{_safe_text(title)}</h4>
            <div>{chips}{overflow}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_dlc_list(game, dlcs_data):
    dlcs = _get_dlcs_for_game(game, dlcs_data)

    st.markdown(
        '<h4 class="game-detail__section-title">DLC List</h4>',
        unsafe_allow_html=True,
    )
    if dlcs.empty:
        st.markdown(
            '<div class="game-detail__panel game-dlc__empty">'
            "No DLC records are available for this game.</div>",
            unsafe_allow_html=True,
        )
        return

    dlcs = _prepare_dlcs_for_display(dlcs)
    for _, dlc in dlcs.iterrows():
        st.markdown(_build_dlc_item_html(dlc), unsafe_allow_html=True)


def _render_external_links(game):
    game_url = _safe_url(game.get("url", ""))
    website_url = _safe_url(game.get("website", ""))
    links = []

    if game_url:
        links.append(
            f'<a class="game-detail__link" href="{game_url}" target="_blank" '
            'rel="noopener noreferrer">Open Steam page</a>'
        )
    if website_url and website_url != game_url:
        links.append(
            f'<a class="game-detail__link game-detail__link--secondary" '
            f'href="{website_url}" target="_blank" rel="noopener noreferrer">'
            "Official website</a>"
        )

    if not links:
        st.caption("No external product links are available.")
        return

    st.markdown(
        f'<div class="game-detail__links">{"".join(links)}</div>',
        unsafe_allow_html=True,
    )


def _get_dlcs_for_game(game, dlcs_data):
    if dlcs_data is None or dlcs_data.empty or "parent_app_id" not in dlcs_data.columns:
        return pd.DataFrame()

    game_id = _normalize_listing_id(game.get("app_id"))
    if not game_id:
        game_id = _normalize_listing_id(game.get("_listing_id"))
    if not game_id:
        return pd.DataFrame()

    parent_ids = dlcs_data["parent_app_id"].apply(_normalize_listing_id)
    return dlcs_data[parent_ids == game_id].copy()


def _prepare_dlcs_for_display(dlcs):
    prepared = dlcs.copy()

    if "price" in prepared.columns:
        prepared["_price_numeric"] = pd.to_numeric(
            prepared["price"], errors="coerce"
        ).fillna(0)
    else:
        prepared["_price_numeric"] = 0

    if "release_date" in prepared.columns:
        prepared["_release_date_sort"] = pd.to_datetime(
            prepared["release_date"], errors="coerce"
        )
    else:
        prepared["_release_date_sort"] = pd.NaT

    sort_columns = [
        column
        for column in ["_release_date_sort", "_price_numeric", "name"]
        if column in prepared.columns
    ]
    if sort_columns:
        prepared = prepared.sort_values(
            sort_columns,
            ascending=[False if column != "name" else True for column in sort_columns],
            na_position="last",
        )

    return prepared


def _build_dlc_item_html(dlc):
    name = _safe_text(_clean_display_value(dlc.get("name", "")) or "Untitled DLC")
    price = _format_price(dlc.get("_price_numeric", dlc.get("price")))
    release = _format_value_release(dlc.get("release_date"))
    app_id = _normalize_listing_id(dlc.get("app_id"))
    dlc_url = _safe_url(dlc.get("url", ""))
    details_url = _build_dlc_details_url(dlc)
    if not dlc_url and app_id:
        dlc_url = f"https://store.steampowered.com/app/{quote(app_id, safe='')}/"

    link_html = (
        f'<a class="game-dlc__steam-link" href="{dlc_url}" '
        'target="_blank" rel="noopener noreferrer">Open Steam</a>'
        if dlc_url
        else "<span>No link</span>"
    )

    return (
        '<div class="game-dlc__item">'
        f"<div><strong>{name}</strong><span>DLC add-on</span><span>{release}</span></div>"
        f"<div><strong>{price}</strong>"
        f'<a class="game-dlc__pdp-link" href="{details_url}">View DLC</a>'
        f"{link_html}</div>"
        "</div>"
    )


def _build_fact_list(facts):
    return "".join(
        f'<div class="game-detail__fact">'
        f"<span>{_safe_text(label)}</span>"
        f"<strong>{value}</strong>"
        f"</div>"
        for label, value in facts
    )


def _get_reviews_for_game(game, reviews_data):
    if reviews_data is None or reviews_data.empty:
        return pd.DataFrame()

    game_id = _normalize_listing_id(game.get("app_id"))
    if not game_id:
        game_id = _normalize_listing_id(game.get("_listing_id"))
    if not game_id:
        return pd.DataFrame()

    review_id_columns = [
        column
        for column in ["parent_app_id", "app_id", "app_id_game"]
        if column in reviews_data.columns
    ]
    for column in review_id_columns:
        review_ids = reviews_data[column].apply(_normalize_listing_id)
        matches = reviews_data[review_ids == game_id]
        if not matches.empty:
            return matches.copy()

    return pd.DataFrame()


def _prepare_reviews_for_display(reviews):
    prepared = reviews.copy()

    if "review_text" in prepared.columns:
        prepared["review_text"] = prepared["review_text"].fillna("").astype(str)
    else:
        prepared["review_text"] = ""

    prepared["review_sentiment"] = prepared.apply(_review_sentiment, axis=1)
    prepared["is_positive_review"] = prepared["review_sentiment"] == "positive"
    prepared["is_negative_review"] = prepared["review_sentiment"] == "negative"

    sort_columns = [
        column
        for column in ["votes_up", "total_playtime_hours", "playtime_at_review_hours"]
        if column in prepared.columns
    ]
    for column in sort_columns:
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce").fillna(0)

    if sort_columns:
        prepared = prepared.sort_values(sort_columns, ascending=False)

    return prepared


def _review_sentiment(review):
    for column in ["recommendation", "review_score"]:
        if column not in review.index:
            continue

        value = review.get(column)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue

        normalized = str(value).strip().casefold()
        if normalized in {"true", "1", "yes", "recommended", "positive"}:
            return "positive"
        if normalized in {"false", "0", "no", "not recommended", "negative"}:
            return "negative"

    return "unknown"


def _build_review_card_html(review):
    sentiment = review.get("review_sentiment", "unknown")
    if sentiment == "positive":
        verdict = "Recommended"
        verdict_class = "game-review__verdict--positive"
    elif sentiment == "negative":
        verdict = "Not Recommended"
        verdict_class = "game-review__verdict--negative"
    else:
        verdict = "Review"
        verdict_class = "game-review__verdict--unknown"
    review_text = _safe_text(
        _truncate_text(_plain_text(review.get("review_text", "")), max_length=850)
    )
    if not review_text:
        review_text = "No written review text is available for this review row."

    votes = _format_count(review.get("votes_up"))
    playtime = _format_hours(review.get("total_playtime_hours"))
    review_playtime = _format_hours(review.get("playtime_at_review_hours"))
    steam_purchase = _format_review_flag(review.get("steam_purchase"))
    early_access = _format_review_flag(review.get("written_during_early_access"))

    return f"""
    <article class="game-review">
        <div class="game-review__topline">
            <span class="game-review__verdict {verdict_class}">{verdict}</span>
            <span>{votes} helpful votes</span>
        </div>
        <p>{review_text}</p>
        <div class="game-review__meta">
            <span>Total playtime: <strong>{playtime}</strong></span>
            <span>At review: <strong>{review_playtime}</strong></span>
            <span>Steam purchase: <strong>{steam_purchase}</strong></span>
            <span>Early access: <strong>{early_access}</strong></span>
        </div>
    </article>
    """


def _get_selected_game_id():
    query_value = None
    try:
        query_value = st.query_params.get(DETAIL_QUERY_PARAM)
    except Exception:
        query_value = None

    if isinstance(query_value, list):
        query_value = query_value[0] if query_value else None

    if query_value:
        return _normalize_listing_id(query_value)

    state_value = st.session_state.get("selected_game_id")
    if state_value:
        return _normalize_listing_id(state_value)

    return None


def _get_selected_dlc_id():
    query_value = None
    try:
        query_value = st.query_params.get(DLC_DETAIL_QUERY_PARAM)
    except Exception:
        query_value = None

    if isinstance(query_value, list):
        query_value = query_value[0] if query_value else None

    if query_value:
        return _normalize_listing_id(query_value)

    state_value = st.session_state.get("selected_dlc_id")
    if state_value:
        return _normalize_listing_id(state_value)

    return None


def _open_game_details(listing_id):
    st.session_state["selected_game_id"] = _normalize_listing_id(listing_id)
    st.session_state.pop("selected_dlc_id", None)


def _open_dlc_details(dlc_id):
    st.session_state["selected_dlc_id"] = _normalize_listing_id(dlc_id)


def _open_parent_game_from_dlc(listing_id):
    _clear_selected_dlc()
    if listing_id:
        _open_game_details(listing_id)


def _clear_selected_game():
    st.session_state.pop("selected_game_id", None)
    st.session_state.pop("selected_dlc_id", None)
    try:
        if DETAIL_QUERY_PARAM in st.query_params:
            del st.query_params[DETAIL_QUERY_PARAM]
        if DLC_DETAIL_QUERY_PARAM in st.query_params:
            del st.query_params[DLC_DETAIL_QUERY_PARAM]
    except Exception:
        try:
            st.query_params.clear()
        except Exception:
            pass


def _clear_selected_dlc():
    st.session_state.pop("selected_dlc_id", None)
    try:
        if DLC_DETAIL_QUERY_PARAM in st.query_params:
            del st.query_params[DLC_DETAIL_QUERY_PARAM]
    except Exception:
        try:
            st.query_params.clear()
        except Exception:
            pass


def _find_game_by_listing_id(games, listing_id):
    matches = games[games["_listing_id"] == _normalize_listing_id(listing_id)]
    if matches.empty:
        return None
    return matches.iloc[0]


def _find_dlc_by_id(dlcs_data, dlc_id):
    if dlcs_data is None or dlcs_data.empty or "app_id" not in dlcs_data.columns:
        return None

    matches = dlcs_data[
        dlcs_data["app_id"].apply(_normalize_listing_id)
        == _normalize_listing_id(dlc_id)
    ]
    if matches.empty:
        return None
    return matches.iloc[0]


def _build_details_url(game):
    listing_id = _normalize_listing_id(game.get("_listing_id"))
    return f"?{DETAIL_QUERY_PARAM}={quote(listing_id, safe='')}"


def _build_dlc_details_url(dlc):
    dlc_id = _normalize_listing_id(dlc.get("app_id"))
    parent_id = _normalize_listing_id(dlc.get("parent_app_id"))
    query_parts = [f"{DLC_DETAIL_QUERY_PARAM}={quote(dlc_id, safe='')}"]
    if parent_id:
        query_parts.append(f"{DETAIL_QUERY_PARAM}={quote(parent_id, safe='')}")
    return f"?{'&'.join(query_parts)}"


def _inject_listing_css():
    st.markdown(
        """
        <style>
        .game-card {
            background: linear-gradient(160deg, #111827 0%, #1f2937 58%, #263647 100%);
            border: 1px solid rgba(148, 163, 184, 0.24);
            border-radius: 22px;
            box-shadow: 0 18px 38px rgba(15, 23, 42, 0.22);
            color: #f8fafc;
            display: flex;
            flex-direction: column;
            min-height: 560px;
            margin-bottom: 1.25rem;
            overflow: hidden;
        }

        .game-card__media {
            background: #0f172a;
            min-height: 160px;
        }

        .game-card__image {
            display: block;
            height: 160px;
            object-fit: cover;
            width: 100%;
        }

        .game-card__image--empty {
            align-items: center;
            background:
                radial-gradient(circle at 20% 20%, rgba(56, 189, 248, 0.28), transparent 30%),
                linear-gradient(135deg, #172033, #0f172a);
            color: #94a3b8;
            display: flex;
            font-weight: 700;
            justify-content: center;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .game-card__body {
            display: flex;
            flex: 1;
            flex-direction: column;
            gap: 0.72rem;
            padding: 1rem;
        }

        .game-card h3 {
            color: #f8fafc;
            font-size: 1.12rem;
            line-height: 1.25;
            margin: 0;
        }

        .game-card__description {
            color: #cbd5e1;
            font-size: 0.9rem;
            line-height: 1.45;
            margin: 0;
            min-height: 4rem;
        }

        .game-card__chips {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            min-height: 1.75rem;
        }

        .game-card__chip {
            background: rgba(56, 189, 248, 0.14);
            border: 1px solid rgba(125, 211, 252, 0.32);
            border-radius: 999px;
            color: #bae6fd;
            font-size: 0.72rem;
            font-weight: 700;
            padding: 0.2rem 0.58rem;
            text-transform: uppercase;
        }

        .game-card__summary {
            background: rgba(15, 23, 42, 0.5);
            border-left: 3px solid #38bdf8;
            border-radius: 10px;
            color: #dbeafe;
            font-size: 0.82rem;
            padding: 0.45rem 0.6rem;
        }

        .game-card__price-row,
        .game-card__stats {
            display: grid;
            gap: 0.5rem;
        }

        .game-card__price-row {
            align-items: center;
            border-top: 1px solid rgba(148, 163, 184, 0.2);
            color: #cbd5e1;
            grid-template-columns: 1fr auto;
            padding-top: 0.75rem;
        }

        .game-card__price-row strong {
            color: #86efac;
            font-size: 1.18rem;
        }

        .game-card__stats {
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }

        .game-card__stats span {
            background: rgba(255, 255, 255, 0.06);
            border-radius: 12px;
            color: #cbd5e1;
            font-size: 0.76rem;
            padding: 0.48rem;
        }

        .game-card__stats strong {
            color: #f8fafc;
            display: block;
            font-size: 0.88rem;
        }

        .game-card__maker {
            color: #94a3b8;
            font-size: 0.8rem;
            margin: 0;
        }

        .game-card__maker strong {
            color: #e2e8f0;
        }

        .game-card__action,
        div[data-testid="stButton"] > button {
            background: linear-gradient(135deg, #38bdf8, #22c55e);
            border: 0;
            border-radius: 13px;
            color: #04111d !important;
            font-weight: 800;
            min-height: 2.75rem;
            padding: 0.68rem 0.85rem;
            text-align: center;
            transition: transform 160ms ease, filter 160ms ease;
        }

        .game-card__action {
            display: block;
            margin-top: auto;
            text-decoration: none !important;
        }

        .game-card__action:hover,
        div[data-testid="stButton"] > button:hover {
            filter: brightness(1.05);
            transform: translateY(-1px);
        }

        .game-detail {
            background:
                radial-gradient(circle at 8% 12%, rgba(56, 189, 248, 0.24), transparent 30%),
                linear-gradient(135deg, #0f172a 0%, #172033 52%, #111827 100%);
            border: 1px solid rgba(148, 163, 184, 0.24);
            border-radius: 28px;
            box-shadow: 0 22px 60px rgba(15, 23, 42, 0.28);
            color: #f8fafc;
            display: grid;
            gap: 2rem;
            grid-template-columns: minmax(260px, 0.9fr) minmax(320px, 1.4fr);
            margin: 1rem 0 1.5rem;
            overflow: hidden;
            padding: 1.25rem;
        }

        .game-detail__visual {
            align-items: stretch;
            display: flex;
        }

        .game-detail__image {
            border-radius: 22px;
            box-shadow: 0 18px 45px rgba(2, 6, 23, 0.36);
            min-height: 320px;
            object-fit: cover;
            width: 100%;
        }

        .game-detail__image--empty {
            align-items: center;
            background:
                radial-gradient(circle at 20% 20%, rgba(56, 189, 248, 0.28), transparent 30%),
                linear-gradient(135deg, #172033, #0f172a);
            color: #94a3b8;
            display: flex;
            font-weight: 800;
            justify-content: center;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .game-detail--dlc {
            border-color: rgba(251, 191, 36, 0.36);
            background:
                radial-gradient(circle at 8% 12%, rgba(251, 191, 36, 0.2), transparent 30%),
                linear-gradient(135deg, #111827 0%, #1f2937 52%, #0f172a 100%);
        }

        .game-detail__content {
            align-self: center;
            padding: 1rem 0.5rem;
        }

        .game-detail__content h1 {
            color: #f8fafc;
            font-size: clamp(2rem, 4vw, 4rem);
            line-height: 0.98;
            margin: 0.35rem 0 1rem;
        }

        .game-detail__content p,
        .game-detail__panel p {
            color: #cbd5e1;
            font-size: 1rem;
            line-height: 1.65;
            margin: 0;
        }

        .game-detail__eyebrow {
            color: #7dd3fc;
            font-size: 0.8rem;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }

        .game-detail__dlc-badge {
            background: rgba(251, 191, 36, 0.16);
            border: 1px solid rgba(251, 191, 36, 0.34);
            border-radius: 999px;
            color: #fde68a;
            display: inline-flex;
            font-size: 0.82rem;
            font-weight: 900;
            margin-bottom: 1rem;
            padding: 0.38rem 0.8rem;
            text-transform: uppercase;
        }

        .game-detail__review {
            background: rgba(15, 23, 42, 0.56);
            border-left: 4px solid #22c55e;
            border-radius: 14px;
            color: #dcfce7;
            font-weight: 700;
            margin-top: 1rem;
            padding: 0.75rem 0.9rem;
        }

        .game-detail__panel {
            background: rgba(15, 23, 42, 0.58);
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 20px;
            margin-bottom: 1rem;
            padding: 1rem;
        }

        .game-detail__chip-group {
            margin: 1rem 0;
        }

        .game-detail__chip-group h4 {
            color: #e2e8f0;
            margin: 0 0 0.6rem;
        }

        .game-detail__chip {
            background: rgba(56, 189, 248, 0.13);
            border: 1px solid rgba(125, 211, 252, 0.28);
            border-radius: 999px;
            color: #bae6fd;
            display: inline-flex;
            font-size: 0.82rem;
            font-weight: 700;
            margin: 0 0.4rem 0.45rem 0;
            padding: 0.32rem 0.7rem;
        }

        .game-detail__fact {
            border-bottom: 1px solid rgba(148, 163, 184, 0.14);
            display: grid;
            gap: 0.4rem;
            grid-template-columns: 0.9fr 1.1fr;
            padding: 0.68rem 0;
        }

        .game-detail__fact:first-child {
            padding-top: 0;
        }

        .game-detail__fact:last-child {
            border-bottom: 0;
            padding-bottom: 0;
        }

        .game-detail__fact span {
            color: #94a3b8;
        }

        .game-detail__fact strong {
            color: #f8fafc;
            text-align: right;
        }

        .game-detail__section-title {
            color: #e2e8f0;
            font-size: 1rem;
            margin: 1rem 0 0.55rem;
        }

        .game-dlc__empty {
            color: #94a3b8;
            font-size: 0.9rem;
        }

        .game-dlc__list {
            display: grid;
            gap: 0.65rem;
            max-height: 360px;
            overflow-y: auto;
        }

        .game-dlc__item {
            align-items: center;
            background: rgba(255, 255, 255, 0.055);
            border: 1px solid rgba(148, 163, 184, 0.14);
            border-radius: 14px;
            display: grid;
            gap: 0.6rem;
            grid-template-columns: 1.4fr 0.7fr;
            margin-bottom: 0.55rem;
            padding: 0.7rem;
        }

        .game-dlc__item strong {
            color: #f8fafc;
            display: block;
            font-size: 0.9rem;
        }

        .game-dlc__item span {
            color: #94a3b8;
            display: block;
            font-size: 0.78rem;
            margin-top: 0.18rem;
        }

        .game-dlc__item div:last-child {
            text-align: right;
        }

        .game-dlc__item a {
            text-decoration: none !important;
        }

        .game-dlc__pdp-link,
        .game-dlc__steam-link {
            color: #7dd3fc !important;
            display: inline-block;
            font-size: 0.76rem;
            font-weight: 800;
            margin-top: 0.34rem;
        }

        .game-dlc__pdp-link {
            margin-right: 0.55rem;
        }

        .game-detail__links {
            display: grid;
            gap: 0.7rem;
        }

        .game-detail__link {
            background: linear-gradient(135deg, #38bdf8, #22c55e);
            border-radius: 14px;
            color: #04111d !important;
            display: block;
            font-weight: 900;
            padding: 0.78rem 1rem;
            text-align: center;
            text-decoration: none !important;
        }

        .game-detail__link--secondary {
            background: rgba(148, 163, 184, 0.22);
            color: #e2e8f0 !important;
        }

        .game-review {
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.94), rgba(30, 41, 59, 0.94));
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 20px;
            box-shadow: 0 14px 34px rgba(15, 23, 42, 0.18);
            color: #e2e8f0;
            margin: 0 0 1rem;
            padding: 1rem;
        }

        .game-review__topline {
            align-items: center;
            color: #94a3b8;
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
            justify-content: space-between;
            margin-bottom: 0.75rem;
        }

        .game-review__verdict {
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 900;
            padding: 0.32rem 0.72rem;
            text-transform: uppercase;
        }

        .game-review__verdict--positive {
            background: rgba(34, 197, 94, 0.16);
            color: #bbf7d0;
        }

        .game-review__verdict--negative {
            background: rgba(248, 113, 113, 0.16);
            color: #fecaca;
        }

        .game-review__verdict--unknown {
            background: rgba(148, 163, 184, 0.18);
            color: #e2e8f0;
        }

        .game-review p {
            color: #dbeafe;
            line-height: 1.58;
            margin: 0 0 0.95rem;
        }

        .game-review__meta {
            display: grid;
            gap: 0.5rem;
            grid-template-columns: repeat(4, minmax(0, 1fr));
        }

        .game-review__meta span {
            background: rgba(255, 255, 255, 0.055);
            border-radius: 12px;
            color: #94a3b8;
            font-size: 0.78rem;
            padding: 0.5rem;
        }

        .game-review__meta strong {
            color: #f8fafc;
            display: block;
            margin-top: 0.12rem;
        }

        @media (max-width: 900px) {
            .game-detail {
                grid-template-columns: 1fr;
            }

            .game-detail__image {
                min-height: 220px;
            }

            .game-review__meta {
                grid-template-columns: 1fr 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _unique_values(games, column):
    if column not in games.columns:
        return []

    values = set()
    for value in games[column].dropna():
        values.update(_as_list(value))

    return sorted(values, key=lambda item: item.casefold())


def _contains_any(value, selected_values):
    normalized_values = {item.casefold() for item in _as_list(value)}
    selected = {item.casefold() for item in selected_values}
    return bool(normalized_values & selected)


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, float) and pd.isna(value):
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


def _unique_ordered_values(values):
    unique_values = []
    seen = set()
    for value in values:
        normalized = str(value).strip().casefold()
        if normalized and normalized not in seen:
            unique_values.append(value)
            seen.add(normalized)
    return unique_values


def _normalize_listing_id(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _first_value(value):
    values = _as_list(value)
    return values[0] if values else ""


def _truncate_text(value, max_length):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""

    text = re.sub(r"\s+", " ", str(value)).strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1].rstrip()}..."


def _plain_text(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""

    text = re.sub(r"<[^>]+>", " ", str(value))
    return re.sub(r"\s+", " ", text).strip()


def _clean_display_value(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _has_display_value(value):
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass

    return str(value).strip().casefold() not in {"", "nan", "none"}


def _format_price(value):
    numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric_value):
        return "N/A"
    if numeric_value == 0:
        return "Free"
    return f"${numeric_value:,.2f}"


def _format_count(value):
    numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric_value):
        return "0"
    return f"{int(numeric_value):,}"


def _format_percent(value):
    numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric_value):
        return "N/A"
    return f"{numeric_value:.0f}%"


def _format_hours(value):
    numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric_value) or numeric_value == 0:
        return "N/A"
    return f"{numeric_value:,.1f}h"


def _format_review_flag(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"

    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return "Yes"
    if normalized in {"false", "0", "no"}:
        return "No"
    if normalized in {"nan", "none", ""}:
        return "N/A"
    return str(value)


def _format_release(game):
    if "release_date" in game.index and pd.notna(game.get("release_date")):
        release_date = pd.to_datetime(game.get("release_date"), errors="coerce")
        if pd.notna(release_date):
            return str(release_date.year)

    year = pd.to_numeric(pd.Series([game.get("year_numeric")]), errors="coerce").iloc[0]
    if pd.notna(year):
        return str(int(year))

    return "Unknown"


def _format_full_release(game):
    if "release_date" in game.index and pd.notna(game.get("release_date")):
        release_date = pd.to_datetime(game.get("release_date"), errors="coerce")
        if pd.notna(release_date):
            return release_date.strftime("%b %d, %Y")

    return _format_release(game)


def _format_value_release(value):
    release_date = pd.to_datetime(value, errors="coerce")
    if pd.notna(release_date):
        return release_date.strftime("%b %d, %Y")
    return "Release date unknown"


def _safe_text(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return escape(str(value), quote=True)


def _safe_url(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""

    text = str(value).strip()
    if not text.startswith(("http://", "https://")):
        return ""
    return escape(text, quote=True)
