"""Offline tests for the shared polite fetch helper."""

import unittest
from unittest.mock import patch

import httpx

from datetime import datetime, timezone

from ecommerce.http import USER_AGENT, FetchError, _retry_after_seconds, polite_get

URL = "https://site.example/page"


def _response(status: int, content: bytes = b"<html></html>", headers=None) -> httpx.Response:
    return httpx.Response(status, content=content, headers=headers or {}, request=httpx.Request("GET", URL))


class PoliteGetTests(unittest.TestCase):
    def test_success_sends_identifying_user_agent_and_timeout(self):
        with patch("ecommerce.http.httpx.get", return_value=_response(200)) as get:
            response = polite_get(URL, source="Demo", sleep=lambda _s: None)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get.call_args.kwargs["headers"]["User-Agent"], USER_AGENT)
        self.assertEqual(get.call_args.kwargs["timeout"], 30.0)

    def test_retries_transient_status_honouring_retry_after(self):
        sleeps: list[float] = []
        responses = [_response(503), _response(429, headers={"Retry-After": "5"}), _response(200)]
        with patch("ecommerce.http.httpx.get", side_effect=responses) as get:
            polite_get(URL, source="Demo", sleep=sleeps.append)
        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleeps, [2.0, 5.0])

    def test_gives_up_after_bounded_timeouts(self):
        sleeps: list[float] = []
        with patch("ecommerce.http.httpx.get", side_effect=httpx.ConnectTimeout("slow")) as get:
            with self.assertRaises(FetchError):
                polite_get(URL, source="Demo", attempts=3, sleep=sleeps.append)
        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleeps, [2.0, 4.0])

    def test_permanent_client_error_is_not_retried(self):
        with patch("ecommerce.http.httpx.get", return_value=_response(403)) as get:
            with self.assertRaises(httpx.HTTPStatusError):
                polite_get(URL, source="Demo", sleep=lambda _s: None)
        self.assertEqual(get.call_count, 1)

    def test_retry_after_is_capped_and_empty_body_rejected(self):
        sleeps: list[float] = []
        responses = [_response(429, headers={"Retry-After": "3600"}), _response(200)]
        with patch("ecommerce.http.httpx.get", side_effect=responses):
            polite_get(URL, source="Demo", sleep=sleeps.append)
        self.assertEqual(sleeps, [60.0])
        with patch("ecommerce.http.httpx.get", return_value=_response(200, content=b"")):
            with self.assertRaises(ValueError):
                polite_get(URL, source="Demo", sleep=lambda _s: None)

    def test_retry_after_http_date_is_honoured_and_capped(self):
        now = lambda: datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)  # noqa: E731
        date = {"Retry-After": "Wed, 30 Sep 2026 12:00:07 GMT"}
        self.assertEqual(_retry_after_seconds(_response(503, headers=date), 2.0, now), 7.0)
        far = {"Retry-After": "Thu, 01 Oct 2026 12:00:00 GMT"}
        self.assertEqual(_retry_after_seconds(_response(503, headers=far), 2.0, now), 60.0)
        past = {"Retry-After": "Tue, 29 Sep 2026 12:00:00 GMT"}
        self.assertEqual(_retry_after_seconds(_response(503, headers=past), 2.0, now), 0.0)

    def test_unparseable_retry_after_falls_back_to_backoff(self):
        for value in ("soon", "-5", "1.5"):
            response = _response(429, headers={"Retry-After": value})
            self.assertEqual(_retry_after_seconds(response, 4.0), 4.0)

    def test_attempts_must_be_positive(self):
        with patch("ecommerce.http.httpx.get") as get:
            with self.assertRaises(ValueError):
                polite_get(URL, source="Demo", attempts=0)
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
