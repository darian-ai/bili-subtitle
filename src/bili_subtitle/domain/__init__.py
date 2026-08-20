"""与平台和界面框架无关的领域类型。"""

from bili_subtitle.domain.errors import (
    AccessDeniedError,
    InputError,
    InvalidPageError,
    MetadataError,
    NetworkError,
    PlatformResponseError,
    RedirectError,
    VideoNotFoundError,
)
from bili_subtitle.domain.models import PageSelection, SelectionSource, VideoMetadata, VideoPage

__all__ = [
    "AccessDeniedError",
    "InputError",
    "InvalidPageError",
    "MetadataError",
    "NetworkError",
    "PageSelection",
    "PlatformResponseError",
    "RedirectError",
    "SelectionSource",
    "VideoMetadata",
    "VideoNotFoundError",
    "VideoPage",
]
