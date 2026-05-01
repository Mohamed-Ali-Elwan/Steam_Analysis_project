# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html

"""
SplitJsonPipeline
=================
Routes each Scrapy item type into its own JSON Lines file:
  - GameItem   → output/games_data.json
  - DlcItem    → output/dlcs_data.json
  - ReviewItem → output/reviews_data.json

Each file is JSONL (one JSON object per line) for efficient streaming
into downstream data pipelines.
"""

import os
import json

from itemadapter import ItemAdapter
from SteamScrapper.items import (
    GameItem, DlcItem, ReviewItem,
    GameExtraItem, ReviewTimestampItem,
)


class SplitJsonPipeline:
    """
    Custom pipeline that writes GameItem, DlcItem, and ReviewItem
    to three separate JSON files.

    Output format: JSON Lines (JSONL). One JSON object per line.
    Files are created in the project root under an 'output/' directory.
    """

    OUTPUT_DIR = "output"

    FILE_MAP = {
        "GameItem":              "games_data_v3.json",
        "DlcItem":               "dlcs_data_v3.json",
        "ReviewItem":            "reviews_data_v3.json",
        "GameExtraItem":         "games_extra_v3.json",
        "ReviewTimestampItem":   "reviews_timestamps_v3.json",
    }

    def open_spider(self, spider):
        """Create output directory and open all three file handles."""
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)

        self._files = {}

        for item_type, filename in self.FILE_MAP.items():
            filepath = os.path.join(self.OUTPUT_DIR, filename)
            self._files[item_type] = open(filepath, "a", encoding="utf-8")

        spider.logger.info(
            f"SplitJsonPipeline: writing to {self.OUTPUT_DIR}/ "
            f"({', '.join(self.FILE_MAP.values())})"
        )

    def close_spider(self, spider):
        """Close all files."""
        for item_type, fh in self._files.items():
            fh.close()

    def process_item(self, item, spider):
        """Route each item to the correct file based on its class."""
        adapter = ItemAdapter(item)
        item_dict = adapter.asdict()

        class_name = type(item).__name__

        if class_name in self._files:
            line = json.dumps(item_dict, ensure_ascii=False)
            self._files[class_name].write(line + "\n")
            self._files[class_name].flush()
        else:
            spider.logger.warning(
                f"SplitJsonPipeline: unknown item type '{class_name}', skipping."
            )

        return item


class IncrementalScrapingPipeline:
    """
    Tracks successfully scraped app_ids in a persistent file
    (scraped_app_ids.txt). The spider reads this file at startup
    to skip already-scraped games.

    This pipeline appends new app_ids AFTER they have been
    successfully processed through all other pipelines.
    """

    TRACKING_FILE = "scraped_app_ids.txt"

    def open_spider(self, spider):
        """Load existing scraped IDs and open file for appending."""
        self._seen_ids = set()

        if os.path.exists(self.TRACKING_FILE):
            with open(self.TRACKING_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._seen_ids.add(line)

        spider.logger.info(
            f"IncrementalScrapingPipeline: loaded {len(self._seen_ids)} "
            f"previously scraped app IDs from {self.TRACKING_FILE}"
        )

        # Share the set with the spider so it can skip known IDs
        spider.scraped_app_ids = self._seen_ids

        # Open for appending new IDs
        self._tracking_fh = open(self.TRACKING_FILE, "a", encoding="utf-8")

    def close_spider(self, spider):
        """Close the tracking file."""
        self._tracking_fh.close()

    def process_item(self, item, spider):
        """Record the app_id of every GameItem and DlcItem that passes through."""
        if isinstance(item, (GameItem, DlcItem)):
            adapter = ItemAdapter(item)
            app_id = str(adapter.get("app_id", ""))
            if app_id and app_id not in self._seen_ids:
                self._seen_ids.add(app_id)
                self._tracking_fh.write(f"{app_id}\n")
                self._tracking_fh.flush()

        return item
