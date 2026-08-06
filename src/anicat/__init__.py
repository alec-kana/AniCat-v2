"""AniCat core package."""

import logging
from importlib.metadata import PackageNotFoundError, version

from .client import Anime1Client
from .errors import AccessDeniedError, AniCatError, DownloadError, FetchError, ParseError
from .models import DownloadProgressEvent, DownloadResult, Episode, EpisodeJob, JobReport
from .options import DownloadOptions
from .service import AniCatService

__all__ = [
    "AccessDeniedError",
    "AniCatError",
    "AniCatService",
    "Anime1Client",
    "DownloadError",
    "DownloadOptions",
    "DownloadProgressEvent",
    "DownloadResult",
    "Episode",
    "EpisodeJob",
    "FetchError",
    "JobReport",
    "ParseError",
    "__version__",
]

try:
    # Read from installed metadata so this can never drift from pyproject.
    __version__ = version("anicat-v2")
except PackageNotFoundError:
    __version__ = "0.0.0+source"

logging.getLogger(__name__).addHandler(logging.NullHandler())
