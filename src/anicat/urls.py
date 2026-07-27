from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Final, Literal
from urllib.parse import parse_qs, unquote, urlparse

from .errors import AniCatError

SourceKind = Literal["anime1_me", "anime1_pw"]
ANIME1_ME_SOURCE: Final[SourceKind] = "anime1_me"
ANIME1_PW_SOURCE: Final[SourceKind] = "anime1_pw"
ANIME1_ME_HOST = "anime1.me"
ANIME1_PW_HOST = "anime1.pw"
EPISODE_PATH_PATTERN = re.compile(r"^/\d+/?$")
URL_SEPARATOR_PATTERN = re.compile(r"[,\s]+")
SUPPORTED_SCHEMES = frozenset({"http", "https"})
WORDPRESS_RESERVED_SLUGS = frozenset(
    {
        "about",
        "contact",
        "feed",
        "page",
        "privacy-policy",
        "wp-admin",
        "wp-content",
        "wp-includes",
        "wp-json",
        "wp-login",
    }
)


def split_urls(values: Sequence[str]) -> list[str]:
    """Split CLI URL arguments that may contain comma or whitespace separators."""

    return [item for value in values for item in URL_SEPARATOR_PATTERN.split(value.strip()) if item]


def is_season_url(url: str) -> bool:
    """Return whether a URL points to an Anime1 category/season page."""

    parsed = urlparse(url)
    kind = source_kind(url)
    if kind == ANIME1_ME_SOURCE:
        return parsed.path.startswith("/category/") and len(parsed.path) > len("/category/")
    if kind == ANIME1_PW_SOURCE:
        if is_numeric_episode_path(parsed.path):
            return False
        return has_numeric_category_query(parsed.query) or is_category_slug_path(parsed.path)
    return False


def is_episode_url(url: str) -> bool:
    """Return whether a URL points to an Anime1 episode page."""

    return source_kind(url) is not None and is_numeric_episode_path(urlparse(url).path)


def has_numeric_category_query(query: str) -> bool:
    """Return whether a query string contains a numeric WordPress category ID."""

    return any(value.isdigit() for value in parse_qs(query).get("cat", []))


def is_numeric_episode_path(path: str) -> bool:
    """Return whether a URL path matches Anime1's numeric episode permalink shape."""

    return bool(EPISODE_PATH_PATTERN.fullmatch(path))


def is_category_slug_path(path: str) -> bool:
    """Return whether a path can be an anime1.pw category slug."""

    slug = path.strip("/")
    if not slug or "/" in slug or "." in slug:
        return False

    decoded_slug = unquote(slug)
    normalized_slug = decoded_slug.lower()
    if "/" in decoded_slug or normalized_slug.startswith("wp-"):
        return False
    if normalized_slug in WORDPRESS_RESERVED_SLUGS:
        return False
    return True


def source_kind(url: str) -> SourceKind | None:
    """Return the supported Anime1 source kind for a URL."""

    if any(character.isspace() for character in url):
        return None

    parsed = urlparse(url)
    if parsed.scheme.lower() not in SUPPORTED_SCHEMES:
        return None

    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    if host == ANIME1_ME_HOST:
        return ANIME1_ME_SOURCE
    if host == ANIME1_PW_HOST:
        return ANIME1_PW_SOURCE
    return None


def ensure_supported_url(url: str) -> None:
    """Raise when a URL is outside the supported Anime1 URL shapes."""

    if not is_season_url(url) and not is_episode_url(url):
        raise AniCatError(f"unsupported Anime1 URL: {url}")


def parse_episode_selector(spec: str) -> frozenset[int]:
    """Parse a comma-separated episode number/range selector like '15-17,20'."""

    numbers: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            raise AniCatError(f"invalid episode selector: {spec!r}")

        if "-" in part:
            start_text, _, end_text = part.partition("-")
            start = _parse_episode_bound(start_text, spec)
            end = _parse_episode_bound(end_text, spec)
            if end < start:
                raise AniCatError(f"invalid episode range {part!r} in selector: {spec!r}")
            numbers.update(range(start, end + 1))
        else:
            numbers.add(_parse_episode_bound(part, spec))

    return frozenset(numbers)


def _parse_episode_bound(value: str, spec: str) -> int:
    """Parse one episode selector bound, rejecting non-positive or non-numeric values."""

    value = value.strip()
    if not value.isdigit() or int(value) < 1:
        raise AniCatError(f"invalid episode selector: {spec!r}")
    return int(value)


def dedupe(values: Iterable[str]) -> list[str]:
    """Remove duplicates while preserving the original order."""

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
