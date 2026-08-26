"""与平台和界面框架无关的领域类型。"""

from bili_subtitle.domain.errors import (
    AccessDeniedError,
    InputError,
    InvalidPageError,
    MetadataError,
    NetworkError,
    PlatformResponseError,
    RedirectError,
    UnsupportedVideoType,
    VideoNotFoundError,
    VideoNotReadyError,
)
from bili_subtitle.domain.models import (
    PageSelection,
    SelectionSource,
    VideoAccessMode,
    VideoCapabilities,
    VideoContainerType,
    VideoMetadata,
    VideoPage,
    VideoType,
)

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
    "UnsupportedVideoType",
    "VideoAccessMode",
    "VideoCapabilities",
    "VideoContainerType",
    "VideoMetadata",
    "VideoNotReadyError",
    "VideoNotFoundError",
    "VideoPage",
    "VideoType",
]
