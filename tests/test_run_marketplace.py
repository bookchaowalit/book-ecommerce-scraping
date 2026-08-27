import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from run_marketplace import JOBS


class RunMarketplaceTests(unittest.TestCase):
    def test_job_roster(self):
        self.assertEqual([name for name, _cls in JOBS], ["kaidee_classifieds"])


if __name__ == "__main__":
    unittest.main()
