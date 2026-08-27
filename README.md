# book-ecommerce-scraping

**Tier:** C / tool prototype (portfolio breadth, not interview flagship)  
**Owner path:** `bookchaowalit/book-apps/tools/book-ecommerce-scraping`

## Purpose

Prototype scrapers for public e-commerce listing pages (Shopee/Lazada style modules).

## Entry points

- `ecommerce/shopee_scraper.py, ecommerce/lazada_scraper.py`

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
