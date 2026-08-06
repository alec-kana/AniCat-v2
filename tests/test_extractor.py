import unittest
from typing import ClassVar, NoReturn, cast
from unittest.mock import patch

import requests
from bs4 import BeautifulSoup, FeatureNotFound

from anicat.errors import FetchError, ParseError
from anicat.extractor import (
    Anime1Extractor,
    extract_access_cookies,
    parse_direct_episode_page,
    parse_episode_number,
    parse_episode_page,
    parse_html,
    parse_season_page,
    parse_set_cookie_header,
    parse_stream_url,
    resolve_standalone_anime_name,
    select_series_link,
    strip_trailing_episode_number,
)


class DirectPageClient:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.get_calls: list[str] = []
        self.post_calls: list[str] = []

    def get_page(self, url: str) -> str:
        self.get_calls.append(url)
        return self.pages[url]

    def post_page(self, url: str) -> str:
        self.post_calls.append(url)
        return self.pages[url]

    def post_api(self, data_apireq: str, *, page_url: str | None = None) -> NoReturn:
        raise AssertionError("anime1.pw extraction should not call post_api")


class ApiResponseStub:
    text = "{}"
    headers: ClassVar[dict[str, str]] = {}

    def __init__(self) -> None:
        self.cookies = {"e": "1", "p": "2", "h": "3"}

    def json(self) -> dict[str, dict[str, str]]:
        return {"s": {"src": "//cdn.example/demo.mp4"}}


class Anime1MeClient:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.post_calls: list[str] = []
        self.api_page_urls: list[str | None] = []

    def post_page(self, url: str) -> str:
        self.post_calls.append(url)
        return self.pages[url]

    def get_page(self, url: str) -> NoReturn:
        raise AssertionError("anime1.me extraction should not call get_page")

    def post_api(self, data_apireq: str, *, page_url: str | None = None) -> requests.Response:
        self.api_page_urls.append(page_url)
        return cast(requests.Response, ApiResponseStub())


class ExtractorTests(unittest.TestCase):
    def test_parse_season_page_extracts_episode_and_next_urls(self):
        page = parse_season_page(
            """
            <h2 class="entry-title"><a rel="bookmark" href="/1">A</a></h2>
            <h2 class="entry-title"><a rel="bookmark" href="https://anime1.me/2">B</a></h2>
            <div class="nav-previous"><a href="/page/2">next</a></div>
            """
        )

        self.assertEqual(page.episode_urls, ["/1", "https://anime1.me/2"])
        self.assertEqual(page.next_url, "/page/2")
        self.assertIsNone(page.anime_name)
        self.assertEqual(page.episode_numbers, [None, None])

    def test_parse_season_page_extracts_anime_name(self):
        page = parse_season_page(
            """
            <h1 class="page-title">CITY THE ANIMATION</h1>
            <h2 class="entry-title"><a rel="bookmark" href="/1">A</a></h2>
            """
        )

        self.assertEqual(page.anime_name, "CITY THE ANIMATION")

    def test_parse_season_page_extracts_episode_numbers(self):
        page = parse_season_page(
            """
            <h2 class="entry-title"><a rel="bookmark" href="/15">Demo [15]</a></h2>
            <h2 class="entry-title"><a rel="bookmark" href="/16">Demo [16]</a></h2>
            <h2 class="entry-title"><a rel="bookmark" href="/sp">Demo [SP]</a></h2>
            """
        )

        self.assertEqual(page.episode_numbers, [15, 16, None])

    def test_parse_episode_number_extracts_trailing_bracket(self):
        self.assertEqual(parse_episode_number("Demo Anime [07]"), 7)
        self.assertEqual(parse_episode_number("約會大作戰 II (第二季) [01]"), 1)
        self.assertIsNone(parse_episode_number("Demo Anime [SP]"))
        self.assertIsNone(parse_episode_number("Demo Anime"))

    def test_parse_episode_page_extracts_api_request_and_title(self):
        data_apireq, title, _series_link = parse_episode_page(
            """
            <h2 class="entry-title"> Demo Episode </h2>
            <video class="video-js" data-apireq="abc123"></video>
            """
        )

        self.assertEqual(data_apireq, "abc123")
        self.assertEqual(title, "Demo Episode")

    def test_parse_direct_episode_page_extracts_title_and_source(self):
        stream_url, title, _series_link = parse_direct_episode_page(
            """
            <h1 class="entry-title"> Direct Demo [06] </h1>
            <video class="video-js">
                <source src="//pwvideo.example/60/6.mp4?h=token&e=1" type="video/mp4">
            </video>
            """,
            "https://anime1.pw/349",
        )

        self.assertEqual(stream_url, "https://pwvideo.example/60/6.mp4?h=token&e=1")
        self.assertEqual(title, "Direct Demo [06]")

    def test_parse_direct_episode_page_prefers_mp4_source_and_warns(self):
        with self.assertLogs("anicat.extractor", level="WARNING") as logs:
            stream_url, title, _series_link = parse_direct_episode_page(
                """
                <h1 class="entry-title"> Direct Demo [06] </h1>
                <video class="video-js">
                    <source src="//pwvideo.example/60/6.m3u8" type="application/x-mpegURL">
                    <source src="//pwvideo.example/60/6.mp4?h=token&e=1" type="video/mp4">
                </video>
                """,
                "https://anime1.pw/349",
            )

        self.assertEqual(stream_url, "https://pwvideo.example/60/6.mp4?h=token&e=1")
        self.assertEqual(title, "Direct Demo [06]")
        self.assertIn("2 source candidates", logs.output[0])
        self.assertIn("1 MP4-compatible", logs.output[0])

    def test_parse_direct_episode_page_accepts_untyped_mp4_source(self):
        stream_url, title, _series_link = parse_direct_episode_page(
            """
            <h1 class="entry-title"> Direct Demo [06] </h1>
            <video class="video-js">
                <source src="//pwvideo.example/60/6.mp4?h=token&e=1">
            </video>
            """,
            "https://anime1.pw/349",
        )

        self.assertEqual(stream_url, "https://pwvideo.example/60/6.mp4?h=token&e=1")
        self.assertEqual(title, "Direct Demo [06]")

    def test_parse_direct_episode_page_rejects_missing_source(self):
        with self.assertRaisesRegex(ParseError, "video source"):
            parse_direct_episode_page('<h1 class="entry-title">Demo</h1>', "https://anime1.pw/1")

    def test_parse_direct_episode_page_rejects_non_mp4_source(self):
        with self.assertRaisesRegex(ParseError, "MP4 video source"):
            parse_direct_episode_page(
                """
                <h1 class="entry-title">Direct Demo</h1>
                <video class="video-js">
                    <source src="//pwvideo.example/playlist.m3u8" type="application/x-mpegURL">
                </video>
                """,
                "https://anime1.pw/1",
            )

    def test_parse_direct_episode_page_rejects_untyped_non_mp4_source(self):
        with self.assertRaisesRegex(ParseError, "MP4 video source"):
            parse_direct_episode_page(
                """
                <h1 class="entry-title">Direct Demo</h1>
                <video class="video-js">
                    <source src="//pwvideo.example/playlist.m3u8">
                </video>
                """,
                "https://anime1.pw/1",
            )

    def test_parse_direct_episode_page_warns_when_no_source_is_mp4(self):
        with self.assertLogs("anicat.extractor", level="WARNING") as logs:
            with self.assertRaisesRegex(ParseError, "MP4 video source"):
                parse_direct_episode_page(
                    """
                    <h1 class="entry-title">Direct Demo</h1>
                    <video class="video-js">
                        <source src="//pwvideo.example/playlist.m3u8">
                        <source src="//pwvideo.example/video.webm" type="video/webm">
                    </video>
                    """,
                    "https://anime1.pw/1",
                )

        self.assertIn("2 source candidates", logs.output[0])
        self.assertIn("0 MP4-compatible", logs.output[0])

    def test_parse_html_falls_back_when_lxml_is_unavailable(self):
        parsers: list[str] = []

        def fake_beautiful_soup(html: str, parser: str) -> BeautifulSoup:
            parsers.append(parser)
            if parser == "lxml":
                raise FeatureNotFound("lxml unavailable")
            return BeautifulSoup(html, parser)

        with patch("anicat.extractor.BeautifulSoup", side_effect=fake_beautiful_soup):
            soup = parse_html('<h2 class="entry-title">Demo</h2>')

        title = soup.select_one("h2.entry-title")
        assert title is not None
        self.assertEqual(parsers, ["lxml", "html.parser"])
        self.assertEqual(title.get_text(strip=True), "Demo")

    def test_parse_episode_page_rejects_missing_video_data(self):
        with self.assertRaises(ParseError):
            parse_episode_page('<h2 class="entry-title">Demo</h2>')

    def test_parse_episode_page_uses_first_video_with_api_request(self):
        data_apireq, title, _series_link = parse_episode_page(
            """
            <h2 class="entry-title">Demo</h2>
            <video class="video-js"></video>
            <video class="video-js" data-apireq="real-request"></video>
            """
        )

        self.assertEqual(data_apireq, "real-request")
        self.assertEqual(title, "Demo")

    def test_parse_episode_page_warns_when_multiple_video_candidates_exist(self):
        with self.assertLogs("anicat.extractor", level="WARNING") as logs:
            data_apireq, title, _series_link = parse_episode_page(
                """
                <h2 class="entry-title">Demo</h2>
                <video class="video-js" data-apireq="first"></video>
                <video class="video-js" data-apireq="second"></video>
                """
            )

        self.assertEqual(data_apireq, "first")
        self.assertEqual(title, "Demo")
        self.assertIn("2 video candidates", logs.output[0])

    def test_parse_stream_url_accepts_dict_or_list_shape(self):
        self.assertEqual(
            parse_stream_url({"s": {"src": "//cdn.example/video.mp4"}}), "//cdn.example/video.mp4"
        )
        self.assertEqual(parse_stream_url({"s": [{"src": "/video.mp4"}]}), "/video.mp4")

    def test_parse_stream_url_rejects_missing_src(self):
        with self.assertRaises(ParseError):
            parse_stream_url({"s": []})

    def test_extract_access_cookies_from_cookie_jar(self):
        response = requests.Response()
        response.cookies.set("e", "1")
        response.cookies.set("p", "2")
        response.cookies.set("h", "3")

        self.assertEqual(extract_access_cookies(response), {"e": "1", "p": "2", "h": "3"})

    def test_extract_access_cookies_from_header(self):
        response = requests.Response()
        response.headers["set-cookie"] = "e=1; Path=/; p=2; Path=/; h=3; Path=/"

        self.assertEqual(extract_access_cookies(response), {"e": "1", "p": "2", "h": "3"})

    def test_extract_access_cookies_from_comma_joined_set_cookie_header(self):
        response = requests.Response()
        response.headers["set-cookie"] = (
            "e=token-e; expires=Wed, 21 Oct 2026 07:28:00 GMT; Path=/; HttpOnly, "
            "p=token-p; expires=Wed, 21 Oct 2026 07:28:00 GMT; Path=/; HttpOnly, "
            "h=token-h; Path=/; Secure; SameSite=None"
        )

        self.assertEqual(
            extract_access_cookies(response),
            {"e": "token-e", "p": "token-p", "h": "token-h"},
        )

    def test_extract_access_cookies_merges_cookie_jar_and_header_fallback(self):
        response = requests.Response()
        response.cookies.set("e", "jar-e")
        response.headers["set-cookie"] = "p=header-p; Path=/; HttpOnly, h=header-h; Path=/"

        self.assertEqual(
            extract_access_cookies(response),
            {"e": "jar-e", "p": "header-p", "h": "header-h"},
        )

    def test_parse_set_cookie_header_preserves_expires_commas(self):
        parsed = parse_set_cookie_header(
            "e=1; expires=Wed, 21 Oct 2026 07:28:00 GMT; Path=/; HttpOnly, p=2; Path=/"
        )

        self.assertEqual(parsed["e"].value, "1")
        self.assertEqual(parsed["p"].value, "2")

    def test_extract_access_cookies_rejects_missing_values(self):
        response = requests.Response()
        response.cookies.set("e", "1")

        with self.assertRaises(ParseError):
            extract_access_cookies(response)

    def test_anime1_pw_episode_uses_direct_source_without_api(self):
        client = DirectPageClient(
            {
                "https://anime1.pw/349": """
                <h1 class="entry-title">Direct Demo [06]</h1>
                <video class="video-js">
                    <source src="//pwvideo.example/60/6.mp4?h=token&e=1" type="video/mp4">
                </video>
                """,
            }
        )

        episode = Anime1Extractor(client).episode("https://anime1.pw/349")

        self.assertEqual(episode.page_url, "https://anime1.pw/349")
        self.assertEqual(episode.title, "Direct Demo [06]")
        self.assertEqual(episode.stream_url, "https://pwvideo.example/60/6.mp4?h=token&e=1")
        self.assertEqual(episode.cookies, {})
        self.assertEqual(client.get_calls, ["https://anime1.pw/349"])
        self.assertEqual(client.post_calls, [])

    def test_anime1_pw_category_collects_episode_urls(self):
        client = DirectPageClient(
            {
                "https://anime1.pw/?cat=60": """
                <h1 class="page-title">Demo Anime</h1>
                <h2 class="entry-title">
                    <a href="https://anime1.pw/349" rel="bookmark">Demo Anime [06]</a>
                </h2>
                <h2 class="entry-title">
                    <a href="/348" rel="bookmark">Demo Anime [05]</a>
                </h2>
                """,
            }
        )

        season = Anime1Extractor(client).season_episode_urls("https://anime1.pw/?cat=60")

        self.assertEqual(season.episode_urls, ["https://anime1.pw/349", "https://anime1.pw/348"])
        self.assertEqual(season.anime_name, "Demo Anime")
        self.assertEqual(season.episode_numbers, [6, 5])
        self.assertEqual(client.get_calls, ["https://anime1.pw/?cat=60"])
        self.assertEqual(client.post_calls, [])

    def test_anime1_pw_category_rejects_empty_episode_list(self):
        client = DirectPageClient(
            {
                "https://anime1.pw/?cat=60": """
                <html><body><p>No matching selector anymore.</p></body></html>
                """,
            }
        )

        with self.assertRaisesRegex(ParseError, "no episode links"):
            Anime1Extractor(client).season_episode_urls("https://anime1.pw/?cat=60")

    def test_select_series_link_finds_full_series_link_in_entry_content(self):
        soup = parse_html('<div class="entry-content"><a href="?cat=1921">全集連結</a></div>')

        self.assertEqual(select_series_link(soup), "?cat=1921")

    def test_select_series_link_ignores_links_outside_entry_content(self):
        soup = parse_html('<a href="?cat=1921">全集連結</a>')

        self.assertIsNone(select_series_link(soup))

    def test_select_series_link_ignores_unrelated_links_in_entry_content(self):
        soup = parse_html('<div class="entry-content"><a href="/other">其他連結</a></div>')

        self.assertIsNone(select_series_link(soup))

    def test_strip_trailing_episode_number_removes_bracket_and_no_trailing_space(self):
        stripped = strip_trailing_episode_number("Demo Anime [12]")

        self.assertEqual(stripped, "Demo Anime")
        self.assertFalse(stripped.endswith(" "))
        self.assertEqual(
            strip_trailing_episode_number("約會大作戰 II (第二季) [01]"), "約會大作戰 II (第二季)"
        )

    def test_strip_trailing_episode_number_leaves_non_matching_titles_unchanged(self):
        self.assertEqual(strip_trailing_episode_number("Demo Anime"), "Demo Anime")
        self.assertEqual(strip_trailing_episode_number("Demo Anime [SP]"), "Demo Anime [SP]")

    def test_parse_episode_page_extracts_series_link(self):
        _, _, series_link = parse_episode_page(
            """
            <div class="entry-content"><a href="?cat=1921">全集連結</a></div>
            <h2 class="entry-title">Demo Episode [12]</h2>
            <video class="video-js" data-apireq="abc123"></video>
            """
        )

        self.assertEqual(series_link, "?cat=1921")

    def test_parse_episode_page_series_link_is_none_when_absent(self):
        _, _, series_link = parse_episode_page(
            """
            <h2 class="entry-title">Demo Episode</h2>
            <video class="video-js" data-apireq="abc123"></video>
            """
        )

        self.assertIsNone(series_link)

    def test_parse_direct_episode_page_extracts_series_link(self):
        _, _, series_link = parse_direct_episode_page(
            """
            <div class="entry-content"><a href="?cat=1921">全集連結</a></div>
            <h1 class="entry-title">Direct Demo [06]</h1>
            <video class="video-js">
                <source src="//pwvideo.example/60/6.mp4" type="video/mp4">
            </video>
            """,
            "https://anime1.pw/349",
        )

        self.assertEqual(series_link, "?cat=1921")

    def test_resolve_standalone_anime_name_prefers_series_link_category_title(self):
        def fetch_page(url: str) -> str:
            self.assertEqual(url, "https://anime1.me/29592?cat=1921")
            return '<h1 class="page-title">Demo Anime Full Title</h1>'

        anime_name = resolve_standalone_anime_name(
            fetch_page, "https://anime1.me/29592", "?cat=1921", "Demo Anime [12]"
        )

        self.assertEqual(anime_name, "Demo Anime Full Title")

    def test_resolve_standalone_anime_name_falls_back_without_series_link(self):
        def fetch_page(url: str) -> NoReturn:
            raise AssertionError("should not fetch a category page without a series link")

        anime_name = resolve_standalone_anime_name(
            fetch_page, "https://anime1.me/29592", None, "Demo Anime [12]"
        )

        self.assertEqual(anime_name, "Demo Anime")

    def test_resolve_standalone_anime_name_falls_back_when_category_fetch_fails(self):
        def fetch_page(url: str) -> NoReturn:
            raise FetchError("boom")

        anime_name = resolve_standalone_anime_name(
            fetch_page, "https://anime1.me/29592", "?cat=1921", "Demo Anime [12]"
        )

        self.assertEqual(anime_name, "Demo Anime")

    def test_resolve_standalone_anime_name_falls_back_when_category_page_has_no_title(self):
        anime_name = resolve_standalone_anime_name(
            lambda url: "<html><body>no title here</body></html>",
            "https://anime1.me/29592",
            "?cat=1921",
            "Demo Anime [12]",
        )

        self.assertEqual(anime_name, "Demo Anime")

    def test_resolve_standalone_anime_name_returns_none_for_empty_fallback_title(self):
        anime_name = resolve_standalone_anime_name(
            lambda url: "", "https://anime1.me/1", None, "[12]"
        )

        self.assertIsNone(anime_name)

    def test_anime1_me_episode_resolves_anime_name_via_series_link(self):
        client = Anime1MeClient(
            {
                "https://anime1.me/29592": """
                <div class="entry-content"><a href="?cat=1921">全集連結</a></div>
                <h2 class="entry-title">Demo Anime [12]</h2>
                <video class="video-js" data-apireq="abc123"></video>
                """,
                "https://anime1.me/29592?cat=1921": """
                <h1 class="page-title">Demo Anime Full Title</h1>
                <h2 class="entry-title">
                    <a rel="bookmark" href="/1">Demo Anime Full Title [01]</a>
                </h2>
                """,
            }
        )

        episode = Anime1Extractor(client).episode(
            "https://anime1.me/29592", resolve_anime_name=True
        )

        self.assertEqual(episode.anime_name, "Demo Anime Full Title")
        self.assertEqual(
            client.post_calls,
            ["https://anime1.me/29592", "https://anime1.me/29592?cat=1921"],
        )
        self.assertEqual(client.api_page_urls, ["https://anime1.me/29592"])

    def test_anime1_me_episode_skips_anime_name_resolution_by_default(self):
        client = Anime1MeClient(
            {
                "https://anime1.me/29592": """
                <div class="entry-content"><a href="?cat=1921">全集連結</a></div>
                <h2 class="entry-title">Demo Anime [12]</h2>
                <video class="video-js" data-apireq="abc123"></video>
                """,
            }
        )

        episode = Anime1Extractor(client).episode("https://anime1.me/29592")

        self.assertIsNone(episode.anime_name)
        self.assertEqual(client.post_calls, ["https://anime1.me/29592"])

    def test_anime1_me_episode_falls_back_to_title_without_series_link(self):
        client = Anime1MeClient(
            {
                "https://anime1.me/29592": """
                <h2 class="entry-title">Demo Anime [12]</h2>
                <video class="video-js" data-apireq="abc123"></video>
                """,
            }
        )

        episode = Anime1Extractor(client).episode(
            "https://anime1.me/29592", resolve_anime_name=True
        )

        self.assertEqual(episode.anime_name, "Demo Anime")
        self.assertEqual(client.post_calls, ["https://anime1.me/29592"])

    def test_anime1_pw_episode_resolves_anime_name_via_series_link(self):
        client = DirectPageClient(
            {
                "https://anime1.pw/349": """
                <div class="entry-content"><a href="?cat=60">全集連結</a></div>
                <h1 class="entry-title">Direct Demo [06]</h1>
                <video class="video-js">
                    <source src="//pwvideo.example/60/6.mp4?h=token&e=1" type="video/mp4">
                </video>
                """,
                "https://anime1.pw/349?cat=60": """
                <h1 class="page-title">Direct Demo Full Title</h1>
                <h2 class="entry-title"><a rel="bookmark" href="/349">Direct Demo [06]</a></h2>
                """,
            }
        )

        episode = Anime1Extractor(client).episode("https://anime1.pw/349", resolve_anime_name=True)

        self.assertEqual(episode.anime_name, "Direct Demo Full Title")
        self.assertEqual(
            client.get_calls, ["https://anime1.pw/349", "https://anime1.pw/349?cat=60"]
        )
        self.assertEqual(client.post_calls, [])


if __name__ == "__main__":
    unittest.main()
