"""Bilibili 视频元数据 HTTP 适配器。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast
from urllib.parse import urljoin

import httpx

from bili_subtitle.application.input_parser import VideoReference, is_allowed_redirect_host
from bili_subtitle.domain.errors import (
    AccessDeniedError,
    NetworkError,
    PlatformResponseError,
    RedirectError,
    VideoNotFoundError,
)
from bili_subtitle.domain.models import (
    VideoAccessMode,
    VideoCapabilities,
    VideoContainerType,
    VideoMetadata,
    VideoPage,
    VideoType,
)

_VIEW_API = "https://api.bilibili.com/x/web-interface/view"
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_NOT_FOUND_CODES = frozenset({-404, 62002, 62004})
_ACCESS_DENIED_CODES = frozenset({-403, -10403})
_DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
_DEFAULT_HEADERS = {"User-Agent": "bili-subtitle/0.1"}


def create_http_client() -> httpx.Client:
    """创建具有统一请求头、超时和手动重定向策略的客户端。"""
    return httpx.Client(timeout=_DEFAULT_TIMEOUT, headers=_DEFAULT_HEADERS, follow_redirects=False)


class BilibiliMetadataAdapter:
    """通过 Bilibili Web 接口取得投稿元数据。"""

    def __init__(self, client: httpx.Client, *, max_redirects: int = 5) -> None:
        self._client = client
        self._max_redirects = max_redirects

    def resolve_short_url(self, url: str) -> str:
        current = url
        visited: set[str] = set()
        for _ in range(self._max_redirects):
            if current in visited:
                raise RedirectError("b23.tv 短链形成了重定向循环。")
            visited.add(current)
            try:
                response = self._client.get(current, follow_redirects=False)
            except httpx.HTTPError as exc:
                raise NetworkError("解析 b23.tv 短链时网络访问失败。") from exc
            if response.status_code not in _REDIRECT_STATUSES:
                raise RedirectError("b23.tv 短链没有返回有效重定向。")
            location = response.headers.get("location")
            if not location:
                raise RedirectError("b23.tv 短链缺少重定向目标。")
            target = urljoin(current, location)
            if not is_allowed_redirect_host(target):
                raise RedirectError("b23.tv 短链跳转到了不受支持的地址。")
            if "b23.tv" not in (httpx.URL(target).host or "").lower():
                return target
            current = target
        raise RedirectError("b23.tv 短链重定向次数超过限制。")

    def fetch_video(self, reference: VideoReference) -> VideoMetadata:
        params = {"bvid": reference.bvid} if reference.bvid is not None else {"aid": reference.aid}
        try:
            response = self._client.get(_VIEW_API, params=params)
        except httpx.HTTPError as exc:
            raise NetworkError("获取视频元数据时网络访问失败。") from exc
        if response.status_code == 404:
            raise VideoNotFoundError("投稿不存在、已删除或当前不可见。")
        if response.status_code in {401, 403}:
            raise AccessDeniedError("当前访问无权查看该投稿。")
        if response.is_server_error:
            raise NetworkError("平台服务暂时不可用。")
        if response.is_error:
            raise PlatformResponseError("平台拒绝了元数据请求。")

        try:
            payload = cast(object, response.json())
        except ValueError as exc:
            raise PlatformResponseError("平台元数据响应不是有效 JSON。") from exc
        if not isinstance(payload, Mapping):
            raise PlatformResponseError("平台元数据响应结构异常。")
        typed_payload = cast(Mapping[str, object], payload)
        code = typed_payload.get("code")
        if code in _NOT_FOUND_CODES:
            raise VideoNotFoundError("投稿不存在、已删除或当前不可见。")
        if code in _ACCESS_DENIED_CODES:
            raise AccessDeniedError("当前访问无权查看该投稿。")
        if code != 0:
            raise PlatformResponseError("平台拒绝了元数据请求。")
        data = typed_payload.get("data")
        if not isinstance(data, Mapping):
            raise PlatformResponseError("平台元数据响应缺少 data 对象。")
        return _parse_video_data(cast(Mapping[object, object], data))


def _parse_video_data(data: Mapping[object, object]) -> VideoMetadata:
    aid = data.get("aid")
    bvid = data.get("bvid")
    title = data.get("title")
    raw_pages = data.get("pages")
    if (
        not isinstance(aid, int)
        or isinstance(aid, bool)
        or not isinstance(bvid, str)
        or not isinstance(title, str)
        or not isinstance(raw_pages, list)
        or not raw_pages
    ):
        raise PlatformResponseError("平台返回的视频字段缺失或类型错误。")

    pages: list[VideoPage] = []
    typed_pages = cast(list[object], raw_pages)
    for raw_page in typed_pages:
        if not isinstance(raw_page, Mapping):
            raise PlatformResponseError("平台返回的分集结构异常。")
        typed_page = cast(Mapping[str, object], raw_page)
        number = typed_page.get("page")
        cid = typed_page.get("cid")
        part = typed_page.get("part")
        if (
            not isinstance(number, int)
            or isinstance(number, bool)
            or not isinstance(cid, int)
            or isinstance(cid, bool)
            or not isinstance(part, str)
        ):
            raise PlatformResponseError("平台返回的分集字段缺失或类型错误。")
        pages.append(VideoPage(number, cid, part))
    return VideoMetadata(aid, bvid, title, tuple(pages), _parse_capabilities(data))


def _platform_flag(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    return None


def _parse_capabilities(data: Mapping[object, object]) -> VideoCapabilities:
    rights = data.get("rights")
    if not isinstance(rights, Mapping):
        return VideoCapabilities(video_type=VideoType.UNKNOWN)
    typed_rights = cast(Mapping[object, object], rights)

    stein = _platform_flag(typed_rights.get("is_stein_gate"))
    story = _platform_flag(data.get("is_story"))
    season = _platform_flag(data.get("is_season_display"))
    access_flags = (
        _platform_flag(data.get("is_chargeable_season")),
        _platform_flag(data.get("is_upower_exclusive")),
        _platform_flag(data.get("is_upower_play")),
        _platform_flag(typed_rights.get("ugc_pay")),
        _platform_flag(typed_rights.get("arc_pay")),
    )
    preview_flags = (
        _platform_flag(typed_rights.get("ugc_pay_preview")),
        _platform_flag(typed_rights.get("free_watch")),
    )
    if (
        stein is None
        or story is None
        or season is None
        or any(value is None for value in access_flags + preview_flags)
    ):
        return VideoCapabilities(video_type=VideoType.UNKNOWN)

    video_type = (
        VideoType.INTERACTIVE_UGC
        if stein
        else VideoType.STORY_UGC
        if story
        else VideoType.STANDARD_UGC
    )
    access_mode = (
        VideoAccessMode.PREVIEW
        if any(preview_flags)
        else VideoAccessMode.ENTITLED
        if any(access_flags)
        else VideoAccessMode.PUBLIC
    )
    premiere = data.get("premiere")
    return VideoCapabilities(
        video_type=video_type,
        container_type=(VideoContainerType.UGC_SEASON if season else VideoContainerType.STANDALONE),
        access_mode=access_mode,
        premiere=isinstance(premiere, Mapping) and len(cast(Mapping[object, object], premiere)) > 0,
    )
