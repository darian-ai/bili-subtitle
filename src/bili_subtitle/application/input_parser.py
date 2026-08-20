"""受支持视频输入的纯解析逻辑。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

from bili_subtitle.domain.errors import InputError

_BV_PATTERN = re.compile(r"(?i:BV)([A-Za-z0-9]{10})\Z")
_AV_PATTERN = re.compile(r"(?i:av)([1-9][0-9]*)\Z")
_VIDEO_HOSTS = frozenset({"bilibili.com", "www.bilibili.com", "m.bilibili.com"})
_SHORT_HOSTS = frozenset({"b23.tv", "www.b23.tv"})


@dataclass(frozen=True, slots=True)
class VideoReference:
    """规范化的视频标识和 URL 中的可选分集。"""

    bvid: str | None = None
    aid: int | None = None
    url_page: int | None = None

    def __post_init__(self) -> None:
        if (self.bvid is None) == (self.aid is None):
            raise ValueError("视频引用必须且只能包含一种标识。")


@dataclass(frozen=True, slots=True)
class ShortVideoUrl:
    """等待基础设施层安全解析的 b23.tv URL。"""

    url: str


ParsedVideoInput = VideoReference | ShortVideoUrl


def parse_video_input(value: str) -> ParsedVideoInput:
    """把一个完整用户输入解析为直接引用或受支持短链。"""
    candidate = value.strip()
    if not candidate:
        raise InputError("视频输入不能为空。")

    direct = _parse_identifier(candidate)
    if direct is not None:
        return direct

    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise InputError("视频 URL 格式无效。") from exc

    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() not in {"http", "https"} or not host:
        raise InputError("请输入受支持的 BV、av 或 Bilibili 视频 URL。")
    if parsed.username is not None or parsed.password is not None or port is not None:
        raise InputError("视频 URL 不允许包含用户信息或显式端口。")

    if host in _SHORT_HOSTS:
        if not parsed.path or parsed.path == "/":
            raise InputError("b23.tv 短链缺少路径。")
        return ShortVideoUrl(candidate)
    if host not in _VIDEO_HOSTS:
        raise InputError("视频 URL 必须使用受支持的 Bilibili 官方域名。")

    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) != 2 or segments[0].lower() != "video":
        raise InputError("URL 不是受支持的 Bilibili 视频页。")
    reference = _parse_identifier(segments[1])
    if reference is None:
        raise InputError("视频 URL 中的 BV 或 av 标识无效。")
    return VideoReference(reference.bvid, reference.aid, _parse_url_page(parsed.query))


def is_allowed_redirect_host(url: str) -> bool:
    """判断短链的下一跳是否仍在允许的官方域名集合中。"""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme.lower() in {"http", "https"}
        and parsed.username is None
        and parsed.password is None
        and port is None
        and host in _SHORT_HOSTS | _VIDEO_HOSTS
    )


def _parse_identifier(value: str) -> VideoReference | None:
    bv_match = _BV_PATTERN.fullmatch(value)
    if bv_match is not None:
        return VideoReference(bvid=f"BV{bv_match.group(1)}")
    av_match = _AV_PATTERN.fullmatch(value)
    if av_match is not None:
        return VideoReference(aid=int(av_match.group(1)))
    return None


def _parse_url_page(query: str) -> int | None:
    page_values = [value for key, value in parse_qsl(query, keep_blank_values=True) if key == "p"]
    if not page_values:
        return None
    if len(page_values) != 1 or not page_values[0].isdigit() or int(page_values[0]) <= 0:
        raise InputError("URL 的 p 参数必须是唯一的正整数。")
    return int(page_values[0])
