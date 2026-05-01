"""
Steam Store Spider (v3)
=======================
Changes from v2:
  - Indie/startup studio priority via tag co-filtering
  - Content blocklists (adult, polytheism, non-game items)
  - Reviews sorted by helpfulness, min 100 chars, deduplicated
  - DLC scraping kept but filtered by same name blocklist
  - 70 games per tag, 30 reviews per game
  - Faster concurrency settings

Usage:
    scrapy crawl steam

Output goes to output/games_data.json, output/dlcs_data.json,
output/reviews_data.json via the SplitJsonPipeline.
"""

import json
import os
import re
import scrapy
from urllib.parse import urlencode, quote

from SteamScrapper.items import GameItem, DlcItem, ReviewItem


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Tags to scrape — rebalanced toward indie games.
# Each genre tag is co-filtered with the Indie tag (492) so results
# are games that are BOTH indie AND that genre.
INDIE_GENRE_TAGS = {
    "Action":       19,
    "Adventure":    21,
    "RPG":          122,
    "Strategy":     9,
    "Simulation":   599,
    "Horror":       1667,
    "Puzzle":       1664,
    "Platformer":   1625,
    "Survival":     1662,
    "FPS":          1663,
    "Open World":   1695,
    "Casual":       597,
}

# Pure genre tags WITHOUT the indie filter — allows a few AAA titles in.
AAA_GENRE_TAGS = {
    "Action":       19,
    "Adventure":    21,
    "RPG":          122,
}
AAA_GAMES_PER_TAG = 10  # Only 10 AAA games per genre

INDIE_TAG_ID = 492
GAMES_PER_TAG = 70
MAX_REVIEWS_PER_GAME = 30     # 30 most-helpful reviews per game
REVIEWS_PER_PAGE = 100        # Steam API max per request
MIN_REVIEW_LENGTH = 100       # Skip reviews shorter than this

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Content Blocklists
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Name patterns — block soundtracks, artbooks, DLC packs, pantheon, etc.
BLOCKED_NAME_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bsoundtrack\b",
        r"\bost\b",
        r"\bartbook\b",
        r"\balbum\b",
        r"\bboost\b",
        r"\bdeluxe edition\b",
        r"\bexpansion pack\b",
        r"\bseason pass\b",
        r"\bbundle\b",
        r"\bcollector'?s edition\b",
        r"\bpantheon\b",
    ]
]

# Genre / tag keywords — block adult content and polytheism
BLOCKED_GENRE_KEYWORDS = {
    "nudity", "sexual content", "nsfw", "hentai", "adult only",
    "fan service", "erotic", "dating sim", "adult",
    "mythology",
}


def _is_name_blocked(name: str) -> bool:
    """Return True if the game name matches any blocked pattern."""
    for pattern in BLOCKED_NAME_PATTERNS:
        if pattern.search(name):
            return True
    return False


def _are_genres_blocked(genres: list, description: str = "") -> bool:
    """Return True if any genre/tag matches the blocklist."""
    combined = " ".join(genres).lower()
    desc_lower = description.lower()
    for keyword in BLOCKED_GENRE_KEYWORDS:
        if keyword in combined:
            return True
    # Also check description for polytheism / multiple deities
    deity_patterns = [
        r"\bgods\b", r"\bdeities\b", r"\bdemigods?\b",
        r"\bpolythe", r"\bpantheon\b",
    ]
    for pat in deity_patterns:
        if re.search(pat, desc_lower):
            return True
    return False


class SteamSpider(scrapy.Spider):
    name = "steam"
    allowed_domains = ["store.steampowered.com"]

    custom_settings = {
        "COOKIES_ENABLED": True,
    }

    # Cookies sent with every request to bypass age verification
    AGE_COOKIES = {
        "birthtime": "568022401",       # Jan 1, 1988 → proves user is 18+
        "mature_content": "1",          # Agree to view mature content
        "wants_mature_content": "1",
        "lastagecheckage": "1-0-1988",
        "Steam_Language": "english",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Will be populated by IncrementalScrapingPipeline.open_spider()
        self.scraped_app_ids = set()
        # In-flight review deduplication
        self._seen_review_ids = set()

    # ──────────────────────────────────────────────────────────────
    #  START REQUESTS — iterate over tags
    # ──────────────────────────────────────────────────────────────
    SEARCH_PAGE_SIZE = 100  # Steam allows up to 100 results per AJAX page

    def start_requests(self):
        """
        Kick off search requests:
        1) Indie + genre co-filtered tags (70 NEW games each)
        2) Pure genre tags for a few AAA titles (10 NEW games each)
        """
        # ── Indie-focused tags ────────────────────────────────────
        for tag_name, tag_id in INDIE_GENRE_TAGS.items():
            url = (
                f"https://store.steampowered.com/search/results/?"
                f"query&start=0&count={self.SEARCH_PAGE_SIZE}"
                f"&tags={INDIE_TAG_ID}%2C{tag_id}&infinite=1"
            )
            yield scrapy.Request(
                url,
                callback=self.parse_search_results,
                cookies=self.AGE_COOKIES,
                meta={
                    "tag_name": f"Indie_{tag_name}",
                    "tag_id": tag_id,
                    "tag_filter": f"{INDIE_TAG_ID}%2C{tag_id}",
                    "games_limit": GAMES_PER_TAG,
                    "collected_new": 0,
                    "page_start": 0,
                },
                headers={"X-Requested-With": "XMLHttpRequest"},
            )

        # ── AAA slots (pure genre, no indie filter) ───────────────
        for tag_name, tag_id in AAA_GENRE_TAGS.items():
            url = (
                f"https://store.steampowered.com/search/results/?"
                f"query&start=0&count={self.SEARCH_PAGE_SIZE}"
                f"&tags={tag_id}&infinite=1"
            )
            yield scrapy.Request(
                url,
                callback=self.parse_search_results,
                cookies=self.AGE_COOKIES,
                meta={
                    "tag_name": f"AAA_{tag_name}",
                    "tag_id": tag_id,
                    "tag_filter": str(tag_id),
                    "games_limit": AAA_GAMES_PER_TAG,
                    "collected_new": 0,
                    "page_start": 0,
                },
                headers={"X-Requested-With": "XMLHttpRequest"},
            )

    # ──────────────────────────────────────────────────────────────
    #  PARSE: Search results (AJAX JSON from /search/results/)
    #  Now with PAGINATION — keeps flipping pages until we hit
    #  the target number of NEW (unscraped) games.
    # ──────────────────────────────────────────────────────────────
    def parse_search_results(self, response):
        """
        Steam's search endpoint with infinite=1 returns JSON containing
        an HTML fragment in .results_html — parse app IDs out of it.
        If we haven't collected enough NEW games, request the next page.
        """
        tag_name = response.meta["tag_name"]
        tag_id = response.meta["tag_id"]
        tag_filter = response.meta["tag_filter"]
        games_limit = response.meta["games_limit"]
        collected_new = response.meta["collected_new"]
        page_start = response.meta["page_start"]

        try:
            data = json.loads(response.text)
            html_fragment = data.get("results_html", "")
            total_count = data.get("total_count", 0)
        except (json.JSONDecodeError, TypeError):
            html_fragment = response.text
            total_count = 0

        # Extract app IDs from <a data-ds-appid="12345"> elements
        sel = scrapy.Selector(text=html_fragment)
        app_links = sel.css("a[data-ds-appid]")

        page_new = 0
        for link in app_links:
            if collected_new >= games_limit:
                break
            app_id = link.attrib.get("data-ds-appid", "").strip()
            if not app_id or not app_id.isdigit():
                continue

            # ── Incremental scraping: skip already-scraped games ──
            if app_id in self.scraped_app_ids:
                continue

            # Fetch full details through the Steam API
            detail_url = (
                f"https://store.steampowered.com/api/appdetails"
                f"?appids={app_id}&l=english&cc=us"
            )
            yield scrapy.Request(
                detail_url,
                callback=self.parse_app_details,
                cookies=self.AGE_COOKIES,
                meta={
                    "app_id": app_id,
                    "tag_name": tag_name,
                    "tag_id": tag_id,
                    "item_type": "game",
                    "parent_app_id": None,
                },
                dont_filter=False,
            )
            collected_new += 1
            page_new += 1

        self.logger.info(
            f"[{tag_name}] Page {page_start // self.SEARCH_PAGE_SIZE + 1}: "
            f"found {page_new} new games (total new: {collected_new}/{games_limit})"
        )

        # ── PAGINATION: If we still need more, request the next page ──
        next_start = page_start + self.SEARCH_PAGE_SIZE
        need_more = collected_new < games_limit
        has_more_pages = len(app_links) > 0 and next_start < total_count

        if need_more and has_more_pages:
            next_url = (
                f"https://store.steampowered.com/search/results/?"
                f"query&start={next_start}&count={self.SEARCH_PAGE_SIZE}"
                f"&tags={tag_filter}&infinite=1"
            )
            yield scrapy.Request(
                next_url,
                callback=self.parse_search_results,
                cookies=self.AGE_COOKIES,
                meta={
                    "tag_name": tag_name,
                    "tag_id": tag_id,
                    "tag_filter": tag_filter,
                    "games_limit": games_limit,
                    "collected_new": collected_new,
                    "page_start": next_start,
                },
                headers={"X-Requested-With": "XMLHttpRequest"},
                dont_filter=True,
            )
        elif need_more and not has_more_pages:
            self.logger.info(
                f"[{tag_name}] Ran out of search results at {collected_new}/{games_limit} new games."
            )

    # ──────────────────────────────────────────────────────────────
    #  PARSE: App details (Steam API JSON)
    # ──────────────────────────────────────────────────────────────
    def parse_app_details(self, response):
        """Parse the /api/appdetails JSON for a single app."""
        app_id = response.meta["app_id"]
        tag_name = response.meta["tag_name"]
        tag_id = response.meta["tag_id"]
        item_type = response.meta["item_type"]
        parent_app_id = response.meta["parent_app_id"]

        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError:
            self.logger.warning(f"Invalid JSON for app {app_id}")
            return

        app_data = payload.get(str(app_id), {})
        if not app_data.get("success"):
            self.logger.warning(f"API returned failure for app {app_id}")
            return

        data = app_data["data"]
        app_type = data.get("type", "").lower()
        name = data.get("name", "")

        # ── FILTER 1: Type check ──────────────────────────────────
        # For base games, only accept type "game"
        # For DLCs, only accept type "dlc"
        if item_type == "game" and app_type != "game":
            self.logger.info(
                f"[BLOCKED] App {app_id} '{name}' — type '{app_type}' "
                f"is not a game, skipping."
            )
            return
        if item_type == "dlc" and app_type != "dlc":
            self.logger.info(
                f"[BLOCKED] App {app_id} '{name}' — type '{app_type}' "
                f"is not a DLC, skipping."
            )
            return

        # ── FILTER 2: Name blocklist ──────────────────────────────
        if _is_name_blocked(name):
            self.logger.info(
                f"[BLOCKED] App {app_id} '{name}' — "
                f"matched name blocklist, skipping."
            )
            return

        # ── FILTER 3: Genre / content blocklist ───────────────────
        genres = [g["description"] for g in data.get("genres", [])]
        short_desc = data.get("short_description", "")
        if _are_genres_blocked(genres, short_desc):
            self.logger.info(
                f"[BLOCKED] App {app_id} '{name}' — "
                f"matched genre/content blocklist, skipping."
            )
            return

        # ── Build a dict of shared fields ─────────────────────────
        fields = {}
        fields["app_id"] = int(app_id)
        fields["name"] = name
        fields["url"] = f"https://store.steampowered.com/app/{app_id}/"
        fields["tag"] = tag_name
        fields["tag_id"] = tag_id

        # Description — strip HTML tags for clean text
        raw_desc = data.get("detailed_description", "")
        fields["description"] = self._strip_html(raw_desc)
        fields["short_description"] = short_desc

        # Price (forced to USD via &cc=us)
        if data.get("is_free"):
            fields["price"] = "Free to Play"
        else:
            price_overview = data.get("price_overview", {})
            fields["price"] = price_overview.get("final_formatted", "N/A")

        # Release date
        release = data.get("release_date", {})
        fields["release_date"] = release.get("date", "TBA")

        # Languages — strip HTML tags like <strong>*</strong>
        raw_langs = data.get("supported_languages", "")
        fields["supported_languages"] = self._parse_languages(raw_langs)

        # Supplementary metadata
        fields["developers"] = data.get("developers", [])
        fields["publishers"] = data.get("publishers", [])
        fields["genres"] = genres
        fields["categories"] = [c["description"] for c in data.get("categories", [])]
        fields["header_image"] = data.get("header_image", "")
        fields["website"] = data.get("website", "")

        # Review aggregates — initialized, updated later
        fields["review_summary"] = ""
        fields["total_positive"] = 0
        fields["total_negative"] = 0
        fields["total_reviews"] = 0
        fields["total_english_reviews"] = 0

        # DLC list (only for base games)
        dlc_ids = data.get("dlc", [])
        if item_type == "game":
            fields["dlc_app_ids"] = dlc_ids
        if item_type == "dlc":
            fields["parent_app_id"] = int(parent_app_id) if parent_app_id else None

        # ── Next step: scrape the store HTML page for total English reviews ──
        store_url = f"https://store.steampowered.com/app/{app_id}/"
        yield scrapy.Request(
            store_url,
            callback=self.parse_store_page,
            cookies=self.AGE_COOKIES,
            meta={
                "fields": fields,
                "item_type": item_type,
                "parent_app_id": parent_app_id,
                "dlc_ids": dlc_ids,
                "app_id": app_id,
            },
            dont_filter=True,
        )

    # ──────────────────────────────────────────────────────────────
    #  PARSE: Store page HTML (extract total English reviews)
    # ──────────────────────────────────────────────────────────────
    def parse_store_page(self, response):
        """
        Scrape the game's main store page to extract the true review
        counts (positive, negative, all, english) directly from HTML.
        """
        fields = response.meta["fields"]
        item_type = response.meta["item_type"]
        parent_app_id = response.meta["parent_app_id"]
        dlc_ids = response.meta["dlc_ids"]
        app_id = response.meta["app_id"]

        def _extract_number(text):
            if not text: return 0
            # Extract consecutive digits, ignoring commas
            match = re.search(r'([0-9,]+)', text)
            if match:
                return int(match.group(1).replace(',', ''))
            return 0

        # Scrape numbers directly from the Review filter dropdown menu labels
        lbl_all = response.xpath('//label[@for="review_type_all"]//span[@class="user_reviews_count"]/text()').get()
        lbl_pos = response.xpath('//label[@for="review_type_positive"]//span[@class="user_reviews_count"]/text()').get()
        lbl_neg = response.xpath('//label[@for="review_type_negative"]//span[@class="user_reviews_count"]/text()').get()

        if lbl_all: fields["total_reviews"] = _extract_number(lbl_all)
        if lbl_pos: fields["total_positive"] = _extract_number(lbl_pos)
        if lbl_neg: fields["total_negative"] = _extract_number(lbl_neg)

        # Scrape the exact English Reviews specific count
        eng_count = response.xpath(
            '//div[contains(@class, "summary_text") and .//div[contains(@class, "title") and contains(text(), "English")]]'
            '//span[contains(@class, "app_reviews_count") or contains(@class, "review_summary_count")]/text()'
        ).get()
        
        # Fallback if structure shifts
        if not eng_count:
            eng_count = response.xpath(
                '//div[contains(@class, "review_summary_ctn") and .//div[contains(text(), "English Reviews")]]'
                '//span[contains(@class, "review_summary_count") or contains(@class, "app_reviews_count")]/text()'
            ).get()

        if eng_count:
            fields["total_english_reviews"] = _extract_number(eng_count)
        
        self.logger.debug(
            f"App {app_id}: English reviews scraped = {fields['total_english_reviews']}"
        )

        # ── Now fetch reviews via AJAX endpoint ───────────────────
        yield from self._request_reviews(
            app_id=app_id,
            fields=fields,
            item_type=item_type,
            parent_app_id=parent_app_id,
            dlc_ids=dlc_ids,
            cursor="*",
            reviews_collected=0,
            review_items=[],
        )

    # ──────────────────────────────────────────────────────────────
    #  REVIEWS: Paginated fetch via /appreviews/<appid> AJAX
    # ──────────────────────────────────────────────────────────────
    def _request_reviews(self, app_id, fields, item_type, parent_app_id,
                         dlc_ids, cursor, reviews_collected, review_items):
        """
        Fire a paginated request to the Steam reviews API.
        Reviews are sorted by helpfulness (most-voted first).
        """
        remaining = MAX_REVIEWS_PER_GAME - reviews_collected
        if remaining <= 0:
            # Already at cap → yield everything
            yield from self._finalize_and_yield(
                fields, item_type, parent_app_id, dlc_ids, review_items
            )
            return

        num_per_page = min(REVIEWS_PER_PAGE, remaining)

        params = {
            "json": "1",
            "cursor": cursor,
            "language": "english",
            "filter": "updated",         # Sort by helpfulness
            "day_range": "9999",         # All-time (not just recent)
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
            callback=self.parse_reviews,
            cookies=self.AGE_COOKIES,
            meta={
                "fields": fields,
                "item_type": item_type,
                "parent_app_id": parent_app_id,
                "dlc_ids": dlc_ids,
                "app_id": app_id,
                "reviews_collected": reviews_collected,
                "review_items": review_items,
            },
            dont_filter=True,
        )

    def parse_reviews(self, response):
        """Parse reviews JSON, accumulate ReviewItems, paginate if needed."""
        fields = response.meta["fields"]
        item_type = response.meta["item_type"]
        parent_app_id = response.meta["parent_app_id"]
        dlc_ids = response.meta["dlc_ids"]
        app_id = response.meta["app_id"]
        reviews_collected = response.meta["reviews_collected"]
        review_items = response.meta["review_items"]

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            self.logger.warning(f"Invalid reviews JSON for app {app_id}")
            data = {}

        # ── Extract review summary stats (on first page only) ─────
        if reviews_collected == 0:
            query_summary = data.get("query_summary", {})
            fields["review_summary"] = query_summary.get("review_score_desc", "")

        # ── Parse individual reviews ──────────────────────────────
        raw_reviews = data.get("reviews", [])

        # Determine FK values for the ReviewItem
        review_app_id = int(app_id)
        if item_type == "dlc":
            review_parent_app_id = int(parent_app_id) if parent_app_id else None
        else:
            review_parent_app_id = int(app_id)

        skipped_short = 0
        skipped_dedup = 0

        for rev in raw_reviews:
            if reviews_collected >= MAX_REVIEWS_PER_GAME:
                break

            # ── FILTER: Minimum review length ─────────────────────
            review_text = rev.get("review", "")
            if len(review_text.strip()) < MIN_REVIEW_LENGTH:
                skipped_short += 1
                continue

            # ── DEDUP: Skip reviews already seen in this session ──
            rec_id = rev.get("recommendationid")
            if rec_id and rec_id in self._seen_review_ids:
                skipped_dedup += 1
                continue
            if rec_id:
                self._seen_review_ids.add(rec_id)

            author = rev.get("author", {})
            total_mins = author.get("playtime_forever", 0)
            at_review_mins = author.get("playtime_at_review", 0)

            review_item = ReviewItem(
                app_id=review_app_id,
                parent_app_id=review_parent_app_id,
                recommendationid=rec_id,
                recommendation=(
                    "Recommended" if rev.get("voted_up") else "Not Recommended"
                ),
                review_text=review_text,
                review_score="positive" if rev.get("voted_up") else "negative",
                total_playtime_hours=round(total_mins / 60, 1),
                playtime_at_review_hours=round(at_review_mins / 60, 1),
                votes_up=rev.get("votes_up", 0),
                steam_purchase=rev.get("steam_purchase", False),
                received_for_free=rev.get("received_for_free", False),
                written_during_early_access=rev.get(
                    "written_during_early_access", False
                ),
            )
            review_items.append(review_item)
            reviews_collected += 1

        if skipped_short:
            self.logger.debug(
                f"App {app_id}: skipped {skipped_short} short reviews (<{MIN_REVIEW_LENGTH} chars)"
            )
        if skipped_dedup:
            self.logger.debug(
                f"App {app_id}: skipped {skipped_dedup} duplicate reviews"
            )

        # ── Decide: paginate or finalize ──────────────────────────
        next_cursor = data.get("cursor", "")
        has_more = (
            len(raw_reviews) > 0
            and next_cursor
            and next_cursor != "*"
            and reviews_collected < MAX_REVIEWS_PER_GAME
        )

        if has_more:
            # Continue paginating
            yield from self._request_reviews(
                app_id=app_id,
                fields=fields,
                item_type=item_type,
                parent_app_id=parent_app_id,
                dlc_ids=dlc_ids,
                cursor=next_cursor,
                reviews_collected=reviews_collected,
                review_items=review_items,
            )
        else:
            # Done collecting reviews for this app
            self.logger.info(
                f"App {app_id} ({fields.get('name', '')}): "
                f"collected {reviews_collected} reviews"
            )
            yield from self._finalize_and_yield(
                fields, item_type, parent_app_id, dlc_ids, review_items
            )

    # ──────────────────────────────────────────────────────────────
    #  FINALIZE: Yield GameItem/DlcItem + all ReviewItems + DLC reqs
    # ──────────────────────────────────────────────────────────────
    def _finalize_and_yield(self, fields, item_type, parent_app_id,
                            dlc_ids, review_items):
        """
        Yield the game/DLC item, then all its associated ReviewItems,
        then spawn DLC detail requests if applicable.
        """
        app_id = fields["app_id"]

        # ── Yield the game or DLC item ────────────────────────────
        if item_type == "game":
            game_item = GameItem()
            for key in GameItem.fields:
                if key in fields:
                    game_item[key] = fields[key]
            yield game_item
        else:
            dlc_item = DlcItem()
            for key in DlcItem.fields:
                if key in fields:
                    dlc_item[key] = fields[key]
            yield dlc_item

        # ── Yield all ReviewItems ─────────────────────────────────
        for review_item in review_items:
            yield review_item

        # ── Spawn DLC detail requests (only for base games) ──────
        if item_type == "game" and dlc_ids:
            for dlc_id in dlc_ids:
                dlc_id_str = str(dlc_id)

                # Incremental: skip already-scraped DLCs
                if dlc_id_str in self.scraped_app_ids:
                    self.logger.info(
                        f"Skipping DLC {dlc_id_str} (already scraped)"
                    )
                    continue

                detail_url = (
                    f"https://store.steampowered.com/api/appdetails"
                    f"?appids={dlc_id}&l=english&cc=us"
                )
                yield scrapy.Request(
                    detail_url,
                    callback=self.parse_app_details,
                    cookies=self.AGE_COOKIES,
                    meta={
                        "app_id": dlc_id_str,
                        "tag_name": fields["tag"],
                        "tag_id": fields["tag_id"],
                        "item_type": "dlc",
                        "parent_app_id": str(app_id),
                    },
                    dont_filter=False,
                )

    # ──────────────────────────────────────────────────────────────
    #  Utility helpers
    # ──────────────────────────────────────────────────────────────
    @staticmethod
    def _strip_html(raw_html: str) -> str:
        """Remove HTML tags and collapse whitespace."""
        clean = re.sub(r"<[^>]+>", " ", raw_html)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    @staticmethod
    def _parse_languages(raw_html: str) -> list:
        """
        Parse the languages string from Steam API.
        e.g. 'English, French, <strong>*</strong>' → ['English', 'French']
        """
        stripped = re.sub(r"<[^>]+>", "", raw_html)
        langs = [lang.strip() for lang in stripped.split(",") if lang.strip()]
        # Remove footnote markers like '*'
        langs = [re.sub(r"\*", "", lang).strip() for lang in langs]
        return [lang for lang in langs if lang]
