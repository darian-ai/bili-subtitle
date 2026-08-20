from __future__ import annotations

import httpx
import pytest
import respx

from bili_subtitle.application.input_parser import VideoReference
from bili_subtitle.domain.errors import (
    AccessDeniedError,
    NetworkError,
    PlatformResponseError,
    RedirectError,
    VideoNotFoundError,
)
from bili_subtitle.infrastructure.bilibili import BilibiliMetadataAdapter, create_http_client

VIEW_API = "https://api.bilibili.com/x/web-interface/view"


def video_payload() -> dict[str, object]:
    return {
        "code": 0,
        "data": {
            "aid": 123,
            "bvid": "BV1xx411c7mD",
            "title": "测试投稿",
            "pages": [
                {"page": 1, "cid": 101, "part": "第一集"},
                {"page": 2, "cid": 102, "part": "第二集"},
            ],
        },
    }


@respx.mock
def test_fetch_video_by_bvid_and_parse_pages() -> None:
    route = respx.get(VIEW_API, params={"bvid": "BV1xx411c7mD"}).mock(
        return_value=httpx.Response(200, json=video_payload())
    )
    with httpx.Client() as client:
        video = BilibiliMetadataAdapter(client).fetch_video(VideoReference(bvid="BV1xx411c7mD"))
    assert route.called
    assert video.aid == 123
    assert [page.cid for page in video.pages] == [101, 102]


@respx.mock
def test_fetch_video_by_aid() -> None:
    respx.get(VIEW_API, params={"aid": 123}).mock(
        return_value=httpx.Response(200, json=video_payload())
    )
    with httpx.Client() as client:
        video = BilibiliMetadataAdapter(client).fetch_video(VideoReference(aid=123))
    assert video.bvid == "BV1xx411c7mD"


@pytest.mark.parametrize(
    ("code", "error"),
    [
        (-404, VideoNotFoundError),
        (62002, VideoNotFoundError),
        (-403, AccessDeniedError),
        (-500, PlatformResponseError),
    ],
)
@respx.mock
def test_maps_platform_codes(code: int, error: type[Exception]) -> None:
    respx.get(VIEW_API).mock(return_value=httpx.Response(200, json={"code": code}))
    with httpx.Client() as client, pytest.raises(error):
        BilibiliMetadataAdapter(client).fetch_video(VideoReference(aid=123))


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"code": 0}),
        httpx.Response(200, json={"code": 0, "data": {"aid": "bad"}}),
        httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"aid": 1, "bvid": "BV1xx411c7mD", "title": "x", "pages": [None]},
            },
        ),
        httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "aid": 1,
                    "bvid": "BV1xx411c7mD",
                    "title": "x",
                    "pages": [{"page": True, "cid": 2, "part": "x"}],
                },
            },
        ),
    ],
)
@respx.mock
def test_rejects_malformed_payload(response: httpx.Response) -> None:
    respx.get(VIEW_API).mock(return_value=response)
    with httpx.Client() as client, pytest.raises(PlatformResponseError):
        BilibiliMetadataAdapter(client).fetch_video(VideoReference(aid=1))


@respx.mock
def test_http_failure_is_network_error() -> None:
    respx.get(VIEW_API).mock(return_value=httpx.Response(503))
    with httpx.Client() as client, pytest.raises(NetworkError):
        BilibiliMetadataAdapter(client).fetch_video(VideoReference(aid=1))


@pytest.mark.parametrize(
    ("status", "error"),
    [(404, VideoNotFoundError), (403, AccessDeniedError), (400, PlatformResponseError)],
)
@respx.mock
def test_maps_http_status(status: int, error: type[Exception]) -> None:
    respx.get(VIEW_API).mock(return_value=httpx.Response(status))
    with httpx.Client() as client, pytest.raises(error):
        BilibiliMetadataAdapter(client).fetch_video(VideoReference(aid=1))


def test_default_client_has_safe_defaults() -> None:
    with create_http_client() as client:
        assert client.headers["user-agent"] == "bili-subtitle/0.1"
        assert client.follow_redirects is False


@respx.mock
def test_resolve_short_url() -> None:
    respx.get("https://b23.tv/abc").mock(
        return_value=httpx.Response(302, headers={"location": "https://b23.tv/next"})
    )
    respx.get("https://b23.tv/next").mock(
        return_value=httpx.Response(
            302, headers={"location": "https://www.bilibili.com/video/BV1xx411c7mD?p=2"}
        )
    )
    with httpx.Client() as client:
        result = BilibiliMetadataAdapter(client).resolve_short_url("https://b23.tv/abc")
    assert result.endswith("?p=2")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200),
        httpx.Response(302),
        httpx.Response(302, headers={"location": "https://attacker.example/video"}),
    ],
)
@respx.mock
def test_rejects_invalid_short_redirect(response: httpx.Response) -> None:
    respx.get("https://b23.tv/abc").mock(return_value=response)
    with httpx.Client() as client, pytest.raises(RedirectError):
        BilibiliMetadataAdapter(client).resolve_short_url("https://b23.tv/abc")


@respx.mock
def test_short_redirect_network_error() -> None:
    respx.get("https://b23.tv/abc").mock(side_effect=httpx.ConnectError("offline"))
    with httpx.Client() as client, pytest.raises(NetworkError):
        BilibiliMetadataAdapter(client).resolve_short_url("https://b23.tv/abc")


@respx.mock
def test_short_redirect_loop_and_limit() -> None:
    respx.get("https://b23.tv/abc").mock(
        return_value=httpx.Response(302, headers={"location": "https://b23.tv/abc"})
    )
    with httpx.Client() as client, pytest.raises(RedirectError, match="循环"):
        BilibiliMetadataAdapter(client).resolve_short_url("https://b23.tv/abc")

    with httpx.Client() as client, pytest.raises(RedirectError, match="超过限制"):
        BilibiliMetadataAdapter(client, max_redirects=0).resolve_short_url("https://b23.tv/abc")
