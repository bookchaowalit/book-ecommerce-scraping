import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from run_marketplace import JOBS, run_marketplace


class RunMarketplaceTests(unittest.TestCase):
    def test_job_roster(self):
        self.assertEqual([name for name, _cls in JOBS], ["kaidee_classifieds"])

    def test_dry_run_does_not_collect(self):
        with tempfile.TemporaryDirectory() as directory:
            result = asyncio.run(run_marketplace(Path(directory), dry_run=True))
        self.assertEqual(result[0]["status"], "dry-run")
        self.assertEqual(result[0]["network"], "not-used")

    def test_failed_job_reports_error_class_only(self):
        async def fake_run(self, **_kwargs):
            raise RuntimeError("page content must not leak")

        with tempfile.TemporaryDirectory() as directory:
            with patch("ecommerce.kaidee_scraper.KaideeScraper.run", fake_run):
                result = asyncio.run(run_marketplace(Path(directory)))
        self.assertEqual(result, [{"job": "kaidee_classifieds", "error": "RuntimeError"}])


if __name__ == "__main__":
    unittest.main()
