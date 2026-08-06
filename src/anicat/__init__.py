"""AniCat core package."""

import logging

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

__version__ = "0.1.0"

logging.getLogger(__name__).addHandler(logging.NullHandler())
