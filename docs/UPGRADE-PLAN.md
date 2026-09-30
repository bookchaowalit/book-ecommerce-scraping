# Upgrade plan — book-ecommerce-scraping

## Current state

Score: **7/10** (was 4/10) — one bounded, fixture-tested Kaidee collector with
polite fetching, raw-capture PII redaction, lint and offline CI. Shopee/Lazada
remain non-runnable legacy prototypes.

## Backlog

### P0
- (none open)

### P1
- Delete or port `ecommerce/shopee_scraper.py` and `ecommerce/lazada_scraper.py`
  (they import the missing monorepo `adapters` package). If ported, give each
  a fixture test first.
- Store only the listing slices of `__NEXT_DATA__` in the raw capture instead
  of the whole (redacted) page payload.
- `KaideeScraper.run` re-applies category/price filters that `parse_html`
  already supports; pass them through once and drop the duplicate loop.

### P2
- Add category-page URLs to `JOBS` (bounded by `MAX_PAGES`) once the downstream
  marketplace product needs them.
- Add a conditional GET/ETag cache.

## Done in this pass
- `ecommerce/http.py`: identifying UA, 30 s timeout, bounded retry with
  backoff for 429/5xx/timeouts only, capped `Retry-After`; 2 s page spacing.
- Raw Kaidee payloads are redacted of seller/user personal data before write.
- A malformed listing card (bad id/timestamp) is skipped instead of aborting
  the page.
- `run_marketplace.py`: job failures reported by exception class; exit 1.
- Tests 5 -> 14; added ruff, pytest config, CI; README entry points fixed;
  untracked committed `__pycache__`.
