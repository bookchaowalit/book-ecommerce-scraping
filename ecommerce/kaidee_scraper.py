#!/usr/bin/env python3
"""Capture bounded Kaidee marketplace listings from server-rendered HTML.

Kaidee does not expose a source-specific API in this workflow, so this adapter
uses the public HTML page and its embedded ``__NEXT_DATA__`` payload. This repo
is the collection producer; the downstream marketplace data product owns
durable lake ingestion and APIs.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

try:
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover - requirements.txt supplies both
    raise RuntimeError("httpx and beautifulsoup4 are required for Kaidee capture") from exc

from ecommerce.atomic_io import append_csv_atomic, render_csv, write_text_atomic
from ecommerce.http import PAGE_DELAY_SECONDS, polite_get


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "exported"
SOURCE_URL = "https://www.kaidee.com/"
MAX_PAGES = 5
MAX_ROWS = 200
LISTING_ID_RE = re.compile(r"(?:product|ad)[-_](\d+)", re.IGNORECASE)
PRICE_RE = re.compile(r"[0-9]+(?:[,.][0-9]+)*")
ALLOWED_HOST = re.compile(r"(?:[a-z0-9-]+\.)*kaidee\.com", re.IGNORECASE)
SNAPSHOT_FIELDS = [
    "captured_at",
    "listing_id",
    "title",
    "price_thb",
    "currency",
    "purpose",
    "category",
    "condition",
    "location",
    "url",
    "image_url",
    "seller_role",
    "first_approved_at",
    "source_url",
]
HISTORY_FIELDS = ["captured_at", "listing_id", "price_thb", "category", "location", "url"]
# Seller/member objects are reduced to these keys in raw captures; everything
# else (names, phone numbers, LINE IDs, avatars, member IDs) is dropped.
MEMBER_KEYS_KEPT = frozenset({"role"})
PERSONAL_KEYS = frozenset(
    {
        "phone",
        "phonenumber",
        "phoneno",
        "mobile",
        "tel",
        "telephone",
        "email",
        "lineid",
        "line_id",
        "contactname",
        "contact_name",
        "sellername",
        "seller_name",
        "firstname",
        "lastname",
        "fullname",
        "address",
        "accesstoken",
        "access_token",
        "refreshtoken",
        "cookie",
        "cookies",
        "session",
    }
)
PERSON_CONTAINERS = frozenset({"member", "seller", "user", "owner", "currentuser", "profile"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_values(values: Iterable[str] | str | None, default: list[str]) -> list[str]:
    if values is None:
        values = default
    if isinstance(values, str):
        values = values.split(",")
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def canonical_url(value: str, base_url: str = SOURCE_URL) -> str:
    """Normalize a Kaidee listing URL and reject off-site destinations."""

    candidate = urljoin(base_url, str(value).strip())
    parts = urlsplit(candidate)
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() != "https" or not ALLOWED_HOST.fullmatch(host):
        raise ValueError("Kaidee URL must remain on an HTTPS kaidee.com host")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, "", ""))


def normalize_urls(urls: Iterable[str] | str | None) -> list[str]:
    normalized = [canonical_url(url) for url in _as_values(urls, [SOURCE_URL])]
    if not normalized or len(normalized) > MAX_PAGES:
        raise ValueError(f"urls must contain 1-{MAX_PAGES} Kaidee pages")
    return normalized


_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def _parse_grouped_number(text: str) -> float | None:
    """Parse "1,299", "1,299.50", "1.234,56", "12,50" or "1.234.567".

    With both separators the last one is the decimal point; a single comma
    followed by one or two digits is a decimal comma; repeated separators of
    one kind are thousands groups. Plain ``float()`` on the comma-stripped
    text read "1.234,56" as 1.23456 and "12,50" as 1250.
    """

    commas, dots = text.count(","), text.count(".")
    if commas and dots:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        if text.count(decimal) > 1:
            return None
        text = text.replace(thousands, "").replace(decimal, ".")
    elif commas:
        head, _, tail = text.partition(",")
        text = f"{head}.{tail}" if commas == 1 and len(tail) in (1, 2) else text.replace(",", "")
    elif dots > 1:
        text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return None


def _price_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number: float | None = float(value)
    else:
        match = PRICE_RE.search(str(value).translate(_THAI_DIGITS).replace(" ", ""))
        if not match:
            return None
        number = _parse_grouped_number(match.group(0))
    if number is None or not math.isfinite(number) or number <= 0:
        return None
    return number


def _finite_bound(value: float | str | None, name: str) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)  # type: ignore[arg-type]
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _iso_datetime(value: Any, field: str) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO datetime string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO datetime string") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.isoformat()


def _listing_id(value: Any) -> str:
    if isinstance(value, bool) or value in (None, ""):
        raise ValueError("Kaidee listing ID is required")
    text = str(value).strip()
    if not (text.isascii() and text.isdigit()) or int(text) <= 0:
        raise ValueError("Kaidee listing ID must be a positive integer")
    return text


def redact_personal_data(value: Any) -> Any:
    """Return a copy of an embedded payload without seller/user personal data.

    Raw captures are kept as evidence of what the page looked like, but they
    must not retain private sellers' contact details or session material.
    Person-like objects keep only ``MEMBER_KEYS_KEPT``; personal keys are
    dropped anywhere in the tree.
    """

    if isinstance(value, list):
        return [redact_personal_data(item) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    for key, item in value.items():
        lowered = str(key).casefold()
        if lowered in PERSONAL_KEYS:
            continue
        if lowered in PERSON_CONTAINERS:
            if isinstance(item, dict):
                result[key] = {k: v for k, v in item.items() if k in MEMBER_KEYS_KEPT}
            continue
        result[key] = redact_personal_data(item)
    return result


def _next_data(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.select_one("#__NEXT_DATA__")
    if script is None or not script.string:
        raise ValueError("Kaidee page is missing __NEXT_DATA__")
    try:
        payload = json.loads(script.string)
    except json.JSONDecodeError as exc:
        raise ValueError("Kaidee __NEXT_DATA__ is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Kaidee __NEXT_DATA__ must be a JSON object")
    return payload


def _href_by_id(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    links: dict[str, str] = {}
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "")
        match = LISTING_ID_RE.search(href)
        if match:
            try:
                links.setdefault(match.group(1), canonical_url(href))
            except ValueError:
                continue
    return links


LISTING_KEYS = ("latestAd", "latestAds")
HOMEPAGE_LISTING_KEYS = ("recommendListing", "latestCategoryAds", "recentlyViewAds")


def listing_slices(payload: dict[str, Any]) -> dict[str, Any]:
    """Return only the listing arrays of a ``__NEXT_DATA__`` payload.

    Raw captures are evidence of the listing data that was parsed; the rest of
    the page state (navigation, session, ads config) is not kept.
    """

    props = payload.get("props")
    page_props = props.get("pageProps") if isinstance(props, dict) else None
    if not isinstance(page_props, dict):
        return {}
    kept: dict[str, Any] = {
        key: page_props[key] for key in LISTING_KEYS if isinstance(page_props.get(key), list)
    }
    homepage = page_props.get("homepageData")
    if isinstance(homepage, dict):
        home = {key: homepage[key] for key in HOMEPAGE_LISTING_KEYS if isinstance(homepage.get(key), list)}
        if home:
            kept["homepageData"] = home
    return kept


def _candidate_ads(page_props: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for key in LISTING_KEYS:
        values = page_props.get(key)
        if isinstance(values, list):
            candidates.extend(item for item in values if isinstance(item, dict))
    homepage = page_props.get("homepageData")
    if isinstance(homepage, dict):
        for key in HOMEPAGE_LISTING_KEYS:
            values = homepage.get(key)
            if isinstance(values, list):
                candidates.extend(item for item in values if isinstance(item, dict))
    return candidates


def parse_html(
    html: str,
    source_url: str = SOURCE_URL,
    categories: Iterable[str] | str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Parse embedded listing data, keeping only priced, canonical listings."""

    payload = _next_data(html)
    props = payload.get("props")
    page_props = props.get("pageProps") if isinstance(props, dict) else None
    if not isinstance(page_props, dict):
        raise ValueError("Kaidee page is missing pageProps")
    allowed_categories = {value.casefold() for value in _as_values(categories, [])}
    hrefs = _href_by_id(html)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _candidate_ads(page_props):
        try:
            listing_id = _listing_id(item.get("id"))
            first_approved_at = _iso_datetime(item.get("firstApprovedTime"), "firstApprovedTime")
        except ValueError:
            # One malformed card must not discard the rest of the page.
            continue
        if listing_id in seen:
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        category = str(item.get("categoryName") or "").strip()
        if allowed_categories and category.casefold() not in allowed_categories:
            continue
        price = _price_value(item.get("price"))
        if price is None:
            continue
        if min_price is not None and price < min_price:
            continue
        if max_price is not None and price > max_price:
            continue
        url = hrefs.get(listing_id, canonical_url(f"/product-{listing_id}", source_url))
        seen.add(listing_id)
        rows.append(
            {
                "listing_id": listing_id,
                "title": title[:500],
                "price_thb": price,
                "currency": "THB",
                "purpose": str(item.get("purposeName") or "").strip(),
                "category": category,
                "condition": str(item.get("conditionName") or "").strip(),
                "location": str(item.get("location") or "").strip(),
                "url": url,
                "image_url": str(item.get("image") or "").strip(),
                "seller_role": str((item.get("member") or {}).get("role") or "").strip()
                if isinstance(item.get("member"), dict)
                else "",
                "first_approved_at": first_approved_at,
                "source_url": canonical_url(source_url),
            }
        )
        if len(rows) >= MAX_ROWS:
            break
    return payload, rows


def fetch_pages(
    urls: list[str],
    *,
    page_delay: float = PAGE_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    categories: Iterable[str] | str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fetch pages politely and parse them with the configured filters.

    Only the listing slices of each page payload are kept in the raw capture,
    and they are redacted of personal data first.
    """

    raw_pages: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, url in enumerate(urls):
        if index and page_delay > 0:
            sleep(page_delay)
        response = polite_get(url, source="Kaidee page", sleep=sleep)
        payload, page_rows = parse_html(
            response.text, url, categories=categories, min_price=min_price, max_price=max_price
        )
        raw_pages[url] = redact_personal_data(listing_slices(payload))
        for row in page_rows:
            if row["listing_id"] not in seen:
                seen.add(row["listing_id"])
                rows.append(row)
    if not rows:
        filtered = categories or min_price is not None or max_price is not None
        raise ValueError(
            "Kaidee pages contained no listings after configured filters"
            if filtered
            else "Kaidee pages contained no priced listings"
        )
    return {"pages": raw_pages}, rows[:MAX_ROWS]


def write_raw(raw: dict[str, Any], output_dir: Path) -> Path:
    path = output_dir / "kaidee_classifieds_raw.json"
    write_text_atomic(path, json.dumps(raw, ensure_ascii=False, separators=(",", ":")))
    return path


def write_snapshot(rows: list[dict[str, Any]], captured_at: str, output_dir: Path) -> Path:
    path = output_dir / "kaidee_classifieds.csv"
    write_text_atomic(path, render_csv(({**row, "captured_at": captured_at} for row in rows), SNAPSHOT_FIELDS))
    return path


def append_history(rows: list[dict[str, Any]], captured_at: str, output_dir: Path) -> Path:
    path = output_dir / "kaidee_classifieds_history.csv"
    append_csv_atomic(path, ({**row, "captured_at": captured_at} for row in rows), HISTORY_FIELDS)
    return path


class KaideeScraper:
    """Scheduler adapter for bounded Kaidee HTML capture."""

    def __init__(
        self,
        urls: Iterable[str] | str | None = None,
        categories: Iterable[str] | str | None = None,
        min_price: float | str | None = None,
        max_price: float | str | None = None,
        output_dir: str | Path | None = None,
        **_: Any,
    ) -> None:
        self.urls = normalize_urls(urls)
        self.categories = _as_values(categories, [])
        self.min_price = _finite_bound(min_price, "min_price")
        self.max_price = _finite_bound(max_price, "max_price")
        if self.min_price is not None and self.min_price < 0:
            raise ValueError("min_price must be non-negative")
        if self.max_price is not None and self.max_price <= 0:
            raise ValueError("max_price must be greater than zero")
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price must not exceed max_price")
        self.output_dir = Path(output_dir) if output_dir else OUTPUT_DIR

    async def run(self, **_: Any) -> list[dict[str, Any]]:
        raw, filtered = fetch_pages(
            self.urls,
            categories=self.categories,
            min_price=self.min_price,
            max_price=self.max_price,
        )
        captured_at = _utc_now()
        raw_path = write_raw(raw, self.output_dir)
        snapshot_path = write_snapshot(filtered, captured_at, self.output_dir)
        history_path = append_history(filtered, captured_at, self.output_dir)
        print(f"[kaidee_classifieds] {len(filtered)} listings -> {snapshot_path}")
        return [
            {
                "source": "kaidee_classifieds",
                "count": len(filtered),
                "output": str(snapshot_path),
                "history": str(history_path),
                "raw": str(raw_path),
            }
        ]


if __name__ == "__main__":
    import asyncio

    asyncio.run(KaideeScraper().run())
