# book-ecommerce-scraping — Product brief

**Slug:** `bookchaowalit/book-ecommerce-scraping`  
**Generated:** 2026-08-11 (bulk Book Dev closeout)  
**Status:** collection adapter present; this repo can schedule Kaidee via `setup_cron.sh`

## Purpose

Portfolio repository under Book Dev. This brief records ownership and the
current honest status so the nested tree is not an empty shell in the task
system.

## Runnable path

See `README.md` for install and run instructions when present.

## Current adapters

- `ecommerce/kaidee_scraper.py`
- `ecommerce/shopee_scraper.py` (legacy prototype)
- `ecommerce/lazada_scraper.py` (legacy prototype)

Tests live under `tests/` for Kaidee. Runtime collection remains scheduled by
`book-job-scraping` until this repository has its own cron.

## Limits

- Not claimed as production-ready unless README and tests prove it.
- Mobile smoke / emulator acceptance is separate and toolchain-dependent.

## Source README excerpt

```
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
# From this repository root
python3 -m venv .venv && source .venv/bin/activate
# Install whatever deps the script imports (often requests/httpx/bs4).
# Prefer reading the scraper module docstring/im
```
