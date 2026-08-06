from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from http.cookies import CookieError, SimpleCookie
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, FeatureNotFound

from .errors import AniCatError, ParseError
from .models import Episode
from .urls import ANIME1_ME_SOURCE, ANIME1_PW_SOURCE, SourceKind, source_kind

ACCESS_COOKIE_NAMES = ("e", "p", "h")
SET_COOKIE_SEPARATOR_PATTERN = re.compile(r",\s*(?=[^=;,\s]+=)")
EPISODE_NUMBER_PATTERN = re.compile(r"\[(\d+)\]\s*$")
TRAILING_EPISODE_NUMBER_PATTERN = re.compile(r"\s*\[\d+\]\s*$")
SERIES_LINK_TEXT = "全集連結"
LOGGER = logging.getLogger(__name__)
PageFetcher = Callable[[str], str]


@dataclass(frozen=True)
class SeasonPage:
    """Parsed season/category page with episode links and pagination."""

    episode_urls: list[str]
    next_url: str | None
    anime_name: str | None = None
    episode_numbers: list[int | None] = field(default_factory=list)


@dataclass(frozen=True)
class SeasonEpisodes:
    """Episode URLs collected from a season/category URL with its anime name."""

    episode_urls: list[str]
    anime_name: str | None = None
    episode_numbers: list[int | None] = field(default_factory=list)


@dataclass(frozen=True)
class EpisodePage:
    """Episode identity parsed from its page, before the stream is resolved.

    Resolving in two phases lets a caller decide the output filename, and so
    skip an episode it already has, without minting stream credentials it
    would immediately throw away. ``data_apireq`` and ``stream_url`` carry
    whatever the owning extractor needs to finish the job.
    """

    page_url: str
    title: str
    anime_name: str | None = None
    data_apireq: str | None = None
    stream_url: str | None = None

    def unresolved_episode(self) -> Episode:
        """Return episode metadata with no stream, for reporting a skipped download."""

        return Episode(
            page_url=self.page_url,
            title=self.title,
            stream_url="",
            anime_name=self.anime_name,
        )


class EpisodeSource(Protocol):
    """Minimal HTTP dependency required by Anime1Extractor."""

    def get_page(self, url: str) -> str:
        """Return raw HTML for an Anime1 page fetched with GET."""

        ...

    def post_page(self, url: str) -> str:
        """Return raw HTML for an Anime1 page fetched with POST."""

        ...

    def post_api(self, data_apireq: str, *, page_url: str | None = None) -> requests.Response:
        """Return raw response for an Anime1 episode API payload."""

        ...


class EpisodeExtractor(Protocol):
    """Provider-specific extraction behavior selected by Anime1Extractor."""

    def season_episode_urls(self, url: str) -> SeasonEpisodes:
        """Collect all episode URLs and the anime name from a season/category URL."""

        ...

    def episode_page(self, url: str, *, resolve_anime_name: bool = False) -> EpisodePage:
        """Parse an episode page into its identity, without resolving the stream."""

        ...

    def resolve_stream(self, page: EpisodePage) -> Episode:
        """Complete a parsed episode page into download-ready metadata."""

        ...


def parse_season_page(html: str) -> SeasonPage:
    """Parse episode URLs and next-page URL from a season/category page."""

    soup = parse_html(html)
    episode_urls: list[str] = []
    episode_numbers: list[int | None] = []
    for anchor in soup.select("h2.entry-title a[rel='bookmark']"):
        href = anchor.get("href")
        if isinstance(href, str):
            episode_urls.append(href)
            episode_numbers.append(parse_episode_number(anchor.get_text(" ", strip=True)))

    next_anchor = soup.select_one("div.nav-previous a[href]")
    next_href = next_anchor.get("href") if next_anchor else None

    title = soup.select_one("h1.page-title")
    anime_name = title.get_text(" ", strip=True) if title else None

    return SeasonPage(
        episode_urls=episode_urls,
        next_url=next_href if isinstance(next_href, str) else None,
        anime_name=anime_name or None,
        episode_numbers=episode_numbers,
    )


def parse_episode_number(title: str) -> int | None:
    """Extract the trailing bracketed episode number from a listing title."""

    match = EPISODE_NUMBER_PATTERN.search(title)
    return int(match.group(1)) if match else None


def parse_episode_page(html: str) -> tuple[str, str, str | None]:
    """Parse data-apireq, display title, and series-link href from an episode page."""

    soup = parse_html(html)
    title = soup.select_one("h2.entry-title")

    data_apireq = select_episode_api_request(soup)
    if data_apireq is None:
        raise ParseError("episode page is missing video data-apireq")
    if not title:
        raise ParseError("episode page is missing title")

    return data_apireq, title.get_text(" ", strip=True), select_series_link(soup)


def parse_direct_episode_page(html: str, base_url: str) -> tuple[str, str, str | None]:
    """Parse direct-video episode pages that expose a source URL in HTML."""

    soup = parse_html(html)
    title = soup.select_one("h1.entry-title") or soup.select_one("h2.entry-title")
    source_url = select_direct_video_source(soup)

    if not title:
        raise ParseError("episode page is missing title")
    if source_url is None:
        raise ParseError("episode page is missing MP4 video source")

    return (
        urljoin(base_url, source_url),
        title.get_text(" ", strip=True),
        select_series_link(soup),
    )


def select_series_link(soup: BeautifulSoup) -> str | None:
    """Return the href of an episode page's "全集連結" (full series) link, if present."""

    for anchor in soup.select("div.entry-content a[href]"):
        if anchor.get_text(strip=True) == SERIES_LINK_TEXT:
            href = anchor.get("href")
            return href if isinstance(href, str) and href else None
    return None


def strip_trailing_episode_number(title: str) -> str:
    """Remove a trailing bracketed episode number (and surrounding whitespace) from a title."""

    return TRAILING_EPISODE_NUMBER_PATTERN.sub("", title).strip()


def resolve_standalone_anime_name(
    fetch_page: PageFetcher,
    episode_url: str,
    series_link: str | None,
    title: str,
) -> str | None:
    """Resolve the anime name for a standalone episode URL.

    Prefers the season/category title reached via the episode page's
    "全集連結" link; falls back to the episode's own title (with its
    trailing episode-number bracket stripped) when there's no such link,
    or the category page can't be fetched or has no title of its own.
    """

    if series_link:
        category_url = urljoin(episode_url, series_link)
        try:
            anime_name = parse_season_page(fetch_page(category_url)).anime_name
        except AniCatError:
            anime_name = None
        if anime_name:
            return anime_name

    return strip_trailing_episode_number(title) or None


def select_direct_video_source(soup: BeautifulSoup) -> str | None:
    """Return the first MP4-compatible direct video source URL."""

    candidates: list[tuple[str, str | None]] = []
    for source in soup.select("video.video-js source[src]"):
        source_url = source.get("src")
        if not isinstance(source_url, str) or not source_url:
            continue
        candidates.append((source_url, source_media_type(source_url, source.get("type"))))

    mp4_candidates = [
        source_url for source_url, source_type in candidates if source_type == "video/mp4"
    ]

    if len(candidates) > 1:
        LOGGER.warning(
            "episode page contains %d source candidates; %d MP4-compatible",
            len(candidates),
            len(mp4_candidates),
        )

    return mp4_candidates[0] if mp4_candidates else None


def source_media_type(source_url: str, value: object) -> str | None:
    """Return the declared media type or infer MP4 from the source URL path."""

    source_type = media_type(value)
    if source_type is not None:
        return source_type
    if urlparse(source_url).path.lower().endswith(".mp4"):
        return "video/mp4"
    return None


def media_type(value: object) -> str | None:
    """Normalize a source type attribute into a comparable media type."""

    if not isinstance(value, str) or not value.strip():
        return None
    return value.split(";", 1)[0].strip().lower()


def select_episode_api_request(soup: BeautifulSoup) -> str | None:
    """Return the first valid video data-apireq from an episode page."""

    candidates = [
        data_apireq
        for video in soup.select("video.video-js")
        if isinstance(data_apireq := video.get("data-apireq"), str) and data_apireq
    ]
    if len(candidates) > 1:
        LOGGER.warning(
            "episode page contains %d video candidates; using the first", len(candidates)
        )
    return candidates[0] if candidates else None


def parse_html(html: str) -> BeautifulSoup:
    """Create a BeautifulSoup document with lxml fallback handling."""

    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        # Keep the CLI usable even when the optional native lxml parser is missing.
        return BeautifulSoup(html, "html.parser")


def parse_stream_url(payload: Any) -> str:
    """Extract the video stream URL from Anime1 API response JSON."""

    stream = payload.get("s") if isinstance(payload, dict) else None
    if isinstance(stream, list):
        stream = stream[0] if stream else None
    if not isinstance(stream, dict) or not stream.get("src"):
        raise ParseError(f"API response is missing stream src: {payload}")
    return stream["src"]


def extract_access_cookies(response: requests.Response) -> dict[str, str]:
    """Extract video access cookies required by the CDN request."""

    # requests can parse some Set-Cookie layouts directly; Anime1 also returns
    # multiple comma-separated HttpOnly cookies that need a header fallback.
    cookies = {name: value for name in ACCESS_COOKIE_NAMES if (value := response.cookies.get(name))}

    if len(cookies) == len(ACCESS_COOKIE_NAMES):
        return cookies

    parsed = parse_set_cookie_header(response.headers.get("set-cookie", ""))

    for name in ACCESS_COOKIE_NAMES:
        if name not in cookies and name in parsed:
            cookies[name] = parsed[name].value

    missing = [name for name in ACCESS_COOKIE_NAMES if name not in cookies]
    if missing:
        raise ParseError(f"API response is missing access cookies: {', '.join(missing)}")

    log_access_cookie_lifetimes(response)
    return cookies


def log_access_cookie_lifetimes(response: requests.Response) -> None:
    """Log signed-cookie names and expiry attributes, never their values."""

    if not LOGGER.isEnabledFor(logging.DEBUG):
        return

    parsed = parse_set_cookie_header(response.headers.get("set-cookie", ""))
    lifetimes = {
        name: morsel["max-age"] or morsel["expires"] or "session"
        for name in ACCESS_COOKIE_NAMES
        if (morsel := parsed.get(name)) is not None
    }
    LOGGER.debug("Access cookie lifetimes: %s", lifetimes or "<not advertised>")


def parse_set_cookie_header(header: str) -> SimpleCookie:
    """Parse a possibly comma-joined Set-Cookie header into a SimpleCookie."""

    parsed = SimpleCookie()
    if not header:
        return parsed

    try:
        parsed.load(header)
    except CookieError:
        parsed = SimpleCookie()

    if parsed:
        return parsed

    for item in split_combined_set_cookie_header(header):
        try:
            parsed.load(item)
        except CookieError:
            continue
    return parsed


def split_combined_set_cookie_header(header: str) -> list[str]:
    """Split requests-style comma-joined Set-Cookie headers into cookie fields."""

    return [item.strip() for item in SET_COOKIE_SEPARATOR_PATTERN.split(header) if item.strip()]


def collect_paginated_episode_urls(fetch_page: PageFetcher, url: str) -> SeasonEpisodes:
    """Collect episode links and the anime name from a paginated WordPress-style listing."""

    collected: list[str] = []
    collected_numbers: list[int | None] = []
    anime_name: str | None = None
    current_url: str | None = url
    visited: set[str] = set()

    while current_url:
        if current_url in visited:
            raise ParseError(f"season pagination loop detected: {current_url}")
        visited.add(current_url)

        html = fetch_page(current_url)
        page = parse_season_page(html)
        if html.strip() and not page.episode_urls:
            raise ParseError(f"season page returned no episode links: {current_url}")
        collected.extend(urljoin(current_url, item) for item in page.episode_urls)
        collected_numbers.extend(page.episode_numbers)
        if anime_name is None:
            anime_name = page.anime_name
        # Resolve relative pagination URLs against the page that produced them.
        current_url = urljoin(current_url, page.next_url) if page.next_url else None

    return SeasonEpisodes(
        episode_urls=collected,
        anime_name=anime_name,
        episode_numbers=collected_numbers,
    )


class Anime1MeExtractor:
    """Extractor for anime1.me pages that require the Anime1 API."""

    def __init__(self, client: EpisodeSource) -> None:
        self.client = client

    def season_episode_urls(self, url: str) -> SeasonEpisodes:
        """Collect all anime1.me episode URLs and anime name from a category URL."""

        return collect_paginated_episode_urls(self.client.post_page, url)

    def episode_page(self, url: str, *, resolve_anime_name: bool = False) -> EpisodePage:
        """Parse one anime1.me episode page into its identity and API payload."""

        data_apireq, title, series_link = parse_episode_page(self.client.post_page(url))
        anime_name = (
            resolve_standalone_anime_name(self.client.post_page, url, series_link, title)
            if resolve_anime_name
            else None
        )
        return EpisodePage(
            page_url=url,
            title=title,
            anime_name=anime_name,
            data_apireq=data_apireq,
        )

    def resolve_stream(self, page: EpisodePage) -> Episode:
        """Resolve anime1.me stream URL and access cookies from the API."""

        if page.data_apireq is None:
            raise ParseError(f"episode page is missing video data-apireq: {page.page_url}")

        # The API expects the Referer/Origin the embedded player would send.
        response = self.client.post_api(page.data_apireq, page_url=page.page_url)

        try:
            payload = response.json()
        except ValueError as error:
            raise ParseError(f"API response is not JSON: {response.text}") from error

        return Episode(
            page_url=page.page_url,
            title=page.title,
            stream_url=urljoin("https://v.anime1.me", parse_stream_url(payload)),
            cookies=extract_access_cookies(response),
            anime_name=page.anime_name,
        )


class Anime1PwExtractor:
    """Extractor for anime1.pw pages that expose direct MP4 sources."""

    def __init__(self, client: EpisodeSource) -> None:
        self.client = client

    def season_episode_urls(self, url: str) -> SeasonEpisodes:
        """Collect all anime1.pw episode URLs and anime name from a category URL."""

        return collect_paginated_episode_urls(self.client.get_page, url)

    def episode_page(self, url: str, *, resolve_anime_name: bool = False) -> EpisodePage:
        """Parse one anime1.pw episode page, which already exposes its source URL."""

        stream_url, title, series_link = parse_direct_episode_page(self.client.get_page(url), url)
        anime_name = (
            resolve_standalone_anime_name(self.client.get_page, url, series_link, title)
            if resolve_anime_name
            else None
        )
        return EpisodePage(
            page_url=url,
            title=title,
            anime_name=anime_name,
            stream_url=stream_url,
        )

    def resolve_stream(self, page: EpisodePage) -> Episode:
        """Return anime1.pw episode metadata; the page fetch already resolved it."""

        if page.stream_url is None:
            raise ParseError(f"episode page is missing MP4 video source: {page.page_url}")

        return Episode(
            page_url=page.page_url,
            title=page.title,
            stream_url=page.stream_url,
            cookies={},
            anime_name=page.anime_name,
        )


class Anime1Extractor:
    """Route supported Anime1 URLs to provider-specific extractors."""

    def __init__(self, client: EpisodeSource) -> None:
        self.extractors: dict[SourceKind, EpisodeExtractor] = {
            ANIME1_ME_SOURCE: Anime1MeExtractor(client),
            ANIME1_PW_SOURCE: Anime1PwExtractor(client),
        }

    def season_episode_urls(self, url: str) -> SeasonEpisodes:
        """Collect all episode URLs and the anime name from a supported category URL."""

        return self._extractor_for_url(url).season_episode_urls(url)

    def episode_page(self, url: str, *, resolve_anime_name: bool = False) -> EpisodePage:
        """Parse one supported episode URL into its identity, without resolving the stream."""

        return self._extractor_for_url(url).episode_page(url, resolve_anime_name=resolve_anime_name)

    def resolve_stream(self, page: EpisodePage) -> Episode:
        """Complete a parsed episode page into stream URL, title, and cookies."""

        return self._extractor_for_url(page.page_url).resolve_stream(page)

    def episode(self, url: str, *, resolve_anime_name: bool = False) -> Episode:
        """Resolve one supported episode URL into stream URL, title, and cookies."""

        extractor = self._extractor_for_url(url)
        page = extractor.episode_page(url, resolve_anime_name=resolve_anime_name)
        return extractor.resolve_stream(page)

    def _extractor_for_url(self, url: str) -> EpisodeExtractor:
        """Return the extractor that owns the URL's supported source kind."""

        kind = source_kind(url)
        if kind is None:
            raise ParseError(f"unsupported Anime1 URL: {url}")
        return self.extractors[kind]
