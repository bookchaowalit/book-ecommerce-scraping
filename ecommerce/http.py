"""Polite, bounded HTTP fetch shared by this repository's adapters.

Requests identify the collector with one User-Agent, use a finite timeout,
and retry only transient failures (timeouts, connection errors, HTTP 429 and
5xx) with exponential backoff. Permanent client errors such as 403/404 fail
immediately so a blocking site is not hammered. Callers space out successive
pages with ``PAGE_DELAY_SECONDS``.
"""

from __future__ import annotations

import time
from typing import Callable

import httpx

USER_AGENT = "book-ecommerce-scraping/1.0 (+https://github.com/bookchaowalit/book-ecommerce-scraping)"
HTML_ACCEPT = "text/html,application/xhtml+xml"
DEFAULT_TIMEOUT = 30.0
DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF = 2.0
MAX_RETRY_AFTER = 60.0
PAGE_DELAY_SECONDS = 2.0
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class FetchError(RuntimeError):
    """Raised when a page cannot be fetched after the bounded retries."""


def _retry_after_seconds(response: httpx.Response, fallback: float) -> float:
    headers = getattr(response, "headers", None) or {}
    raw = str(headers.get("Retry-After", "")).strip()
    if raw.isdigit():
        return min(float(raw), MAX_RETRY_AFTER)
    return fallback


def polite_get(
    url: str,
    *,
    source: str,
    accept: str = HTML_ACCEPT,
    timeout: float = DEFAULT_TIMEOUT,
    attempts: int = DEFAULT_ATTEMPTS,
    backoff: float = DEFAULT_BACKOFF,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """GET ``url`` and return a successful, non-empty response."""

    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    last_error = "unknown error"
    for attempt in range(1, attempts + 1):
        delay = backoff * (2 ** (attempt - 1))
        try:
            response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = type(exc).__name__
        else:
            status = getattr(response, "status_code", 200)
            if status in RETRYABLE_STATUS:
                last_error = f"HTTP {status}"
                delay = _retry_after_seconds(response, delay)
            else:
                response.raise_for_status()
                if not (getattr(response, "content", None) or getattr(response, "text", None)):
                    raise ValueError(f"{source} response is empty")
                return response
        if attempt < attempts:
            sleep(delay)
    raise FetchError(f"{source} fetch failed after {attempts} attempts: {last_error}")
