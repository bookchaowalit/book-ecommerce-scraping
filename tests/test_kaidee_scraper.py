import asyncio
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ecommerce.kaidee_scraper import (
    KaideeScraper,
    canonical_url,
    fetch_pages,
    listing_slices,
    parse_html,
    redact_personal_data,
)


FIXTURE = Path(__file__).parent / "fixtures" / "kaidee_home.html"


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class KaideeScraperTests(unittest.TestCase):
    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_canonical_url_rejects_off_site_and_strips_tracking(self):
        self.assertEqual(
            canonical_url("/product-12345?utm_source=test"),
            "https://www.kaidee.com/product-12345",
        )
        with self.assertRaises(ValueError):
            canonical_url("https://example.com/product-12345")

    def test_parse_html_deduplicates_and_requires_positive_price(self):
        payload, rows = parse_html(self.html)

        self.assertIn("props", payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["listing_id"], "12345")
        self.assertEqual(rows[0]["price_thb"], 125000.0)
        self.assertEqual(rows[0]["url"], "https://www.kaidee.com/product-12345")

        _, filtered = parse_html(self.html, categories=["บ้าน"])
        self.assertEqual([row["listing_id"] for row in filtered], ["67890"])

    def test_run_writes_raw_snapshot_and_history(self):
        html = self.html
        with tempfile.TemporaryDirectory() as temp_dir:
            scraper = KaideeScraper(urls=["https://www.kaidee.com/"], output_dir=temp_dir)
            with patch("ecommerce.http.httpx.get", return_value=FakeResponse(html)):
                result = asyncio.run(scraper.run())

            self.assertEqual(result[0]["source"], "kaidee_classifieds")
            self.assertEqual(result[0]["count"], 2)
            output_dir = Path(temp_dir)
            self.assertTrue((output_dir / "kaidee_classifieds_raw.json").exists())
            with (output_dir / "kaidee_classifieds.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["category"], "บ้าน")
            with (output_dir / "kaidee_classifieds_history.csv").open(newline="", encoding="utf-8") as handle:
                history = list(csv.DictReader(handle))
            self.assertEqual(len(history), 2)
            raw = json.loads((output_dir / "kaidee_classifieds_raw.json").read_text(encoding="utf-8"))
            self.assertIn("pages", raw)

    def test_raw_capture_drops_seller_personal_data(self):
        payload = {
            "props": {
                "pageProps": {
                    "latestAds": [
                        {
                            "id": 1,
                            "title": "Bike",
                            "member": {"role": "private", "name": "Somchai", "phone": "0812345678", "id": 99},
                            "contact": {"phoneNumber": "0812345678", "lineId": "somchai"},
                        }
                    ],
                    "currentUser": {"email": "someone@example.com"},
                }
            }
        }
        redacted = redact_personal_data(payload)
        ad = redacted["props"]["pageProps"]["latestAds"][0]
        self.assertEqual(ad["member"], {"role": "private"})
        self.assertEqual(ad["contact"], {})
        self.assertEqual(redacted["props"]["pageProps"]["currentUser"], {})
        self.assertEqual(ad["title"], "Bike")
        self.assertNotIn("0812345678", json.dumps(redacted))
        # The input payload is not mutated.
        self.assertEqual(payload["props"]["pageProps"]["latestAds"][0]["member"]["name"], "Somchai")

    def test_malformed_cards_are_skipped_not_fatal(self):
        next_data = {
            "props": {
                "pageProps": {
                    "latestAds": [
                        {"id": "abc", "title": "Bad id", "price": 10},
                        {"id": 5, "title": "Bad time", "price": 10, "firstApprovedTime": "yesterday"},
                        {"id": 6, "title": "No price", "price": None},
                        {"id": 7, "title": "Good", "price": "1,500 บาท", "firstApprovedTime": "2026-09-01T00:00:00Z"},
                    ]
                }
            }
        }
        html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script>'
        _payload, rows = parse_html(html)
        self.assertEqual([row["listing_id"] for row in rows], ["7"])
        self.assertEqual(rows[0]["price_thb"], 1500.0)
        with self.assertRaises(ValueError):
            parse_html("<html>no next data</html>")

    def test_fetch_pages_spaces_requests(self):
        sleeps = []
        with patch("ecommerce.http.httpx.get", return_value=FakeResponse(self.html)) as get:
            _raw, rows = fetch_pages(
                ["https://www.kaidee.com/", "https://www.kaidee.com/c1-auto"], sleep=sleeps.append
            )
        self.assertEqual(get.call_count, 2)
        self.assertEqual(sleeps, [2.0])
        self.assertEqual(len(rows), 2)

    def test_raw_capture_keeps_only_listing_slices(self):
        payload = {
            "buildId": "x",
            "props": {
                "pageProps": {
                    "latestAds": [{"id": 1}],
                    "navigation": {"menu": [1, 2]},
                    "session": {"token": "secret"},
                    "homepageData": {"recommendListing": [{"id": 2}], "banners": [{"img": "b"}]},
                }
            },
        }
        self.assertEqual(
            listing_slices(payload),
            {"latestAds": [{"id": 1}], "homepageData": {"recommendListing": [{"id": 2}]}},
        )
        self.assertEqual(listing_slices({"props": None}), {})

    def test_run_applies_filters_once_through_fetch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scraper = KaideeScraper(urls=["https://www.kaidee.com/"], categories="บ้าน", output_dir=temp_dir)
            with patch("ecommerce.http.httpx.get", return_value=FakeResponse(self.html)):
                result = asyncio.run(scraper.run())
            self.assertEqual(result[0]["count"], 1)
            raw = json.loads((Path(temp_dir) / "kaidee_classifieds_raw.json").read_text(encoding="utf-8"))
            page = raw["pages"]["https://www.kaidee.com/"]
            self.assertNotIn("props", page)

            too_expensive = KaideeScraper(urls=["https://www.kaidee.com/"], min_price=10**9, output_dir=temp_dir)
            with patch("ecommerce.http.httpx.get", return_value=FakeResponse(self.html)):
                with self.assertRaisesRegex(ValueError, "after configured filters"):
                    asyncio.run(too_expensive.run())


class NumericEdgeCaseTests(unittest.TestCase):
    def test_price_separators_and_thai_digits(self):
        from ecommerce.kaidee_scraper import _price_value

        cases = {
            "฿1,299": 1299.0,
            "1,299.50 บาท": 1299.5,
            "1.234,56": 1234.56,
            "12,50": 12.5,
            "1.234.567": 1234567.0,
            "๑,๒๙๙": 1299.0,
        }
        for raw, expected in cases.items():
            self.assertEqual(_price_value(raw), expected, raw)

    def test_non_finite_price_bounds_are_rejected(self):
        for bound in ("nan", "inf"):
            with self.assertRaises(ValueError):
                KaideeScraper(urls=["https://www.kaidee.com/"], min_price=bound)

    def test_listing_id_must_be_ascii_digits(self):
        from ecommerce.kaidee_scraper import _listing_id

        self.assertEqual(_listing_id(123), "123")
        for raw in ("๑๒๓", "\u00b2"):
            with self.assertRaises(ValueError):
                _listing_id(raw)


if __name__ == "__main__":
    unittest.main()
