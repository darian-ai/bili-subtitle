"""视频与分集领域模型。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from bili_subtitle.domain.errors import PlatformResponseError, SubtitlePlatformResponseError

_BVID_PATTERN = re.compile(r"BV[A-Za-z0-9]{10}\Z")


@dataclass(frozen=True, slots=True)
class VideoPage:
    """一个普通 UGC 投稿中的分集。"""

    number: int
    cid: int
    title: str

    def __post_init__(self) -> None:
        if self.number <= 0 or self.cid <= 0:
            raise PlatformResponseError("平台返回了无效的分集标识。")


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    """经过结构校验的视频元数据。"""

    aid: int
    bvid: str
    title: str
    pages: tuple[VideoPage, ...]

    def __post_init__(self) -> None:
        if self.aid <= 0 or _BVID_PATTERN.fullmatch(self.bvid) is None or not self.pages:
            raise PlatformResponseError("平台返回了无效的视频元数据。")
        numbers = [page.number for page in self.pages]
        if len(numbers) != len(set(numbers)):
            raise PlatformResponseError("平台返回了重复的分集序号。")


class SelectionSource(Enum):
    """最终分集选择由何种输入决定。"""

    DEFAULT_ALL = "default_all"
    URL_PAGE = "url_page"
    EXPLICIT_PAGE = "explicit_page"
    EXPLICIT_ALL = "explicit_all"


@dataclass(frozen=True, slots=True)
class PageSelection:
    """一次命令确定的视频及有序分集集合。"""

    video: VideoMetadata
    pages: tuple[VideoPage, ...]
    source: SelectionSource
    notices: tuple[str, ...] = ()


class SubtitleTrackKind(Enum):
    HUMAN = "human"
    AI = "ai"


@dataclass(frozen=True, slots=True)
class SubtitleTrack:
    track_id: int
    language: str
    display_name: str
    kind: SubtitleTrackKind

    def __post_init__(self) -> None:
        if (
            isinstance(self.track_id, bool)
            or self.track_id <= 0
            or not self.language
            or not self.display_name
        ):
            raise SubtitlePlatformResponseError("平台返回了无效的字幕轨道。")


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    start: Decimal
    end: Decimal
    text: str

    def __post_init__(self) -> None:
        if (
            not self.start.is_finite()
            or not self.end.is_finite()
            or self.start < 0
            or self.end < self.start
        ):
            raise SubtitlePlatformResponseError("平台返回了无效的字幕时间。")


@dataclass(frozen=True, slots=True)
class SubtitleBody:
    """同一次正文响应的原始字节与已校验片段。"""

    raw_json: bytes
    cues: tuple[SubtitleCue, ...]
