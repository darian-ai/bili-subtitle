"""播放器字幕发现与正文即时下载。签名 URL 永不离开本模块。"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import cast
from urllib.parse import urlsplit, urlunsplit

import httpx

from bili_subtitle.domain.errors import (
    AuthenticationRequired,
    NoSubtitles,
    SubtitleAccessDenied,
    SubtitleNetworkError,
    SubtitlePlatformResponseError,
)
from bili_subtitle.domain.models import SubtitleBody, SubtitleCue, SubtitleTrack, SubtitleTrackKind

_PLAYER_API = "https://api.bilibili.com/x/player/v2"
_TRUSTED_SUFFIXES = (".bilibili.com", ".bilivideo.com", ".hdslb.com")


@dataclass(frozen=True, slots=True)
class _DiscoveredTrack:
    public: SubtitleTrack
    url: str | None = field(repr=False)


class BilibiliSubtitleAdapter:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self._pending: dict[tuple[str, int, SubtitleTrack], _DiscoveredTrack] = {}

    def discover(self, *, bvid: str, cid: int, aid: int | None = None) -> tuple[SubtitleTrack, ...]:
        self.discard_pending(bvid=bvid, cid=cid)
        discovered = self._discover_private(bvid=bvid, cid=cid, aid=aid)
        # Signed addresses stay private to this adapter and are consumed once by
        # download_selected.  Reusing the player response avoids a second request
        # whose short-lived address set can legitimately differ from discovery.
        for item in discovered:
            if (bvid, cid, item.public) in self._pending:
                self.discard_pending(bvid=bvid, cid=cid)
                raise SubtitlePlatformResponseError("字幕轨道身份重复。")
            self._pending[(bvid, cid, item.public)] = item
        return tuple(item.public for item in discovered)

    def download_selected(self, *, bvid: str, cid: int, selected: SubtitleTrack) -> SubtitleBody:
        match = self._pending.pop((bvid, cid, selected), None)
        if match is None:
            raise SubtitlePlatformResponseError("选定轨道不属于本次发现结果。")
        if match.url is None:
            raise SubtitleAccessDenied("字幕轨道当前不可访问。")
        response = self._get(_safe_subtitle_url(match.url))
        return _parse_body(response.content)

    def discard_pending(self, *, bvid: str, cid: int) -> None:
        """Drop every unconsumed signed address at the end of one page."""
        self._pending = {
            key: value for key, value in self._pending.items() if key[:2] != (bvid, cid)
        }

    def _discover_private(
        self, *, bvid: str, cid: int, aid: int | None
    ) -> tuple[_DiscoveredTrack, ...]:
        params: dict[str, str | int] = {"bvid": bvid, "cid": cid}
        if aid is not None:
            params["aid"] = aid
        response = self._get(_PLAYER_API, params=params, no_cache=True)
        payload = _response_payload(response)
        code = payload.get("code")
        if code in {-101, -111}:
            raise AuthenticationRequired("需要登录后访问字幕。")
        if code in {-403, -10403}:
            raise SubtitleAccessDenied("当前账号无权访问字幕。")
        if code != 0:
            raise SubtitlePlatformResponseError("平台拒绝了字幕轨道请求。")
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise SubtitlePlatformResponseError("字幕轨道响应结构异常。")
        typed_data = cast(Mapping[str, object], data)
        identities = {"aid": aid, "bvid": bvid, "cid": cid}
        if aid is not None and any(
            typed_data.get(key) != expected for key, expected in identities.items()
        ):
            raise SubtitlePlatformResponseError("字幕轨道响应来源与请求视频不一致。")
        subtitle = cast(Mapping[object, object], data).get("subtitle")
        if subtitle is None:
            raise NoSubtitles("该分集没有可见字幕。")
        if not isinstance(subtitle, Mapping):
            raise SubtitlePlatformResponseError("字幕轨道响应结构异常。")
        raw_tracks = cast(Mapping[object, object], subtitle).get("subtitles")
        if not isinstance(raw_tracks, list):
            raise SubtitlePlatformResponseError("字幕轨道列表结构异常。")
        if not raw_tracks:
            raise NoSubtitles("该分集没有可见字幕。")
        return tuple(_parse_track(item) for item in cast(list[object], raw_tracks))

    def _get(
        self,
        url: str,
        *,
        params: dict[str, str | int] | None = None,
        no_cache: bool = False,
    ) -> httpx.Response:
        try:
            headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"} if no_cache else None
            response = self._client.get(url, params=params, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError):
            raise SubtitleNetworkError("字幕网络访问失败。") from None
        if response.status_code == 401:
            raise AuthenticationRequired("需要登录后访问字幕。")
        if response.status_code == 403:
            raise SubtitleAccessDenied("当前账号无权访问字幕。")
        if response.is_server_error:
            raise SubtitleNetworkError("字幕服务暂时不可用。")
        if response.is_error:
            raise SubtitlePlatformResponseError("平台拒绝了字幕请求。")
        return response


def _response_payload(response: httpx.Response) -> Mapping[str, object]:
    try:
        payload = cast(object, response.json())
    except ValueError:
        raise SubtitlePlatformResponseError("字幕轨道响应不是有效 JSON。") from None
    if not isinstance(payload, Mapping):
        raise SubtitlePlatformResponseError("字幕轨道响应结构异常。")
    return cast(Mapping[str, object], payload)


def _parse_body(raw: bytes) -> SubtitleBody:
    try:
        decoded = raw.decode("utf-8")
        payload = json.loads(
            decoded,
            parse_float=Decimal,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        # Parser exceptions can embed the source document.  Suppress their
        # context so response content cannot escape via tracebacks or repr.
        raise SubtitlePlatformResponseError("字幕正文不是有效 JSON。") from None
    if not isinstance(payload, Mapping):
        raise SubtitlePlatformResponseError("字幕正文结构异常。")
    body = cast(Mapping[object, object], payload).get("body")
    if not isinstance(body, list):
        raise SubtitlePlatformResponseError("字幕正文缺少片段列表。")
    cues = tuple(_parse_cue(item) for item in cast(list[object], body))
    return SubtitleBody(raw, cues)


def _parse_track(raw: object) -> _DiscoveredTrack:
    if not isinstance(raw, Mapping):
        raise SubtitlePlatformResponseError("字幕轨道结构异常。")
    item = cast(Mapping[str, object], raw)
    track_id, language, name, url = (
        item.get("id"),
        item.get("lan"),
        item.get("lan_doc"),
        item.get("subtitle_url"),
    )
    if (
        not isinstance(track_id, int)
        or isinstance(track_id, bool)
        or track_id <= 0
        or not isinstance(language, str)
        or not language
        or not isinstance(name, str)
        or not name
        or not isinstance(url, str)
    ):
        raise SubtitlePlatformResponseError("字幕轨道字段缺失或类型错误。")
    kind = _parse_track_kind(item)
    # An advertised track with no body address is distinct from an empty track
    # collection.  Preserve its public identity and classify access on download.
    return _DiscoveredTrack(SubtitleTrack(track_id, language, name, kind), url or None)


def _parse_track_kind(item: Mapping[str, object]) -> SubtitleTrackKind:
    """兼容播放器字幕轨道的新旧 AI 类型字段。"""
    marker = item.get("is_ai") if "is_ai" in item else item.get("type")
    if (
        not isinstance(marker, (bool, int))
        or isinstance(marker, float)
        or marker not in {False, True}
    ):
        raise SubtitlePlatformResponseError("字幕轨道字段缺失或类型错误。")
    return SubtitleTrackKind.AI if bool(marker) else SubtitleTrackKind.HUMAN


def _safe_subtitle_url(value: str) -> str:
    candidate = f"https:{value}" if value.startswith("//") else value
    parts = urlsplit(candidate)
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        raise SubtitlePlatformResponseError("平台返回了不安全的字幕地址。") from None
    if (
        parts.scheme != "https"
        or parts.username is not None
        or parts.password is not None
        or port not in {None, 443}
        or not any(host == suffix[1:] or host.endswith(suffix) for suffix in _TRUSTED_SUFFIXES)
    ):
        raise SubtitlePlatformResponseError("平台返回了不安全的字幕地址。")
    return urlunsplit(parts)


def _parse_cue(raw: object) -> SubtitleCue:
    if not isinstance(raw, Mapping):
        raise SubtitlePlatformResponseError("字幕片段结构异常。")
    item = cast(Mapping[str, object], raw)
    start, end, text = item.get("from"), item.get("to"), item.get("content")
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, (int, Decimal))
        or not isinstance(end, (int, Decimal))
        or not isinstance(text, str)
    ):
        raise SubtitlePlatformResponseError("字幕片段字段缺失或类型错误。")
    if not math.isfinite(start) or not math.isfinite(end):
        raise SubtitlePlatformResponseError("字幕片段时间无效。")
    try:
        return SubtitleCue(Decimal(str(start)), Decimal(str(end)), text)
    except (InvalidOperation, ValueError) as exc:
        raise SubtitlePlatformResponseError("字幕片段时间无效。") from exc
