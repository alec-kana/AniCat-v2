import os
import signal
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from anicat import AnimeEntry, EpisodeJob, __version__
from anicat.cli import (
    EXIT_FAILURE,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_USAGE,
    build_parser,
    env_flag,
    main,
    options_from_args,
    run_downloads,
    termination_as_interrupt,
)
from anicat.constants import KEEP_PARTIAL_ENV_VAR, PLAIN_PROGRESS_ENV_VAR


class CliTests(unittest.TestCase):
    def test_missing_url_does_not_prompt_when_stdin_is_not_tty(self):
        with (
            patch("sys.stdin.isatty", return_value=False),
            patch("builtins.input", side_effect=AssertionError("input should not run")),
        ):
            self.assertEqual(main([]), EXIT_USAGE)

    def test_invalid_options_return_argument_error(self):
        self.assertEqual(main(["--timeout", "0", "https://anime1.me/1"]), EXIT_USAGE)

    def test_invalid_connect_timeout_returns_argument_error(self):
        self.assertEqual(main(["--connect-timeout", "0", "https://anime1.me/1"]), EXIT_USAGE)

    def test_invalid_episodes_selector_returns_argument_error(self):
        self.assertEqual(main(["--episodes", "abc", "https://anime1.me/1"]), EXIT_USAGE)

    def test_episodes_flag_is_parsed(self):
        args = build_parser().parse_args(["--episodes", "15-17", "https://anime1.me/1"])

        self.assertEqual(args.episodes, "15-17")

    def test_timeout_flags_build_request_timeout_tuple(self):
        args = build_parser().parse_args(
            [
                "--connect-timeout",
                "2",
                "--timeout",
                "9",
                "https://anime1.me/1",
            ]
        )

        self.assertEqual(options_from_args(args).request_timeout, (2, 9))

    def test_pacing_and_recovery_flags_reach_options(self):
        args = build_parser().parse_args(
            [
                "--min-delay",
                "2",
                "--max-delay",
                "6",
                "--stagger-start",
                "3",
                "--host-interval",
                "1.5",
                "--resolve-attempts",
                "5",
                "--retry-budget",
                "120",
                "--circuit-breaker-threshold",
                "8",
                "--circuit-breaker-cooldown",
                "90",
                "https://anime1.me/1",
            ]
        )

        options = options_from_args(args)

        self.assertEqual(options.min_delay, 2)
        self.assertEqual(options.max_delay, 6)
        self.assertEqual(options.stagger, 3)
        self.assertEqual(options.host_interval, 1.5)
        self.assertEqual(options.resolve_attempts, 5)
        self.assertEqual(options.retry_budget, 120)
        self.assertEqual(options.circuit_breaker_threshold, 8)
        self.assertEqual(options.circuit_breaker_cooldown, 90)

    def test_no_pacing_zeroes_every_delay_and_wins_over_explicit_flags(self):
        args = build_parser().parse_args(["--no-pacing", "--min-delay", "5", "https://anime1.me/1"])

        options = options_from_args(args)

        self.assertEqual(options.min_delay, 0.0)
        self.assertEqual(options.max_delay, 0.0)
        self.assertEqual(options.stagger, 0.0)
        self.assertEqual(options.host_interval, 0.0)

    def test_inverted_delay_range_returns_argument_error(self):
        self.assertEqual(
            main(["--min-delay", "9", "--max-delay", "1", "https://anime1.me/1"]),
            EXIT_USAGE,
        )

    def test_verbose_flag_counts_diagnostic_level(self):
        args = build_parser().parse_args(["-vv", "https://anime1.me/1"])

        self.assertEqual(args.verbose, 2)
        self.assertFalse(args.quiet)

    def test_verbose_and_quiet_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
            build_parser().parse_args(["-vv", "--quiet", "https://anime1.me/1"])

    def test_version_flag_prints_package_version(self):
        stdout = StringIO()

        with self.assertRaises(SystemExit) as error, redirect_stdout(stdout):
            build_parser().parse_args(["--version"])

        self.assertEqual(error.exception.code, 0)
        self.assertIn(__version__, stdout.getvalue())

    def test_quiet_flag_parse(self):
        args = build_parser().parse_args(["--quiet", "https://anime1.me/1"])

        self.assertEqual(args.verbose, 0)
        self.assertTrue(args.quiet)

    def test_plain_progress_flag_sets_options(self):
        args = build_parser().parse_args(["--plain-progress", "https://anime1.me/1"])

        self.assertTrue(options_from_args(args).plain_progress)

    def test_plain_progress_defaults_to_false(self):
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop(PLAIN_PROGRESS_ENV_VAR, None)
            args = build_parser().parse_args(["https://anime1.me/1"])

        self.assertFalse(options_from_args(args).plain_progress)

    def test_plain_progress_env_var_sets_default_on(self):
        with patch.dict("os.environ", {PLAIN_PROGRESS_ENV_VAR: "1"}):
            args = build_parser().parse_args(["https://anime1.me/1"])

        self.assertTrue(options_from_args(args).plain_progress)

    def test_env_flag_recognizes_common_truthy_spellings(self):
        for value in ("1", "true", "True", "yes", "on"):
            with patch.dict("os.environ", {PLAIN_PROGRESS_ENV_VAR: value}):
                self.assertTrue(env_flag(PLAIN_PROGRESS_ENV_VAR), msg=value)

    def test_env_flag_treats_unset_or_zero_as_false(self):
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop(PLAIN_PROGRESS_ENV_VAR, None)
            self.assertFalse(env_flag(PLAIN_PROGRESS_ENV_VAR))

        with patch.dict("os.environ", {PLAIN_PROGRESS_ENV_VAR: "0"}):
            self.assertFalse(env_flag(PLAIN_PROGRESS_ENV_VAR))

    def test_plain_progress_flag_forces_plain_renderer_even_on_a_live_capable_terminal(self):
        args = build_parser().parse_args(["--plain-progress", "https://anime1.me/1"])
        options = options_from_args(args)
        service = MagicMock()

        with (
            patch("anicat.cli.supports_rich_live", return_value=True),
            patch("anicat.cli.plain_download_progress") as plain_factory,
            patch("anicat.cli.rich_download_progress") as rich_factory,
        ):
            run_downloads(service, options, [])

        plain_factory.assert_called_once_with(0)
        rich_factory.assert_not_called()

    def test_search_subcommand_prints_titles_and_category_urls(self):
        entries = [
            AnimeEntry(
                anime_id=1935,
                title="GRAND BLUE 碧藍之海 第三季",
                episodes="連載中(07)",
                year="2026",
                season="夏",
                subtitle_group="",
                url="https://anime1.me/?cat=1935",
            )
        ]
        stdout = StringIO()

        with (
            # Pin the render width so table wrapping cannot break these assertions.
            patch.dict(os.environ, {"COLUMNS": "200"}),
            patch("anicat.cli.Anime1Client"),
            patch("anicat.cli.fetch_catalog", return_value=entries),
            redirect_stdout(stdout),
        ):
            self.assertEqual(main(["search", "碧藍之海"]), EXIT_OK)

        output = stdout.getvalue()
        self.assertIn("GRAND BLUE 碧藍之海 第三季", output)
        self.assertIn("https://anime1.me/?cat=1935", output)
        self.assertIn("1 result(s)", output)

    def test_search_without_match_returns_failure(self):
        with (
            patch("anicat.cli.Anime1Client"),
            patch("anicat.cli.fetch_catalog", return_value=[]),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main(["search", "no such anime"]), EXIT_FAILURE)

    def test_non_search_first_argument_still_uses_the_download_parser(self):
        with patch("anicat.cli.search_main", side_effect=AssertionError("search should not run")):
            self.assertEqual(main(["--timeout", "0", "https://anime1.me/1"]), EXIT_USAGE)

    def test_search_without_keyword_prompts_when_stdin_is_a_tty(self):
        stdout = StringIO()

        with (
            patch.dict(os.environ, {"COLUMNS": "200"}),
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", return_value="  碧藍之海  ") as prompt,
            patch("anicat.cli.Anime1Client"),
            patch("anicat.cli.fetch_catalog", return_value=[]),
            redirect_stdout(stdout),
            redirect_stderr(StringIO()),
        ):
            # No match is fine here; the point is that the prompt supplied the keyword.
            self.assertEqual(main(["search"]), EXIT_FAILURE)

        prompt.assert_called_once()

    def test_search_without_keyword_does_not_prompt_when_stdin_is_not_a_tty(self):
        with (
            patch("sys.stdin.isatty", return_value=False),
            patch("builtins.input", side_effect=AssertionError("input should not run")),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main(["search"]), EXIT_USAGE)

    def test_search_with_blank_keyword_returns_usage_error(self):
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", return_value="   "),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main(["search", "   "]), EXIT_USAGE)

    def test_keep_partial_defaults_to_false(self):
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop(KEEP_PARTIAL_ENV_VAR, None)
            args = build_parser().parse_args(["https://anime1.me/1"])

        self.assertFalse(options_from_args(args).keep_partial)

    def test_keep_partial_flag_and_env_var_set_options(self):
        args = build_parser().parse_args(["--keep-partial", "https://anime1.me/1"])
        self.assertTrue(options_from_args(args).keep_partial)

        with patch.dict("os.environ", {KEEP_PARTIAL_ENV_VAR: "1"}):
            args = build_parser().parse_args(["https://anime1.me/1"])
        self.assertTrue(options_from_args(args).keep_partial)

    def test_interrupted_download_exits_130_and_reports_cleanup(self):
        service = MagicMock()
        service.collect_episode_urls.return_value = [EpisodeJob(url="https://anime1.me/1")]
        service.removed_partials = [(Path("a.mp4.part"), 2048)]
        stdout = StringIO()
        stderr = StringIO()

        with (
            patch("anicat.cli.AniCatService", return_value=service),
            patch("anicat.cli.run_downloads", side_effect=KeyboardInterrupt),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            self.assertEqual(main(["https://anime1.me/1"]), EXIT_INTERRUPTED)

        self.assertIn("interrupted", stderr.getvalue())
        self.assertIn("removed 1 partial file(s), freeing 2.00 KB", stdout.getvalue())

    @unittest.skipUnless(hasattr(signal, "SIGTERM"), "platform has no SIGTERM")
    def test_sigterm_is_raised_as_keyboard_interrupt_then_restored(self):
        original = signal.getsignal(signal.SIGTERM)

        with self.assertRaises(KeyboardInterrupt), termination_as_interrupt():
            signal.raise_signal(signal.SIGTERM)

        self.assertIs(signal.getsignal(signal.SIGTERM), original)

    def test_exit_code_constants_match_documented_values(self):
        self.assertEqual(EXIT_OK, 0)
        self.assertEqual(EXIT_FAILURE, 1)
        self.assertEqual(EXIT_USAGE, 2)
        self.assertEqual(EXIT_INTERRUPTED, 130)


if __name__ == "__main__":
    unittest.main()
