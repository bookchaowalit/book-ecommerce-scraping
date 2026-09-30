"""Offline tests for the shared polite fetch helper."""

import unittest
from unittest.mock import patch

import httpx

from ecommerce.http import USER_AGENT, FetchError, polite_get

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


if __name__ == "__main__":
    unittest.main()
