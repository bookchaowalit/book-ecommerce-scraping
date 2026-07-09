#!/usr/bin/env python3
"""
Kaidee classifieds scraper — extracts from __NEXT_DATA__ JSON.
Replaces the dead Lazada scraper with working classifieds data.

Data: 8+ items per run from homepage latestAd with title, price, location, contact info
"""

import asyncio
import csv
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import httpx
from adapters.outbound.engines.base import BaseScraper

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent.parent / "data"

HOMEPAGE_URL = "https://www.kaidee.com/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.8",
}


def extract_next_data(html: str) -> Optional[dict]:
    """Extract __NEXT_DATA__ JSON from HTML."""
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>({.*?})</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def parse_listing(item: dict) -> dict:
    """Parse a classified listing from Kaidee data."""
    if not item:
        return {}

    contact_info = item.get("contactInfo", {}) or {}
    
    return {
        "title": item.get("title", ""),
        "price": item.get("price"),
        "location": item.get("location", ""),
        "category": item.get("categoryName", ""),
        "condition": item.get("conditionName", ""),
        "image": item.get("image", ""),
        "contact_chat": contact_info.get("chat", ""),
        "contact_phone": contact_info.get("phone", ""),
        "contact_email": contact_info.get("email", ""),
        "contact_line": contact_info.get("line", ""),
        "member_id": item.get("memberId", ""),
        "ad_id": item.get("id", ""),
        "approved_time": item.get("firstApprovedTime", ""),
        "url": f"https://www.kaidee.com/post/{item.get('id', '')}",
    }


class KaideeScraper(BaseScraper):
    """Scrape classified listings from Kaidee using embedded JSON."""

    def __init__(self, **kwargs):
        super().__init__(
            name="kaidee",
            rate_limit=kwargs.get("rate_limit", 3.0),
            max_retries=3,
            timeout=30.0,
        )

    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch a page with retries."""
        await self._wait_for_rate_limit()
        self.stats["requests"] += 1

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                    resp = await client.get(url, headers=HEADERS)
                    if resp.status_code >= 400:
                        logger.warning(f"[HTTP {resp.status_code}] {url}")
                        continue
                    self.stats["misses"] += 1
                    return resp.text
            except Exception as e:
                logger.error(f"[ERROR] {url}: {e} (attempt {attempt+1})")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        self.stats["errors"] += 1
        return None

    def parse_page(self, html: str) -> List[dict]:
        """Extract listings from __NEXT_DATA__ JSON."""
        data = extract_next_data(html)
        if not data:
            logger.warning("No __NEXT_DATA__ found in page")
            return []

        # Navigate to latestAd array
        props = data.get("props", {})
        page_props = props.get("pageProps", {})
        latest_ads = page_props.get("latestAd", [])

        if not latest_ads:
            logger.warning("No latestAd data found")
            return []

        results = []
        for item in latest_ads:
            listing = parse_listing(item)
            if listing.get("title"):
                results.append(listing)

        return results

    async def run(self, **kwargs):
        """Run scraper for homepage latest ads."""
        logger.info("Scraping Kaidee homepage for latest classifieds...")

        html = await self.fetch_page(HOMEPAGE_URL)
        if not html:
            logger.error("Failed to fetch Kaidee homepage")
            return []

        items = self.parse_page(html)
        for item in items:
            self.add_result(item)

        logger.info(f"Found {len(items)} classified listings")

        self.print_stats()
        self.export_csv("kaidee_listings.csv")
        self.export_json("kaidee_listings.json")

        # Also save to data/ directory for dashboard
        if self.results:
            save_results(self.results, OUTPUT_DIR)

        return self.results


def save_results(results: list, output_dir: Path):
    """Save results to data/ directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "title", "price", "location", "category", "condition",
        "contact_chat", "contact_phone", "contact_email", "contact_line",
        "member_id", "ad_id", "approved_time", "url", "image", "scraped_at",
    ]

    # Current snapshot
    csv_path = output_dir / "kaidee_listings.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    # History append
    history_path = output_dir / "kaidee_history.csv"
    file_exists = history_path.exists()
    with open(history_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        now = datetime.now().isoformat()
        for r in results:
            row = {**r, "scraped_at": now}
            writer.writerow(row)

    logger.info(f"Saved {len(results)} listings to {csv_path}")


async def main():
    scraper = KaideeScraper()
    results = await scraper.run()
    print(f"\nTotal listings scraped: {len(results)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
