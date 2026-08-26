"""播放器字幕发现与正文即时下载。签名 URL 永不离开本模块。"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from hashlib import md5
from typing import cast
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

import httpx

from bili_subtitle.domain.errors import (
    AuthenticationRequired,
    NoSubtitles,
    SubtitleAccessDenied,
    SubtitleNetworkError,
    SubtitlePlatformResponseError,
)
from bili_subtitle.domain.models import SubtitleBody, SubtitleCue, SubtitleTrack, SubtitleTrackKind

_NAV_API = "https://api.bilibili.com/x/web-interface/nav"
_PLAYER_API = "https://api.bilibili.com/x/player/wbi/v2"
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
_WBI_KEY_TTL_SECONDS = 6 * 60 * 60
_WBI_MIXIN_ORDER = (
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
)
_WBI_SIGNATURE_FAILURES = frozenset({-352, -403, -412})
_TRUSTED_SUFFIXES = (".bilibili.com", ".bilivideo.com", ".hdslb.com")


@dataclass(frozen=True, slots=True)
class _DiscoveredTrack:
    public: SubtitleTrack
    url: str | None = field(repr=False)


class BilibiliSubtitleAdapter:
    def __init__(self, client: httpx.Client, *, clock: Callable[[], float] = time.time) -> None:
        self._client = client
        self._clock = clock
        self._wbi_key: str | None = None
        self._wbi_key_loaded_at = 0.0
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
        unsigned: dict[str, str | int] = {"cid": cid}
        unsigned["aid" if aid is not None else "bvid"] = aid if aid is not None else bvid
        payload: Mapping[str, object] | None = None
        for attempt in range(2):
            params = self._signed_wbi_params(unsigned, refresh=attempt == 1)
            response = self._get(
                _PLAYER_API,
                params=params,
                no_cache=True,
                request_headers={
                    "Referer": f"https://www.bilibili.com/video/{bvid}",
                    "User-Agent": _BROWSER_USER_AGENT,
                },
            )
            payload = _response_payload(response)
            if payload.get("code") not in _WBI_SIGNATURE_FAILURES or attempt == 1:
                break
        assert payload is not None
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

    def _signed_wbi_params(
        self, params: Mapping[str, str | int], *, refresh: bool
    ) -> dict[str, str | int]:
        mixin_key = self._load_wbi_key(refresh=refresh)
        signed: dict[str, str | int] = dict(params)
        signed["wts"] = int(self._clock())
        filtered = {
            key: str(value).translate({ord(char): None for char in "!'()*"})
            for key, value in signed.items()
        }
        query = urlencode(sorted(filtered.items()), quote_via=quote)
        signed["w_rid"] = md5(f"{query}{mixin_key}".encode()).hexdigest()  # noqa: S324
        return signed

    def _load_wbi_key(self, *, refresh: bool) -> str:
        now = self._clock()
        if (
            not refresh
            and self._wbi_key is not None
            and now - self._wbi_key_loaded_at < _WBI_KEY_TTL_SECONDS
        ):
            return self._wbi_key
        response = self._get(
            _NAV_API,
            no_cache=refresh,
            request_headers={
                "Referer": "https://www.bilibili.com/",
                "User-Agent": _BROWSER_USER_AGENT,
            },
        )
        payload = _response_payload(response)
        if payload.get("code") != 0:
            raise SubtitlePlatformResponseError("平台拒绝了 WBI 签名密钥请求。")
        data = payload.get("data")
        typed_data: Mapping[str, object] = (
            cast(Mapping[str, object], data) if isinstance(data, Mapping) else {}
        )
        wbi_img = typed_data.get("wbi_img")
        if not isinstance(wbi_img, Mapping):
            raise SubtitlePlatformResponseError("WBI 签名密钥响应结构异常。")
        typed_wbi_img = cast(Mapping[str, object], wbi_img)
        raw_key = "".join(
            _url_filename(typed_wbi_img.get(field)) for field in ("img_url", "sub_url")
        )
        if len(raw_key) < 64:
            raise SubtitlePlatformResponseError("WBI 签名密钥响应结构异常。")
        try:
            mixin_key = "".join(raw_key[index] for index in _WBI_MIXIN_ORDER)[:32]
        except IndexError:
            raise SubtitlePlatformResponseError("WBI 签名密钥响应结构异常。") from None
        self._wbi_key = mixin_key
        self._wbi_key_loaded_at = now
        return mixin_key

    def _get(
        self,
        url: str,
        *,
        params: dict[str, str | int] | None = None,
        no_cache: bool = False,
        request_headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        try:
            headers = dict(request_headers or {})
            if no_cache:
                headers.update({"Cache-Control": "no-cache", "Pragma": "no-cache"})
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


def _url_filename(value: object) -> str:
    if not isinstance(value, str):
        return ""
    filename = urlsplit(value).path.rsplit("/", 1)[-1]
    return filename.split(".", 1)[0]


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
