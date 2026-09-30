#!/usr/bin/env python3
"""Run the bounded Kaidee adapter owned by this repository."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Provider classes are loaded only for a real collection. This keeps the
# dependency-free dry-run path usable on an offline control-plane host.
JOBS = (("kaidee_classifieds", None),)


async def run_marketplace(output_dir: Path, *, dry_run: bool = False) -> list[dict[str, Any]]:
    if dry_run:
        return [
            {
                "job": name,
                "status": "dry-run",
                "source_url": "https://www.kaidee.com/",
                "network": "not-used",
                "writes": "not-used",
            }
            for name, _cls in JOBS
        ]
    results: list[dict[str, Any]] = []
    from ecommerce.kaidee_scraper import KaideeScraper

    for name, cls in JOBS:
        scraper = (cls or KaideeScraper)(urls=["https://www.kaidee.com/"], output_dir=output_dir)
        batch = await scraper.run()
        results.extend(batch)
        print(f"[run_marketplace] {name}: {batch[0].get('count') if batch else 0}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run book-ecommerce-scraping marketplace jobs")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "exported")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print the bounded job plan without collection or writes")
    args = parser.parse_args()
    results = asyncio.run(run_marketplace(args.output_dir, dry_run=args.dry_run))
    if args.json:
        print(json.dumps(results, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
