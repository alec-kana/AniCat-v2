from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .constants import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CONCURRENCY,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_OUTPUT_DIR_NAME,
    DEFAULT_READ_TIMEOUT,
    DEFAULT_RETRIES,
    PLAIN_PROGRESS_ENV_VAR,
)
from .errors import AniCatError
from .logging_config import configure_logging
from .models import EpisodeJob, JobReport
from .options import DownloadOptions
from .progress import (
    format_size,
    plain_download_progress,
    rich_download_progress,
    supports_rich_live,
)
from .service import AniCatService
from .urls import parse_episode_selector, split_urls

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2

_TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


def env_flag(name: str) -> bool:
    """Read a boolean CLI-flag default from an environment variable."""

    return os.environ.get(name, "").strip().lower() in _TRUTHY_ENV_VALUES


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""

    parser = argparse.ArgumentParser(
        prog="anicat",
        description="Download Anime1 episodes from episode or category URLs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  All downloads completed or were skipped\n"
            "  1  At least one URL failed or no episode was found\n"
            "  2  Invalid CLI usage or options"
        ),
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="Anime1 episode/category URLs. Whitespace and commas are accepted.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path.cwd() / DEFAULT_OUTPUT_DIR_NAME,
        help=f"Output directory. Default: ./{DEFAULT_OUTPUT_DIR_NAME}",
    )
    parser.add_argument(
        "-e",
        "--episodes",
        type=str,
        default=None,
        metavar="SPEC",
        help=(
            "Restrict category/season URLs to these episode numbers, e.g. '15-17' "
            "or '1,3,5-8'. Explicit episode URLs are never filtered."
        ),
    )
    parser.add_argument(
        "-c",
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Concurrent episode downloads. Default: {DEFAULT_CONCURRENCY}",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_READ_TIMEOUT,
        help=f"HTTP read timeout in seconds. Default: {DEFAULT_READ_TIMEOUT:g}",
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=DEFAULT_CONNECT_TIMEOUT,
        help=f"HTTP connect timeout in seconds. Default: {DEFAULT_CONNECT_TIMEOUT:g}",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=f"HTTP and stream retry count. Default: {DEFAULT_RETRIES}",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"Download chunk size in bytes. Default: {DEFAULT_CHUNK_SIZE}",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Discard existing .part files instead of resuming.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing completed files.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bar.",
    )
    parser.add_argument(
        "--plain-progress",
        action="store_true",
        default=env_flag(PLAIN_PROGRESS_ENV_VAR),
        help=(
            "Force line-based progress output instead of the Rich live bar. Use this on "
            "phone terminal apps (e.g. a-shell) where the live bar reports itself as a "
            f"compatible terminal but never actually redraws in place. Defaults to on if "
            f"the {PLAIN_PROGRESS_ENV_VAR} environment variable is set to a truthy value."
        ),
    )
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Show diagnostic logs. Use -vv for HTTP-level debug details.",
    )
    verbosity_group.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress diagnostic logs except errors. Summary output is unchanged.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show version and exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the AniCat CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(verbose=args.verbose, quiet=args.quiet)
    try:
        options = options_from_args(args)
    except ValueError as error:
        print(f"argument error: {error}", file=sys.stderr)
        return EXIT_USAGE

    episodes = None
    if args.episodes is not None:
        try:
            episodes = parse_episode_selector(args.episodes)
        except AniCatError as error:
            print(f"argument error: {error}", file=sys.stderr)
            return EXIT_USAGE

    input_urls = split_urls(args.urls)
    if not input_urls:
        if not sys.stdin.isatty():
            print("No URL provided.", file=sys.stderr)
            return EXIT_USAGE
        try:
            input_urls = split_urls([input("? Anime1 URL：")])
        except EOFError:
            print("No URL provided.", file=sys.stderr)
            return EXIT_USAGE
    if not input_urls:
        print("No URL provided.", file=sys.stderr)
        return EXIT_USAGE

    service = AniCatService(options)

    try:
        episode_jobs = service.collect_episode_urls(input_urls, episodes=episodes)
    except AniCatError as error:
        print(f"- {error}", file=sys.stderr)
        return EXIT_FAILURE

    if not episode_jobs:
        print("- No episode found.", file=sys.stderr)
        return EXIT_FAILURE

    started_at = time.perf_counter()
    reports = run_downloads(service, options, episode_jobs)
    elapsed = time.perf_counter() - started_at

    downloaded = [item for item in reports if item.result and item.result.status == "downloaded"]
    skipped = [item for item in reports if item.result and item.result.status == "skipped"]
    failed = [item for item in reports if item.error]

    for item in reports:
        if item.result:
            marker = "+" if item.result.status == "downloaded" else "="
            size = format_size(item.result.bytes_written)
            print(f"{marker} {item.result.status}: {item.result.episode.title} [{size}]")
            print(f"  -> {item.result.path}")
        else:
            print(f"- failed: {item.url}")
            print(f"  {item.error}")

    print(
        f"+ done in {elapsed:.2f}s: "
        f"{len(downloaded)} downloaded, {len(skipped)} skipped, {len(failed)} failed"
    )
    return EXIT_FAILURE if failed else EXIT_OK


def options_from_args(args: argparse.Namespace) -> DownloadOptions:
    """Convert parsed CLI arguments into service runtime options."""

    return DownloadOptions(
        output_dir=args.output,
        concurrency=args.concurrency,
        timeout=args.timeout,
        connect_timeout=args.connect_timeout,
        retries=args.retries,
        chunk_size=args.chunk_size,
        resume=not args.no_resume,
        overwrite=args.overwrite,
        progress=not args.no_progress,
        plain_progress=args.plain_progress,
    )


def run_downloads(
    service: AniCatService,
    options: DownloadOptions,
    episode_jobs: list[EpisodeJob],
) -> list[JobReport]:
    """Run downloads with or without Rich progress rendering."""

    if not options.progress:
        return service.download_many(episode_jobs)

    use_rich = not options.plain_progress and supports_rich_live()
    progress_factory = rich_download_progress if use_rich else plain_download_progress
    with progress_factory(len(episode_jobs)) as progress:
        return service.download_many(
            episode_jobs,
            on_progress=progress.on_progress,
            on_done=progress.on_done,
        )
