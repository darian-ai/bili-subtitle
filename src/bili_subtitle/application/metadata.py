"""输入解析、元数据获取和分集选择的应用流程。"""

from __future__ import annotations

from typing import Protocol

from bili_subtitle.application.input_parser import (
    ParsedVideoInput,
    ShortVideoUrl,
    VideoReference,
    parse_video_input,
)
from bili_subtitle.domain.errors import (
    AccessDeniedError,
    InputError,
    InvalidPageError,
    RedirectError,
    UnsupportedVideoType,
    VideoNotReadyError,
)
from bili_subtitle.domain.models import (
    PageSelection,
    SelectionSource,
    VideoAccessMode,
    VideoMetadata,
    VideoType,
)

_OVERRIDE_NOTICE = "提示：显式分集选项已覆盖视频 URL 中的 p 参数。"


class MetadataPort(Protocol):
    """应用层所需的平台元数据能力。"""

    def resolve_short_url(self, url: str) -> str: ...

    def fetch_video(self, reference: VideoReference) -> VideoMetadata: ...


def resolve_selection(
    raw_input: str,
    *,
    page: int | None,
    all_pages: bool,
    metadata: MetadataPort,
) -> PageSelection:
    """解析输入、取得投稿并按公开优先级选择分集。"""
    if page is not None and all_pages:
        raise InputError("--page 与 --all-pages 不能同时使用。")
    if page is not None and page <= 0:
        raise InputError("--page 必须是正整数。")

    parsed = parse_video_input(raw_input)
    return resolve_parsed_selection(parsed, page=page, all_pages=all_pages, metadata=metadata)


def resolve_parsed_selection(
    parsed: ParsedVideoInput,
    *,
    page: int | None,
    all_pages: bool,
    metadata: MetadataPort,
) -> PageSelection:
    """Resolve an input that the CLI has already validated without I/O."""
    if isinstance(parsed, ShortVideoUrl):
        parsed = parse_video_input(metadata.resolve_short_url(parsed.url))
        if isinstance(parsed, ShortVideoUrl):
            raise RedirectError("短链没有解析到受支持的 Bilibili 视频页。")

    video = metadata.fetch_video(parsed)
    _ensure_supported_video(video)
    notices = (
        (_OVERRIDE_NOTICE,)
        if parsed.url_page is not None and (page is not None or all_pages)
        else ()
    )

    if page is not None:
        selected = tuple(item for item in video.pages if item.number == page)
        if not selected:
            raise InvalidPageError(f"投稿中不存在第 {page} 分集。")
        return PageSelection(video, selected, SelectionSource.EXPLICIT_PAGE, notices)
    if all_pages:
        return PageSelection(video, video.pages, SelectionSource.EXPLICIT_ALL, notices)
    if parsed.url_page is not None:
        selected = tuple(item for item in video.pages if item.number == parsed.url_page)
        if not selected:
            raise InvalidPageError(f"投稿中不存在第 {parsed.url_page} 分集。")
        return PageSelection(video, selected, SelectionSource.URL_PAGE)
    return PageSelection(video, video.pages, SelectionSource.DEFAULT_ALL)


def _ensure_supported_video(video: VideoMetadata) -> None:
    capabilities = video.capabilities
    if capabilities.video_type is not VideoType.STANDARD_UGC:
        raise UnsupportedVideoType("当前仅支持普通 UGC 视频，不支持互动或特殊播放器视频。")
    if capabilities.premiere:
        raise VideoNotReadyError("首映状态的视频暂不支持，请在首映结束后重试。")
    if capabilities.access_mode is VideoAccessMode.PREVIEW:
        raise AccessDeniedError("当前仅能访问视频预览，无法读取完整字幕。")
