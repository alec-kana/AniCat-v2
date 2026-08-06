import unittest
from collections.abc import Iterator, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, ClassVar, NoReturn, cast

import requests

from anicat.errors import AccessDeniedError
from anicat.models import EpisodeJob, VideoStreamResponse
from anicat.options import DownloadOptions
from anicat.service import AniCatService


class BadClient:
    def get_page(self, url: str) -> str:
        return "<html></html>"

    def post_page(self, url: str) -> str:
        return "<html></html>"

    def post_api(self, data_apireq: str, *, page_url: str | None = None) -> NoReturn:
        raise AssertionError("post_api should not be called")

    def stream_video(
        self,
        url: str,
        *,
        cookies: Mapping[str, str],
        headers: Mapping[str, str] | None = None,
        page_url: str | None = None,
    ) -> NoReturn:
        raise AssertionError("stream_video should not be called")


class ApiResponse:
    text = "{}"
    headers: ClassVar[dict[str, str]] = {}

    def __init__(self) -> None:
        self.cookies = {
            "e": "1",
            "p": "2",
            "h": "3",
        }

    def json(self) -> dict[str, dict[str, str]]:
        return {"s": {"src": "//cdn.example/demo.mp4"}}


class VideoResponse:
    status_code = 200
    content = b"a" * 2500

    def __init__(self) -> None:
        self.headers = {"content-length": str(len(self.content))}
        self.closed = False

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        for index in range(0, len(self.content), chunk_size):
            yield self.content[index : index + chunk_size]

    def close(self) -> None:
        self.closed = True


class GoodClient:
    instances: ClassVar[list["GoodClient"]] = []

    def __init__(self) -> None:
        self.closed = False
        self.instances.append(self)

    def post_page(self, url: str) -> str:
        return """
        <h2 class="entry-title">Demo</h2>
        <video class="video-js" data-apireq="%7B%7D"></video>
        """

    def get_page(self, url: str) -> str:
        return self.post_page(url)

    def post_api(self, data_apireq: str, *, page_url: str | None = None) -> requests.Response:
        return cast(requests.Response, ApiResponse())

    def stream_video(
        self,
        url: str,
        *,
        cookies: Mapping[str, str],
        headers: Mapping[str, str] | None = None,
        page_url: str | None = None,
    ) -> VideoStreamResponse:
        return VideoResponse()

    def close(self) -> None:
        self.closed = True


class DirectClient:
    instances: ClassVar[list["DirectClient"]] = []

    def __init__(self) -> None:
        self.closed = False
        self.stream_calls: list[tuple[str, dict[str, str]]] = []
        self.instances.append(self)

    def get_page(self, url: str) -> str:
        return """
        <h1 class="entry-title">Direct Demo</h1>
        <video class="video-js">
            <source src="//pwvideo.example/60/6.mp4?h=token&e=1" type="video/mp4">
        </video>
        """

    def post_page(self, url: str) -> NoReturn:
        raise AssertionError("anime1.pw extraction should use get_page")

    def post_api(self, data_apireq: str, *, page_url: str | None = None) -> NoReturn:
        raise AssertionError("direct source extraction should not call post_api")

    def stream_video(
        self,
        url: str,
        *,
        cookies: Mapping[str, str],
        headers: Mapping[str, str] | None = None,
        page_url: str | None = None,
    ) -> VideoStreamResponse:
        self.stream_calls.append((url, dict(cookies)))
        return VideoResponse()

    def close(self) -> None:
        self.closed = True


class SeasonClient:
    def get_page(self, url: str) -> str:
        return self.post_page(url)

    def post_page(self, url: str) -> str:
        if url == "https://anime1.me/category/demo":
            return """
            <h1 class="page-title">Demo Anime</h1>
            <h2 class="entry-title"><a rel="bookmark" href="https://anime1.me/1">Demo [01]</a></h2>
            <h2 class="entry-title"><a rel="bookmark" href="https://anime1.me/2">Demo [02]</a></h2>
            """
        number = "02" if url.endswith("/2") else "01"
        return f"""
        <h2 class="entry-title">Demo [{number}]</h2>
        <video class="video-js" data-apireq="%7B%7D"></video>
        """

    def post_api(self, data_apireq: str, *, page_url: str | None = None) -> requests.Response:
        return cast(requests.Response, ApiResponse())

    def stream_video(
        self,
        url: str,
        *,
        cookies: Mapping[str, str],
        headers: Mapping[str, str] | None = None,
        page_url: str | None = None,
    ) -> VideoStreamResponse:
        return VideoResponse()

    def close(self) -> None:
        pass


class StandaloneEpisodeClient:
    """anime1.me client whose episode page links to its category via 全集連結."""

    def get_page(self, url: str) -> NoReturn:
        raise AssertionError("anime1.me extraction should use post_page")

    def post_page(self, url: str) -> str:
        if url == "https://anime1.me/29592":
            return """
            <div class="entry-content"><a href="?cat=1921">全集連結</a></div>
            <h2 class="entry-title">Demo Anime [12]</h2>
            <video class="video-js" data-apireq="%7B%7D"></video>
            """
        if url == "https://anime1.me/29592?cat=1921":
            return """
            <h1 class="page-title">Demo Anime Full Title</h1>
            <h2 class="entry-title"><a rel="bookmark" href="/29592">Demo Anime [12]</a></h2>
            """
        raise AssertionError(f"unexpected page request: {url}")

    def post_api(self, data_apireq: str, *, page_url: str | None = None) -> requests.Response:
        return cast(requests.Response, ApiResponse())

    def stream_video(
        self,
        url: str,
        *,
        cookies: Mapping[str, str],
        headers: Mapping[str, str] | None = None,
        page_url: str | None = None,
    ) -> VideoStreamResponse:
        return VideoResponse()

    def close(self) -> None:
        pass


class StandaloneEpisodeNoSeriesLinkClient:
    """anime1.me client whose episode page has no 全集連結 link."""

    def get_page(self, url: str) -> NoReturn:
        raise AssertionError("anime1.me extraction should use post_page")

    def post_page(self, url: str) -> str:
        return """
        <h2 class="entry-title">Demo Anime [12]</h2>
        <video class="video-js" data-apireq="%7B%7D"></video>
        """

    def post_api(self, data_apireq: str, *, page_url: str | None = None) -> requests.Response:
        return cast(requests.Response, ApiResponse())

    def stream_video(
        self,
        url: str,
        *,
        cookies: Mapping[str, str],
        headers: Mapping[str, str] | None = None,
        page_url: str | None = None,
    ) -> VideoStreamResponse:
        return VideoResponse()

    def close(self) -> None:
        pass


class DenyingClient:
    """anime1.me client whose signed CDN credentials expire mid-download."""

    def __init__(self, *, denials: int = 1, denial_headers: dict[str, str] | None = None) -> None:
        self.remaining_denials = denials
        self.denial_headers = denial_headers or {"Server": "nginx"}
        self.api_calls = 0
        self.stream_calls: list[tuple[str, dict[str, str], dict[str, str]]] = []
        self.closed = False

    def post_page(self, url: str) -> str:
        return """
        <h2 class="entry-title">Demo Anime [12]</h2>
        <video class="video-js" data-apireq="%7B%7D"></video>
        """

    def get_page(self, url: str) -> str:
        return self.post_page(url)

    def post_api(self, data_apireq: str, *, page_url: str | None = None) -> requests.Response:
        self.api_calls += 1
        return cast(requests.Response, SignedApiResponse(self.api_calls))

    def stream_video(
        self,
        url: str,
        *,
        cookies: Mapping[str, str],
        headers: Mapping[str, str] | None = None,
        page_url: str | None = None,
    ) -> VideoStreamResponse:
        self.stream_calls.append((url, dict(cookies), dict(headers or {})))
        if self.remaining_denials > 0:
            self.remaining_denials -= 1
            return DeniedMidStreamResponse(self.denial_headers)
        return ResumedResponse()

    def close(self) -> None:
        self.closed = True


class SignedApiResponse:
    text = "{}"
    headers: ClassVar[dict[str, str]] = {}

    def __init__(self, generation: int) -> None:
        self.generation = generation
        self.cookies = {"e": f"e{generation}", "p": f"p{generation}", "h": f"h{generation}"}

    def json(self) -> dict[str, dict[str, str]]:
        return {"s": {"src": f"//v.anime1.me/demo.mp4?sig={self.generation}"}}


class DeniedMidStreamResponse:
    """Response revoked after the first chunk lands on disk."""

    status_code = 200

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = {"content-length": "6", **headers}
        self.closed = False

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        yield b"abc"
        raise AccessDeniedError("stream denied", status_code=403, headers=self.headers)

    def close(self) -> None:
        self.closed = True


class ResumedResponse:
    status_code = 206

    def __init__(self) -> None:
        self.headers = {"content-range": "bytes 3-5/6"}
        self.closed = False

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        yield b"def"

    def close(self) -> None:
        self.closed = True


def download_options(**overrides: object) -> DownloadOptions:
    """Build options with pacing disabled so tests never sleep."""

    defaults: dict[str, object] = {
        "min_delay": 0.0,
        "max_delay": 0.0,
        "stagger": 0.0,
        "host_interval": 0.0,
    }
    return DownloadOptions(**cast(Any, {**defaults, **overrides}))


class ServiceTests(unittest.TestCase):
    def test_download_one_reports_recoverable_extractor_error(self):
        service = AniCatService(
            download_options(output_dir=Path("unused")),
            client_factory=BadClient,
        )

        report = service.download_one("https://anime1.me/1")

        self.assertEqual(report.url, "https://anime1.me/1")
        self.assertIsNone(report.result)
        error = report.error
        assert error is not None
        self.assertIn("data-apireq", error)

    def test_download_many_reports_chunk_progress(self):
        progress: list[tuple[str, int, int, int | None]] = []
        GoodClient.instances.clear()

        with TemporaryDirectory() as directory:
            service = AniCatService(
                download_options(
                    output_dir=Path(directory),
                    concurrency=1,
                    chunk_size=1024,
                ),
                client_factory=GoodClient,
            )

            reports = service.download_many(
                [EpisodeJob(url="https://anime1.me/1")],
                on_progress=lambda event: progress.append(
                    (
                        event.phase,
                        event.bytes_delta,
                        event.bytes_completed,
                        event.total_bytes,
                    )
                ),
            )

            self.assertEqual(
                progress,
                [
                    ("started", 0, 0, 2500),
                    ("advanced", 1024, 1024, 2500),
                    ("advanced", 1024, 2048, 2500),
                    ("advanced", 452, 2500, 2500),
                ],
            )
            self.assertEqual(len(reports), 1)
            result = reports[0].result
            assert result is not None
            self.assertEqual(result.path.read_bytes(), VideoResponse.content)
            self.assertEqual(len(GoodClient.instances), 1)
            self.assertTrue(GoodClient.instances[0].closed)

    def test_download_many_reuses_one_client_per_worker_thread(self):
        GoodClient.instances.clear()

        with TemporaryDirectory() as directory:
            service = AniCatService(
                download_options(
                    output_dir=Path(directory),
                    concurrency=1,
                    chunk_size=1024,
                ),
                client_factory=GoodClient,
            )

            reports = service.download_many(
                [
                    EpisodeJob(url="https://anime1.me/1"),
                    EpisodeJob(url="https://anime1.me/2"),
                ]
            )

            self.assertEqual(len(reports), 2)
            self.assertEqual(len(GoodClient.instances), 1)
            self.assertTrue(GoodClient.instances[0].closed)

    def test_collect_episode_urls_closes_client(self):
        GoodClient.instances.clear()

        service = AniCatService(
            download_options(output_dir=Path("unused")),
            client_factory=GoodClient,
        )

        jobs = service.collect_episode_urls(["https://anime1.me/1"])

        self.assertEqual(jobs, [EpisodeJob(url="https://anime1.me/1")])
        self.assertEqual(len(GoodClient.instances), 1)
        self.assertTrue(GoodClient.instances[0].closed)

    def test_download_one_supports_anime1_pw_direct_source(self):
        DirectClient.instances.clear()

        with TemporaryDirectory() as directory:
            service = AniCatService(
                download_options(output_dir=Path(directory), chunk_size=1024),
                client_factory=DirectClient,
            )

            report = service.download_one("https://anime1.pw/349")

            result = report.result
            assert result is not None
            self.assertEqual(result.path.read_bytes(), VideoResponse.content)
            self.assertEqual(
                DirectClient.instances[0].stream_calls,
                [("https://pwvideo.example/60/6.mp4?h=token&e=1", {})],
            )
            self.assertTrue(DirectClient.instances[0].closed)

    def test_season_download_places_episode_under_anime_name_subfolder(self):
        with TemporaryDirectory() as directory:
            service = AniCatService(
                download_options(output_dir=Path(directory), chunk_size=1024),
                client_factory=SeasonClient,
            )

            jobs = service.collect_episode_urls(["https://anime1.me/category/demo"])
            self.assertEqual(
                jobs,
                [
                    EpisodeJob(url="https://anime1.me/1", anime_name="Demo Anime"),
                    EpisodeJob(url="https://anime1.me/2", anime_name="Demo Anime"),
                ],
            )

            reports = service.download_many(jobs)

            result = reports[0].result
            assert result is not None
            self.assertEqual(result.path.parent, Path(directory) / "Demo Anime")
            self.assertEqual(result.path.read_bytes(), VideoResponse.content)

    def test_standalone_episode_download_resolves_anime_name_via_series_link(self):
        with TemporaryDirectory() as directory:
            service = AniCatService(
                download_options(output_dir=Path(directory), chunk_size=1024),
                client_factory=StandaloneEpisodeClient,
            )

            reports = service.download_many([EpisodeJob(url="https://anime1.me/29592")])

            result = reports[0].result
            assert result is not None
            self.assertEqual(result.path.parent, Path(directory) / "Demo Anime Full Title")

    def test_standalone_episode_download_falls_back_to_stripped_title_subfolder(self):
        with TemporaryDirectory() as directory:
            service = AniCatService(
                download_options(output_dir=Path(directory), chunk_size=1024),
                client_factory=StandaloneEpisodeNoSeriesLinkClient,
            )

            reports = service.download_many([EpisodeJob(url="https://anime1.me/29592")])

            result = reports[0].result
            assert result is not None
            self.assertEqual(result.path.parent, Path(directory) / "Demo Anime")

    def test_collect_episode_urls_filters_season_by_episodes(self):
        service = AniCatService(
            download_options(output_dir=Path("unused")),
            client_factory=SeasonClient,
        )

        jobs = service.collect_episode_urls(
            ["https://anime1.me/category/demo"],
            episodes=frozenset({2}),
        )

        self.assertEqual(
            jobs,
            [EpisodeJob(url="https://anime1.me/2", anime_name="Demo Anime")],
        )

    def test_collect_episode_urls_warns_about_missing_requested_episodes(self):
        service = AniCatService(
            download_options(output_dir=Path("unused")),
            client_factory=SeasonClient,
        )

        with self.assertLogs("anicat.service", level="WARNING") as logs:
            jobs = service.collect_episode_urls(
                ["https://anime1.me/category/demo"],
                episodes=frozenset({2, 5}),
            )

        self.assertEqual(
            jobs,
            [EpisodeJob(url="https://anime1.me/2", anime_name="Demo Anime")],
        )
        self.assertIn("not found", logs.output[0])
        self.assertIn("5", logs.output[0])

    def test_existing_file_is_skipped_without_resolving_a_stream(self):
        client = DenyingClient(denials=99)

        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "Demo Anime"
            output_dir.mkdir()
            (output_dir / "Demo Anime [12].mp4").write_bytes(b"already downloaded")

            service = AniCatService(
                download_options(output_dir=Path(directory), chunk_size=3),
                client_factory=lambda: client,
            )

            report = service.download_one("https://anime1.me/29592")

            result = report.result
            assert result is not None
            self.assertEqual(result.status, "skipped")
            self.assertEqual(result.bytes_written, len(b"already downloaded"))

        # The page fetch is unavoidable (it names the file), but nothing past
        # it should run: no API call, and no stream request to be denied.
        self.assertEqual(client.api_calls, 0)
        self.assertEqual(client.stream_calls, [])

    def test_overwrite_still_resolves_an_existing_file(self):
        client = DenyingClient(denials=0)

        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "Demo Anime"
            output_dir.mkdir()
            (output_dir / "Demo Anime [12].mp4").write_bytes(b"stale")

            service = AniCatService(
                download_options(output_dir=Path(directory), chunk_size=3, overwrite=True),
                client_factory=lambda: client,
            )

            report = service.download_one("https://anime1.me/29592")

            result = report.result
            assert result is not None
            self.assertEqual(result.status, "downloaded")

        self.assertEqual(client.api_calls, 1)

    def test_expired_credentials_are_re_resolved_and_the_download_resumes(self):
        client = DenyingClient()

        with TemporaryDirectory() as directory:
            service = AniCatService(
                download_options(output_dir=Path(directory), chunk_size=3),
                client_factory=lambda: client,
            )

            report = service.download_one("https://anime1.me/29592")

            result = report.result
            assert result is not None
            self.assertEqual(result.path.read_bytes(), b"abcdef")

        # Fresh credentials, and a retry that resumes instead of restarting.
        self.assertEqual(client.api_calls, 2)
        first_url, first_cookies, first_headers = client.stream_calls[0]
        second_url, second_cookies, second_headers = client.stream_calls[1]
        self.assertEqual(first_cookies, {"e": "e1", "p": "p1", "h": "h1"})
        self.assertEqual(second_cookies, {"e": "e2", "p": "p2", "h": "h2"})
        self.assertNotEqual(first_url, second_url)
        self.assertEqual(first_headers, {})
        self.assertEqual(second_headers, {"Range": "bytes=3-"})

    def test_denial_that_survives_every_re_resolution_is_reported_as_failed(self):
        client = DenyingClient(denials=99)

        with TemporaryDirectory() as directory:
            service = AniCatService(
                download_options(
                    output_dir=Path(directory),
                    chunk_size=3,
                    resolve_attempts=2,
                ),
                client_factory=lambda: client,
            )

            report = service.download_one("https://anime1.me/29592")

        self.assertIsNone(report.result)
        error = report.error
        assert error is not None
        self.assertIn("credentials were rejected", error)
        self.assertEqual(client.api_calls, 2)

    def test_bot_mitigation_denial_is_reported_with_actionable_guidance(self):
        client = DenyingClient(denials=99, denial_headers={"cf-mitigated": "challenge"})
        sleeps: list[float] = []

        with TemporaryDirectory() as directory:
            service = AniCatService(
                download_options(
                    output_dir=Path(directory),
                    chunk_size=3,
                    resolve_attempts=2,
                ),
                client_factory=lambda: client,
                sleeper=sleeps.append,
            )

            report = service.download_one("https://anime1.me/29592")

        error = report.error
        assert error is not None
        self.assertIn("anti-bot protection", error)
        self.assertIn("--concurrency", error)
        # A block backs off despite the zero-delay pacing used in these tests.
        self.assertTrue(any(delay > 0 for delay in sleeps))

    def test_retry_budget_stops_recovery_before_the_attempts_run_out(self):
        client = DenyingClient(denials=99)
        clock = iter([0.0, 0.0, 10_000.0, 10_000.0])

        with TemporaryDirectory() as directory:
            service = AniCatService(
                download_options(
                    output_dir=Path(directory),
                    chunk_size=3,
                    resolve_attempts=10,
                    retry_budget=60.0,
                ),
                client_factory=lambda: client,
                clock=lambda: next(clock),
            )

            report = service.download_one("https://anime1.me/29592")

        self.assertIsNotNone(report.error)
        self.assertEqual(client.api_calls, 1)

    def test_circuit_breaker_pauses_workers_after_repeated_denials(self):
        client = DenyingClient(denials=99)
        sleeps: list[float] = []

        with TemporaryDirectory() as directory:
            service = AniCatService(
                download_options(
                    output_dir=Path(directory),
                    chunk_size=3,
                    resolve_attempts=2,
                    circuit_breaker_threshold=2,
                    circuit_breaker_cooldown=30.0,
                ),
                client_factory=lambda: client,
                sleeper=sleeps.append,
            )

            with self.assertLogs("anicat.pacing", level="WARNING") as logs:
                service.download_many(
                    [
                        EpisodeJob(url="https://anime1.me/29592"),
                        EpisodeJob(url="https://anime1.me/29593"),
                    ]
                )

        output = "".join(logs.output)
        self.assertIn("Circuit breaker tripped", output)
        self.assertIn("Circuit breaker open", output)
        # The second episode waits out the cooldown before trying.
        self.assertAlmostEqual(max(sleeps), 30.0, delta=1.0)

    def test_workers_are_staggered_and_paced_between_episodes(self):
        sleeps: list[float] = []
        GoodClient.instances.clear()

        with TemporaryDirectory() as directory:
            service = AniCatService(
                download_options(
                    output_dir=Path(directory),
                    concurrency=1,
                    chunk_size=1024,
                    min_delay=2.0,
                    max_delay=2.0,
                    stagger=1.0,
                ),
                client_factory=GoodClient,
                sleeper=sleeps.append,
            )

            service.download_many(
                [
                    EpisodeJob(url="https://anime1.me/1"),
                    EpisodeJob(url="https://anime1.me/2"),
                ]
            )

        # One stagger before the first request, then one gap before the next.
        self.assertEqual(len(sleeps), 2)
        self.assertLessEqual(sleeps[0], 1.0)
        self.assertEqual(sleeps[1], 2.0)

    def test_collect_episode_urls_never_filters_explicit_episode_urls(self):
        service = AniCatService(
            download_options(output_dir=Path("unused")),
            client_factory=GoodClient,
        )

        jobs = service.collect_episode_urls(
            ["https://anime1.me/1"],
            episodes=frozenset({99}),
        )

        self.assertEqual(jobs, [EpisodeJob(url="https://anime1.me/1")])


if __name__ == "__main__":
    unittest.main()
