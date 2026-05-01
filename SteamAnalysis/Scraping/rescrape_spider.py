"""
Rescrape Spider
===============
Re-fetches OLD games (from scraped_app_ids.txt) that are NOT yet in
the v3 data files.  Applies the exact same v3 rules as the main spider:
  - Content blocklists (adult, polytheism, soundtracks, etc.)
  - 30 most-helpful reviews per game, min 100 chars
  - In-flight review deduplication
  - DLC scraping (filtered by name blocklist)

Usage:
    scrapy crawl rescrape

Output appends to the same v3 files via SplitJsonPipeline.
"""

import json
import os
import scrapy

from SteamScrapper.spiders.steam_spider import SteamSpider


class RescrapeSpider(SteamSpider):
    """
    Inherits ALL parsing logic, blocklists, and review filters from
    SteamSpider.  Only overrides start_requests() to feed old app IDs
    instead of searching Steam by tags.
    """
    name = "rescrape"

    SCRAPED_IDS_FILE = "scraped_app_ids.txt"
    V3_GAMES_FILE = os.path.join("output", "games_data_v3.json")
    V3_DLCS_FILE = os.path.join("output", "dlcs_data_v3.json")

    def _load_v3_app_ids(self):
        """Read app_ids already present in the v3 JSON files."""
        v3_ids = set()
        for filepath in (self.V3_GAMES_FILE, self.V3_DLCS_FILE):
            if not os.path.exists(filepath):
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        app_id = str(data.get("app_id", ""))
                        if app_id:
                            v3_ids.add(app_id)
                    except json.JSONDecodeError:
                        continue
        return v3_ids

    def _load_all_scraped_ids(self):
        """Read every app_id from scraped_app_ids.txt."""
        all_ids = set()
        if os.path.exists(self.SCRAPED_IDS_FILE):
            with open(self.SCRAPED_IDS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        all_ids.add(line)
        return all_ids

    def start_requests(self):
        """
        Instead of searching Steam by tags, calculate the difference
        between all scraped IDs and those already in v3 files, then
        feed each missing ID directly into parse_app_details().
        """
        all_scraped = self._load_all_scraped_ids()
        already_in_v3 = self._load_v3_app_ids()
        missing = all_scraped - already_in_v3

        self.logger.info(
            f"Rescrape: {len(all_scraped)} total IDs in txt, "
            f"{len(already_in_v3)} already in v3 files, "
            f"{len(missing)} to rescrape."
        )

        for app_id in missing:
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
                    "tag_name": "Rescrape",
                    "tag_id": 0,
                    "item_type": "game",
                    "parent_app_id": None,
                },
                dont_filter=False,
            )
