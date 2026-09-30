# book-ecommerce-scraping

**Tier:** C / tool prototype (portfolio breadth, not interview flagship)  
**Owner path:** `bookchaowalit/book-apps/tools/book-ecommerce-scraping`

## Purpose

Prototype scrapers for public e-commerce listing pages (Shopee/Lazada style modules).

## Entry points

- `scripts/run_marketplace.py` -> `ecommerce/kaidee_scraper.py` (active, bounded Kaidee collector)
- `ecommerce/shopee_scraper.py`, `ecommerce/lazada_scraper.py` (legacy prototypes; they import the old
  monorepo `adapters` package and do not run from a standalone checkout)

## Stack

Python

## How to run (local)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 scripts/run_marketplace.py
bash setup_cron.sh install   # optional; every 6 hours
```

Kaidee is the active bounded collector. Shopee/Lazada modules remain prototypes.
Output stays in this repository's `data/exported/`.

## Polite collection and privacy

`ecommerce/http.py` is the only network path: an identifying `User-Agent`
(`book-ecommerce-scraping/1.0`), a 30 s timeout, and at most three attempts
with exponential backoff that retry only timeouts, connection errors, HTTP 429
(honouring `Retry-After`, capped at 60 s) and 5xx; 403/404 fail at once.
Kaidee pages (max 5 per run, 200 rows) are spaced 2 s apart. A malformed
listing card is skipped instead of failing the whole page.

Kaidee lists private sellers. Snapshot rows keep only `seller_role`, and the
raw `__NEXT_DATA__` capture is passed through `redact_personal_data` first:
seller/member/user objects keep only `role`, and phone, email, LINE ID, name,
address and session/token keys are dropped anywhere in the payload.
`scripts/run_marketplace.py` reports a failed job as `{"job": ...,
"error": "<ExceptionClass>"}` and exits 1.

## Checks (offline)

```bash
pip install -r requirements.txt pytest ruff
ruff check .
python -m pytest -q
python3 scripts/run_marketplace.py --dry-run --json   # plan only, no network
```

Tests replay `tests/fixtures/` and mock the HTTP layer; CI
(`.github/workflows/ci.yml`) runs the same commands.

## Boundaries

- **Not** a lake-first data product. Durable market datasets live under `book-*-data` repos.
- **Not** coupled to Solo Empire monorepo runtime. Nested Git repo; commit only inside this tree.
- Never commit `.env`, cookies, session dumps, or scraped PII dumps to Git.

## Limitations (honest)

Marketplace ToS often forbid scraping. Treat as learning/prototype code only; no secrets; no mass commercial harvest claims.

## Related

- Active collection product: `book-job-scraping` (Tier A tool)
- Lake products: `book-crypto-data`, `book-fx-data`, `book-stock-data`, …
- Solo Empire catalog: `repository-catalog/BOOK-DEV-BACKLOG-BD.md` (BD-012)
