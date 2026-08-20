"""视频与分集领域模型。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from bili_subtitle.domain.errors import PlatformResponseError

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
