# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class GameItem(scrapy.Item):
    """
    Base game scraped from the Steam Store.
    Written to: games_data.json
    """
    # ── Identity ──────────────────────────────────────────────────
    app_id = scrapy.Field()
    name = scrapy.Field()
    url = scrapy.Field()

    # ── Discovery Metadata ────────────────────────────────────────
    tag = scrapy.Field()                   # Tag/Category this game was found under
    tag_id = scrapy.Field()

    # ── Core Details ──────────────────────────────────────────────
    description = scrapy.Field()           # Full game description (HTML stripped)
    short_description = scrapy.Field()
    price = scrapy.Field()                 # Current price string (e.g. "$29.99" or "Free to Play")
    release_date = scrapy.Field()
    supported_languages = scrapy.Field()   # List of language strings

    # ── Supplementary Metadata ────────────────────────────────────
    developers = scrapy.Field()
    publishers = scrapy.Field()
    genres = scrapy.Field()
    categories = scrapy.Field()
    header_image = scrapy.Field()
    website = scrapy.Field()

    # ── Review Aggregates ─────────────────────────────────────────
    review_summary = scrapy.Field()        # e.g. "Very Positive", "Mixed", etc.
    total_positive = scrapy.Field()
    total_negative = scrapy.Field()
    total_reviews = scrapy.Field()         # From API query_summary
    total_english_reviews = scrapy.Field() # Scraped from store page HTML

    # ── DLCs ──────────────────────────────────────────────────────
    dlc_app_ids = scrapy.Field()           # List of DLC app IDs


class DlcItem(scrapy.Item):
    """
    A DLC associated with a base game.
    Written to: dlcs_data.json
    """
    # ── Identity ──────────────────────────────────────────────────
    app_id = scrapy.Field()
    name = scrapy.Field()
    url = scrapy.Field()
    parent_app_id = scrapy.Field()         # FK → GameItem.app_id

    # ── Discovery Metadata ────────────────────────────────────────
    tag = scrapy.Field()
    tag_id = scrapy.Field()

    # ── Core Details ──────────────────────────────────────────────
    description = scrapy.Field()
    short_description = scrapy.Field()
    price = scrapy.Field()
    release_date = scrapy.Field()
    supported_languages = scrapy.Field()

    # ── Supplementary Metadata ────────────────────────────────────
    developers = scrapy.Field()
    publishers = scrapy.Field()
    genres = scrapy.Field()
    categories = scrapy.Field()
    header_image = scrapy.Field()
    website = scrapy.Field()

    # ── Review Aggregates ─────────────────────────────────────────
    review_summary = scrapy.Field()
    total_positive = scrapy.Field()
    total_negative = scrapy.Field()
    total_reviews = scrapy.Field()
    total_english_reviews = scrapy.Field()


class ReviewItem(scrapy.Item):
    """
    A single user review extracted via the Steam Reviews API.
    Written to: reviews_data.json
    """
    # ── Foreign Key ───────────────────────────────────────────────
    app_id = scrapy.Field()                # FK → GameItem.app_id or DlcItem.app_id
    parent_app_id = scrapy.Field()         # FK → GameItem.app_id (same as app_id for games,
                                           #       base game's app_id for DLCs)

    # ── Review Identity ───────────────────────────────────────────
    recommendationid = scrapy.Field()      # Unique Steam review ID (for deduplication)

    # ── Review Data ───────────────────────────────────────────────
    recommendation = scrapy.Field()        # "Recommended" or "Not Recommended"
    review_text = scrapy.Field()           # Full review body
    review_score = scrapy.Field()          # "positive" or "negative" (raw API value)
    total_playtime_hours = scrapy.Field()  # Total hours played by reviewer
    playtime_at_review_hours = scrapy.Field()  # Hours played when review was posted
    votes_up = scrapy.Field()              # Number of helpful votes
    steam_purchase = scrapy.Field()        # Whether game was bought on Steam
    received_for_free = scrapy.Field()     # Whether reviewer got the game for free
    written_during_early_access = scrapy.Field()


class GameExtraItem(scrapy.Item):
    """
    Supplementary game metadata scraped by the update spider.
    Written to: games_extra.json
    """
    app_id = scrapy.Field()
    user_defined_tags = scrapy.Field()     # List of community tags from div.glance_tags
    original_price = scrapy.Field()        # Pre-discount price (if on sale)
    discount_percentage = scrapy.Field()   # e.g. "-75%"
    follower_count = scrapy.Field()        # Number of followers on the store page


class ReviewTimestampItem(scrapy.Item):
    """
    Timestamps for individual reviews fetched by the update spider.
    Written to: reviews_timestamps.json
    """
    app_id = scrapy.Field()
    recommendationid = scrapy.Field()      # Unique review ID from Steam
    timestamp_created = scrapy.Field()     # Unix timestamp when review was written
    timestamp_updated = scrapy.Field()     # Unix timestamp when review was last edited
