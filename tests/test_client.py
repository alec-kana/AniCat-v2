import unittest
from typing import Any, ClassVar, cast

import requests

from anicat.client import API_URL, Anime1Client
from anicat.errors import AccessDeniedError, FetchError
from anicat.pacing import RateLimiter


class FakeResponse:
    status_code = 200
    text = "{}"
    headers: ClassVar[dict[str, str]] = {}

    def raise_for_status(self) -> None:
        return None

    def close(self) -> None:
        return None


class DeniedResponse:
    status_code = 403
    text = ""

    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}
        self.closed = False

    def raise_for_status(self) -> None:
        raise AssertionError("a denial should be classified before raise_for_status")

    def close(self) -> None:
        self.closed = True


class ThrottledResponse:
    status_code = 429
    text = ""

    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        raise requests.HTTPError("429 Too Many Requests")

    def close(self) -> None:
        return None


class FakeSession:
    def __init__(self, responses: list[Any] | None = None) -> None:
        self.calls = []
        self.responses = responses
        self.closed = False

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append((method, url, kwargs))
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse()

    def close(self) -> None:
        self.closed = True


def request_headers(session: FakeSession, index: int = 0) -> dict[str, str]:
    """Return the headers sent on one recorded request."""

    return session.calls[index][2]["headers"]


class ClientTests(unittest.TestCase):
    def test_post_api_sends_raw_form_body_without_double_encoding(self):
        session = FakeSession()
        client = Anime1Client(session=cast(Any, session))

        client.post_api("%7B%22c%22%3A%221846%22%7D")

        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, API_URL)
        self.assertEqual(kwargs["data"], "d=%7B%22c%22%3A%221846%22%7D")
        self.assertEqual(
            kwargs["headers"]["Content-Type"],
            "application/x-www-form-urlencoded",
        )

    def test_get_page_uses_get_method(self):
        session = FakeSession()
        client = Anime1Client(session=cast(Any, session))

        client.get_page("https://anime1.pw/349")

        method, url, _ = session.calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(url, "https://anime1.pw/349")

    def test_stream_video_uses_client_timeout(self):
        session = FakeSession()
        client = Anime1Client(session=cast(Any, session), timeout=(1.0, 2.0))

        client.stream_video("https://cdn.example/demo.mp4", cookies={})

        _, _, kwargs = session.calls[0]
        self.assertEqual(kwargs["timeout"], (1.0, 2.0))

    def test_request_honors_explicit_falsy_timeout(self):
        session = FakeSession()
        client = Anime1Client(session=cast(Any, session), timeout=(1.0, 2.0))

        client.request("GET", "https://anime1.me/1", timeout=0)

        _, _, kwargs = session.calls[0]
        self.assertEqual(kwargs["timeout"], 0)

    def test_close_releases_session(self):
        session = FakeSession()

        with Anime1Client(session=cast(Any, session)):
            pass

        self.assertTrue(session.closed)


class RequestIdentityTests(unittest.TestCase):
    def test_stream_video_sends_the_episode_page_referer(self):
        session = FakeSession()
        client = Anime1Client(session=cast(Any, session))

        client.stream_video(
            "https://v.anime1.me/2024/demo.mp4",
            cookies={"e": "1"},
            page_url="https://anime1.me/29592",
        )

        headers = request_headers(session)
        self.assertEqual(headers["Referer"], "https://anime1.me/")
        self.assertEqual(headers["Sec-Fetch-Dest"], "video")
        self.assertEqual(headers["Sec-Fetch-Site"], "same-site")

    def test_post_api_sends_the_episode_page_origin(self):
        session = FakeSession()
        client = Anime1Client(session=cast(Any, session))

        client.post_api("%7B%7D", page_url="https://anime1.me/29592")

        headers = request_headers(session)
        self.assertEqual(headers["Origin"], "https://anime1.me")
        self.assertEqual(headers["Referer"], "https://anime1.me/")
        self.assertEqual(headers["Sec-Fetch-Mode"], "cors")

    def test_page_requests_reference_the_site_root(self):
        session = FakeSession()
        client = Anime1Client(session=cast(Any, session))

        client.post_page("https://anime1.me/category/demo")

        headers = request_headers(session)
        self.assertEqual(headers["Referer"], "https://anime1.me/")
        self.assertEqual(headers["Sec-Fetch-Site"], "same-origin")
        self.assertEqual(headers["Sec-Fetch-Dest"], "document")

    def test_caller_headers_win_over_computed_identity(self):
        session = FakeSession()
        client = Anime1Client(session=cast(Any, session))

        client.stream_video(
            "https://v.anime1.me/2024/demo.mp4",
            cookies={},
            headers={"Referer": "https://anime1.me/1"},
            page_url="https://anime1.me/29592",
        )

        self.assertEqual(request_headers(session)["Referer"], "https://anime1.me/1")


class DenialTests(unittest.TestCase):
    def test_403_is_raised_immediately_without_resending_the_request(self):
        denied = DeniedResponse({"Server": "nginx"})
        session = FakeSession([denied])
        client = Anime1Client(session=cast(Any, session), retries=3, backoff=0)

        with self.assertRaises(AccessDeniedError) as caught:
            client.stream_video("https://v.anime1.me/demo.mp4", cookies={"e": "1"})

        self.assertEqual(len(session.calls), 1)
        self.assertEqual(caught.exception.status_code, 403)
        self.assertFalse(caught.exception.bot_mitigation)
        self.assertTrue(denied.closed)

    def test_403_from_a_mitigation_edge_is_classified_as_a_block(self):
        session = FakeSession([DeniedResponse({"cf-mitigated": "challenge"})])
        client = Anime1Client(session=cast(Any, session), retries=1, backoff=0)

        with self.assertRaises(AccessDeniedError) as caught:
            client.get_page("https://anime1.me/1")

        self.assertTrue(caught.exception.bot_mitigation)

    def test_denial_carries_retry_after(self):
        session = FakeSession([DeniedResponse({"Retry-After": "30"})])
        client = Anime1Client(session=cast(Any, session), retries=0)

        with self.assertRaises(AccessDeniedError) as caught:
            client.get_page("https://anime1.me/1")

        self.assertEqual(caught.exception.retry_after, 30.0)

    def test_denial_logs_context_without_leaking_cookie_values(self):
        session = FakeSession([DeniedResponse({"Server": "nginx", "cf-ray": "abc123"})])
        client = Anime1Client(session=cast(Any, session), retries=0)

        with self.assertLogs("anicat.client", level="INFO") as logs:
            with self.assertRaises(AccessDeniedError):
                client.stream_video(
                    "https://v.anime1.me/demo.mp4",
                    cookies={"e": "secret-token", "p": "2", "h": "3"},
                    page_url="https://anime1.me/29592",
                )

        rejection = logs.output[0]
        self.assertIn("cookies=[e,h,p]", rejection)
        self.assertIn("abc123", rejection)
        self.assertIn("https://anime1.me/", rejection)
        self.assertNotIn("secret-token", "".join(logs.output))


class RetryPacingTests(unittest.TestCase):
    def test_retry_sleeps_are_jittered_rather_than_fixed(self):
        delays: list[float] = []
        for _ in range(20):
            session = FakeSession([ThrottledResponse(), FakeResponse()])
            client = Anime1Client(
                session=cast(Any, session),
                retries=1,
                backoff=1.0,
                sleeper=delays.append,
            )
            client.get_page("https://anime1.me/1")

        self.assertGreater(len(set(delays)), 1)
        self.assertTrue(all(0.0 <= delay <= 1.0 for delay in delays))

    def test_retry_after_header_overrides_backoff(self):
        delays: list[float] = []
        session = FakeSession([ThrottledResponse({"Retry-After": "7"}), FakeResponse()])
        client = Anime1Client(
            session=cast(Any, session),
            retries=1,
            backoff=1.0,
            sleeper=delays.append,
        )

        client.get_page("https://anime1.me/1")

        self.assertEqual(delays, [7.0])

    def test_rate_limiter_gates_every_request(self):
        waits: list[float] = []
        limiter = RateLimiter(2.0, sleeper=waits.append, clock=lambda: 0.0)
        session = FakeSession()
        client = Anime1Client(session=cast(Any, session), rate_limiter=limiter)

        client.get_page("https://anime1.me/1")
        client.get_page("https://anime1.me/2")

        self.assertEqual(waits, [2.0])

    def test_exhausted_retries_raise_fetch_error(self):
        session = FakeSession([ThrottledResponse(), ThrottledResponse()])
        client = Anime1Client(session=cast(Any, session), retries=1, backoff=0)

        with self.assertRaises(FetchError):
            client.get_page("https://anime1.me/1")


if __name__ == "__main__":
    unittest.main()
