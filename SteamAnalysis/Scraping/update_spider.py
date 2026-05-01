"""
Steam Update Spider (v3)
========================
A lightweight spider that fetches supplementary data for games already
present in the v3 data files.

It reads app_ids from 'output/games_data_v3.json' and for each one:
  1) Hits the store page HTML to extract:
       - user_defined_tags (from div.glance_tags)
       - original_price / discount_percentage (from discount block)
       - follower_count (from embedded script data)
  2) Hits the /appreviews/ AJAX endpoint to extract:
       - recommendationid, timestamp_created, timestamp_updated

v3 Rules Applied:
  - Content blocklists (adult, polytheism, non-game items)
  - Reviews sorted by helpfulness, min 100 chars
  - 30 review timestamps per game (matching main spider)

Speed: 4× faster than the global settings via custom_settings overrides.

Output:
  - output/games_extra.json        (GameExtraItem JSONL)
  - output/reviews_timestamps.json (ReviewTimestampItem JSONL)

Usage:
    scrapy crawl steam_update

This spider does NOT touch your existing v3 data files.
"""

import json
import os
import re
import scrapy
from urllib.parse import urlencode, quote

from SteamScrapper.items import GameExtraItem, ReviewTimestampItem
from SteamScrapper.spiders.steam_spider import (
    BLOCKED_NAME_PATTERNS, BLOCKED_GENRE_KEYWORDS,
    _is_name_blocked, _are_genres_blocked,
    MIN_REVIEW_LENGTH,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
V3_GAMES_FILE = os.path.join("output", "games_data_v3.json")
UPDATED_IDS_FILE = "updated_app_ids_v3.txt"
MAX_REVIEWS_PER_GAME = 30       # Match v3 spider's cap
REVIEWS_PER_PAGE = 100          # Steam API max per request


class SteamUpdateSpider(scrapy.Spider):
    name = "steam_update"
    allowed_domains = ["store.steampowered.com"]

    # ── Age-gate bypass cookies ─────────────────────────────────────
    AGE_COOKIES = {
        "birthtime": "568022401",
        "mature_content": "1",
        "wants_mature_content": "1",
        "lastagecheckage": "1-0-1988",
    }

    # ── 4× FASTER: Override global settings ─────────────────────────
    custom_settings = {
        # Disable the IncrementalScrapingPipeline — we don't want to
        # re-register IDs or interfere with the tracking file.
        "ITEM_PIPELINES": {
            "SteamScrapper.pipelines.SplitJsonPipeline": 300,
        },
        # 4× speed boost over global settings (8 → 32 concurrent, 4 → 16 per domain)
        "CONCURRENT_REQUESTS": 32,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 16,
        "DOWNLOAD_DELAY": 0.25,
        "AUTOTHROTTLE_START_DELAY": 0.25,
        "AUTOTHROTTLE_MAX_DELAY": 5,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 12.0,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # In-flight review deduplication
        self._seen_review_ids = set()

    def _load_v3_app_ids(self):
        """Read all app_ids from games_data_v3.json."""
        app_ids = []
        if not os.path.exists(V3_GAMES_FILE):
            return app_ids
        with open(V3_GAMES_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    app_id = str(data.get("app_id", ""))
                    if app_id:
                        app_ids.append(app_id)
                except json.JSONDecodeError:
                    continue
        return app_ids

    def _load_completed_ids(self):
        """Load IDs that have already been updated (for resume support)."""
        completed = set()
        if os.path.exists(UPDATED_IDS_FILE):
            with open(UPDATED_IDS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        completed.add(line.strip())
        return completed

    def start_requests(self):
        """
        Read app_ids from games_data_v3.json, skip already-updated IDs,
        and yield one store-page request per remaining ID.
        """
        all_ids = self._load_v3_app_ids()
        completed_ids = self._load_completed_ids()

        pending = [aid for aid in all_ids if aid not in completed_ids]

        self.logger.info(
            f"Update spider: {len(all_ids)} games in v3 file, "
            f"{len(completed_ids)} already updated, "
            f"{len(pending)} pending."
        )

        if not pending:
            self.logger.info("Nothing to update — all games already processed!")
            return

        for app_id in pending:
            store_url = f"https://store.steampowered.com/app/{app_id}/"
            yield scrapy.Request(
                url=store_url,
                callback=self.parse_store_page,
                cookies=self.AGE_COOKIES,
                meta={"app_id": app_id},
                dont_filter=True,
            )

    # ──────────────────────────────────────────────────────────────
    #  PARSE 1: Store page → GameExtraItem
    # ──────────────────────────────────────────────────────────────
    def parse_store_page(self, response):
        """
        Extract user_defined_tags, original_price, discount_percentage,
        and follower_count from the game's store page HTML.
        Applies v3 content blocklists before yielding.
        """
        app_id = response.meta["app_id"]

        # ── 1. User-defined tags (community tags) ─────────────────
        tags = response.css(
            "div.glance_tags a.app_tag::text"
        ).getall()
        tags = [t.strip() for t in tags if t.strip()]

        # ── v3 RULE: Check tags against genre blocklist ───────────
        if _are_genres_blocked(tags):
            self.logger.info(
                f"[BLOCKED] App {app_id}: tags matched genre blocklist, skipping."
            )
            # Still mark as completed so we don't retry
            self._mark_completed(app_id)
            return

        # ── 2. Pricing info ───────────────────────────────────────
        original_price = None
        discount_percentage = None

        # Case A: Game is on sale (discount block exists)
        discount_pct_raw = response.css(
            "div.discount_pct::text"
        ).get()
        if discount_pct_raw:
            discount_percentage = discount_pct_raw.strip()

        original_price_raw = response.css(
            "div.discount_original_price::text"
        ).get()
        if original_price_raw:
            original_price = original_price_raw.strip()

        # Case B: No discount → the "regular" price is the only one
        if not original_price:
            regular_price = response.css(
                "div.game_purchase_price.price::text"
            ).get()
            if regular_price:
                price_text = regular_price.strip()
                if price_text.lower() not in ("", "free", "free to play"):
                    original_price = price_text

        # ── 3. Follower count ─────────────────────────────────────
        follower_count = None
        scripts = response.xpath(
            "//script[contains(text(), 'GStoreItemData')]/text()"
        ).getall()
        for script_text in scripts:
            match = re.search(
                r'"followers"\s*:\s*(\d+)', script_text
            )
            if match:
                follower_count = int(match.group(1))
                break

        # ── Yield GameExtraItem ───────────────────────────────────
        yield GameExtraItem(
            app_id=int(app_id),
            user_defined_tags=tags,
            original_price=original_price,
            discount_percentage=discount_percentage,
            follower_count=follower_count,
        )

        self.logger.info(
            f"App {app_id}: tags={len(tags)}, "
            f"discount={discount_percentage}, "
            f"followers={follower_count}"
        )

        # ── Now fetch review timestamps via AJAX ──────────────────
        # v3 RULE: Sort by helpfulness (filter=updated, day_range=9999)
        yield from self._request_review_timestamps(
            app_id=app_id,
            cursor="*",
            collected=0,
        )

    # ──────────────────────────────────────────────────────────────
    #  PARSE 2: Reviews API → ReviewTimestampItem
    # ──────────────────────────────────────────────────────────────
    def _request_review_timestamps(self, app_id, cursor, collected):
        """
        Fire a paginated request to the Steam reviews API
        to extract review timestamps.
        Uses v3 helpfulness sorting.
        """
        remaining = MAX_REVIEWS_PER_GAME - collected
        if remaining <= 0:
            return

        num_per_page = min(REVIEWS_PER_PAGE, remaining)

        params = {
            "json": "1",
            "cursor": cursor,
            "language": "english",
            "filter": "updated",          # v3: sort by helpfulness
            "day_range": "9999",          # v3: all-time reviews
            "review_type": "all",
            "purchase_type": "all",
            "num_per_page": str(num_per_page),
            "filter_offtopic_activity": "0",
        }
        url = (
            f"https://store.steampowered.com/appreviews/{app_id}"
            f"?{urlencode(params, quote_via=quote)}"
        )
        yield scrapy.Request(
            url,
            callback=self.parse_review_timestamps,
            cookies=self.AGE_COOKIES,
            meta={
                "app_id": app_id,
                "collected": collected,
            },
            dont_filter=True,
        )

    def parse_review_timestamps(self, response):
        """
        Parse review JSON and yield ReviewTimestampItem for each review.
        Applies v3 rules: min 100 chars, in-flight deduplication.
        """
        app_id = response.meta["app_id"]
        collected = response.meta["collected"]

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            self.logger.warning(
                f"Invalid reviews JSON for app {app_id}"
            )
            return

        raw_reviews = data.get("reviews", [])

        for rev in raw_reviews:
            if collected >= MAX_REVIEWS_PER_GAME:
                break

            # ── v3 RULE: In-flight deduplication ──────────────────
            rec_id = rev.get("recommendationid")
            if rec_id and rec_id in self._seen_review_ids:
                continue
            if rec_id:
                self._seen_review_ids.add(rec_id)

            # ── v3 RULE: Min 100-character review length ──────────
            review_text = rev.get("review", "")
            if len(review_text) < MIN_REVIEW_LENGTH:
                continue

            yield ReviewTimestampItem(
                app_id=int(app_id),
                recommendationid=rec_id,
                timestamp_created=rev.get("timestamp_created"),
                timestamp_updated=rev.get("timestamp_updated"),
            )
            collected += 1

        # ── Paginate if needed ────────────────────────────────────
        next_cursor = data.get("cursor", "")
        has_more = (
            len(raw_reviews) > 0
            and next_cursor
            and next_cursor != "*"
            and collected < MAX_REVIEWS_PER_GAME
        )

        if has_more:
            yield from self._request_review_timestamps(
                app_id=app_id,
                cursor=next_cursor,
                collected=collected,
            )
        else:
            self.logger.info(
                f"App {app_id}: collected {collected} review timestamps"
            )
            # Mark as successfully completed so we can resume later
            self._mark_completed(app_id)

    def _mark_completed(self, app_id):
        """Append app_id to the updated tracking file for resume support."""
        with open(UPDATED_IDS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{app_id}\n")
