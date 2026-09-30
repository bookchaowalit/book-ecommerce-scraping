# Upgrade plan — book-ecommerce-scraping

## Current state

Score: **8/10** (pass 1: 4 -> 7; pass 2: 7 -> 7.5; pass 3: 7.5 -> 8) — one bounded,
fixture-tested Kaidee collector with polite fetching, minimal redacted raw
captures, single-pass filtering, lint and offline CI. No dead legacy modules.

## Backlog

### P0
- (none open)

### P1
- A second marketplace source (e.g. an official Shopee/Lazada affiliate or
  product API) only if a downstream product needs it; fixture test first.

### P2
- Add category-page URLs to `JOBS` (bounded by `MAX_PAGES`) once the downstream
  marketplace product needs them.
- Add a conditional GET/ETag cache.
- Extract `http.py` + `atomic_io.py` into a small shared package once a third
  scraper repo needs them (today they are hand-synced with
  book-restaurant-scraping).

## Done in this pass (pass 1)
- `ecommerce/http.py`: identifying UA, 30 s timeout, bounded retry with
  backoff for 429/5xx/timeouts only, capped `Retry-After`; 2 s page spacing.
- Raw Kaidee payloads are redacted of seller/user personal data before write.
- A malformed listing card (bad id/timestamp) is skipped instead of aborting
  the page.
- `run_marketplace.py`: job failures reported by exception class; exit 1.
- Tests 5 -> 14; added ruff, pytest config, CI; README entry points fixed;
  untracked committed `__pycache__`.

## Done in this pass (pass 2)
- Removed `ecommerce/shopee_scraper.py` (actually a Notebookspec news RSS
  reader) and `ecommerce/lazada_scraper.py` (an older Kaidee scraper superseded
  by `kaidee_scraper.py`); both imported the retired monorepo `adapters`.
- Category/price filters now pass through `fetch_pages` -> `parse_html` once;
  the duplicate loop in `KaideeScraper.run` is gone and the 200-row cap counts
  matching rows only.
- Raw capture keeps only `__NEXT_DATA__` listing arrays (`listing_slices`)
  before redaction. Tests 14 -> 16.

## Done in this pass (pass 3)
- `ecommerce/http.py`: `Retry-After` HTTP-dates honoured (capped, never
  negative; unparseable values fall back to backoff). Kept byte-identical to
  book-restaurant-scraping except the UA; docstring records the sync rule.
- `ecommerce/atomic_io.py`: raw JSON and snapshot CSV written atomically;
  history "append" rewrites old + new atomically (no torn final row, repairs a
  missing trailing newline).
- `run_marketplace.main(argv)` is testable and rejects an `--output-dir` that
  is a file. Tests 16 -> 25.
- Numeric edge cases: `_price_value` read "1.234,56" as 1.23456 and "12,50"
  as 1250 (commas stripped blindly); it now picks the decimal separator
  (`_parse_grouped_number`) and maps Thai digits to ASCII. `min_price` /
  `max_price` of "nan"/"inf" are rejected (NaN silently disabled the filter).
  `_listing_id` requires ASCII digits ("๑๒๓" became a listing ID).
  `_retry_after_seconds` crashed on a `Retry-After: ²` header ("²".isdigit()
  is True, float() is not); it now falls back to backoff. Regression tests
  in `tests/test_kaidee_scraper.py` and `tests/test_http.py`.
