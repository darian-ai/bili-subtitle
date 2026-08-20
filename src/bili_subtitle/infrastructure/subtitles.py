"""播放器字幕发现与正文即时下载。签名 URL 永不离开本模块。"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
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
from bili_subtitle.domain.models import SubtitleCue, SubtitleTrack, SubtitleTrackKind

_PLAYER_API = "https://api.bilibili.com/x/player/v2"
_TRUSTED_SUFFIXES = (".bilibili.com", ".bilivideo.com")


@dataclass(frozen=True, slots=True)
class SubtitleBody:
    raw_json: bytes
    cues: tuple[SubtitleCue, ...]


@dataclass(frozen=True, slots=True)
class _DiscoveredTrack:
    public: SubtitleTrack
    url: str


class BilibiliSubtitleAdapter:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self._pending: tuple[_DiscoveredTrack, ...] = ()

    def discover(self, *, bvid: str, cid: int) -> tuple[SubtitleTrack, ...]:
        response = self._get(_PLAYER_API, params={"bvid": bvid, "cid": cid})
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
        subtitle = cast(Mapping[object, object], data).get("subtitle")
        if subtitle is None:
            self._pending = ()
            raise NoSubtitles("该分集没有可见字幕。")
        if not isinstance(subtitle, Mapping):
            raise SubtitlePlatformResponseError("字幕轨道响应结构异常。")
        raw_tracks = cast(Mapping[object, object], subtitle).get("subtitles")
        if not isinstance(raw_tracks, list):
            raise SubtitlePlatformResponseError("字幕轨道列表结构异常。")
        if not raw_tracks:
            self._pending = ()
            raise NoSubtitles("该分集没有可见字幕。")
        parsed = tuple(_parse_track(item) for item in cast(list[object], raw_tracks))
        self._pending = parsed
        return tuple(item.public for item in parsed)

    def download_selected(self, selected: SubtitleTrack) -> SubtitleBody:
        matches = [item for item in self._pending if item.public == selected]
        self._pending = ()
        if len(matches) != 1:
            raise SubtitlePlatformResponseError("选定轨道不属于本次发现结果。")
        response = self._get(_safe_subtitle_url(matches[0].url))
        raw = response.content
        try:
            decoded = raw.decode("utf-8")
            payload = json.loads(
                decoded, parse_constant=lambda _value: (_ for _ in ()).throw(ValueError())
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise SubtitlePlatformResponseError("字幕正文不是有效 JSON。") from exc
        if not isinstance(payload, Mapping):
            raise SubtitlePlatformResponseError("字幕正文结构异常。")
        body = cast(Mapping[object, object], payload).get("body")
        if not isinstance(body, list):
            raise SubtitlePlatformResponseError("字幕正文缺少片段列表。")
        cues = tuple(_parse_cue(item) for item in cast(list[object], body))
        return SubtitleBody(raw, cues)

    def _get(self, url: str, **kwargs: object) -> httpx.Response:
        try:
            response = self._client.get(url, **kwargs)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise SubtitleNetworkError("字幕网络访问失败。") from exc
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
    except ValueError as exc:
        raise SubtitlePlatformResponseError("字幕轨道响应不是有效 JSON。") from exc
    if not isinstance(payload, Mapping):
        raise SubtitlePlatformResponseError("字幕轨道响应结构异常。")
    return cast(Mapping[str, object], payload)


def _parse_track(raw: object) -> _DiscoveredTrack:
    if not isinstance(raw, Mapping):
        raise SubtitlePlatformResponseError("字幕轨道结构异常。")
    item = cast(Mapping[str, object], raw)
    track_id, language, name, is_ai, url = (
        item.get("id"),
        item.get("lan"),
        item.get("lan_doc"),
        item.get("is_ai"),
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
        or not isinstance(is_ai, (bool, int))
        or isinstance(is_ai, float)
        or is_ai not in {False, True}
        or not isinstance(url, str)
        or not url
    ):
        raise SubtitlePlatformResponseError("字幕轨道字段缺失或类型错误。")
    kind = SubtitleTrackKind.AI if bool(is_ai) else SubtitleTrackKind.HUMAN
    return _DiscoveredTrack(SubtitleTrack(track_id, language, name, kind), url)


def _safe_subtitle_url(value: str) -> str:
    candidate = f"https:{value}" if value.startswith("//") else value
    parts = urlsplit(candidate)
    host = (parts.hostname or "").lower()
    if (
        parts.scheme != "https"
        or parts.username is not None
        or parts.password is not None
        or parts.port not in {None, 443}
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
        or not isinstance(start, (int, float))
        or not isinstance(end, (int, float))
        or not isinstance(text, str)
    ):
        raise SubtitlePlatformResponseError("字幕片段字段缺失或类型错误。")
    if not math.isfinite(float(start)) or not math.isfinite(float(end)):
        raise SubtitlePlatformResponseError("字幕片段时间无效。")
    try:
        return SubtitleCue(Decimal(str(start)), Decimal(str(end)), text)
    except (InvalidOperation, ValueError) as exc:
        raise SubtitlePlatformResponseError("字幕片段时间无效。") from exc
