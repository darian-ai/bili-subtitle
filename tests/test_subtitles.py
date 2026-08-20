from collections.abc import Callable

import httpx
import pytest

from bili_subtitle.domain.errors import (
    AuthenticationRequired,
    NoSubtitles,
    SubtitleAccessDenied,
    SubtitleNetworkError,
    SubtitlePlatformResponseError,
)
from bili_subtitle.domain.models import SubtitleTrack, SubtitleTrackKind
from bili_subtitle.infrastructure.subtitles import BilibiliSubtitleAdapter

SIGNED = "https://aisubtitle.hdslb.com/bfs/subtitle/fake.json?token=FAKE_SIGNATURE_CANARY"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_discovers_in_order_and_immediately_downloads_raw_bytes() -> None:
    raw = b'{ "extra": 1, "body": [{"from":1.0005,"to":2,"content":"  \\u4e2d\\u6587\\nline "}] }'
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/x/player/v2":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "subtitle": {
                            "subtitles": [
                                {
                                    "id": 8,
                                    "lan": "zh-CN",
                                    "lan_doc": "中文",
                                    "is_ai": 0,
                                    "subtitle_url": SIGNED,
                                },
                                {
                                    "id": 9,
                                    "lan": "zh-CN",
                                    "lan_doc": "中文AI",
                                    "is_ai": 1,
                                    "subtitle_url": SIGNED,
                                },
                            ]
                        }
                    },
                },
            )
        return httpx.Response(200, content=raw)

    adapter = BilibiliSubtitleAdapter(_client(handler))
    tracks = adapter.discover(bvid="BV1xx411c7mD", cid=1)
    assert [x.track_id for x in tracks] == [8, 9]
    assert tracks[1].kind is SubtitleTrackKind.AI
    assert SIGNED not in repr(adapter.__dict__)
    body = adapter.download_selected(bvid="BV1xx411c7mD", cid=1, selected=tracks[1])
    assert body.raw_json == raw
    assert body.cues[0].text == "  中文\nline "
    assert len(calls) == 3
    assert SIGNED not in repr(tracks) + repr(body)


@pytest.mark.parametrize("subtitle", [None, {"subtitles": []}])
def test_legal_no_subtitles(subtitle: object) -> None:
    payload: object = (
        {"code": 0, "data": {}} if subtitle is None else {"code": 0, "data": {"subtitle": subtitle}}
    )
    adapter = BilibiliSubtitleAdapter(_client(lambda request: httpx.Response(200, json=payload)))
    with pytest.raises(NoSubtitles):
        adapter.discover(bvid="BV1xx411c7mD", cid=1)


@pytest.mark.parametrize(
    "url",
    [
        "http://aisubtitle.hdslb.com/x",
        "https://evil.test/x",
        "https://u:p@aisubtitle.hdslb.com/x",
        "https://aisubtitle.hdslb.com:444/x",
        "https://aisubtitle.hdslb.com:bad/x",
    ],
)
def test_rejects_unsafe_url_without_leaking(url: str) -> None:
    adapter = BilibiliSubtitleAdapter(
        _client(
            lambda request: httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "subtitle": {
                            "subtitles": [
                                {
                                    "id": 1,
                                    "lan": "x",
                                    "lan_doc": "x",
                                    "is_ai": 0,
                                    "subtitle_url": url,
                                }
                            ]
                        }
                    },
                },
            )
        )
    )
    track = adapter.discover(bvid="BV1xx411c7mD", cid=1)[0]
    with pytest.raises(SubtitlePlatformResponseError) as caught:
        adapter.download_selected(bvid="BV1xx411c7mD", cid=1, selected=track)
    assert url not in str(caught.value)


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, AuthenticationRequired),
        (403, SubtitleAccessDenied),
        (500, SubtitleNetworkError),
        (418, SubtitlePlatformResponseError),
    ],
)
def test_http_failures_have_stable_classification(status: int, error: type[Exception]) -> None:
    adapter = BilibiliSubtitleAdapter(
        _client(lambda request: httpx.Response(status, request=request))
    )
    with pytest.raises(error):
        adapter.discover(bvid="BV1xx411c7mD", cid=1)


@pytest.mark.parametrize(
    ("code", "error"),
    [
        (-101, AuthenticationRequired),
        (-111, AuthenticationRequired),
        (-403, SubtitleAccessDenied),
        (-10403, SubtitleAccessDenied),
        (-1, SubtitlePlatformResponseError),
    ],
)
def test_platform_codes_have_stable_classification(code: int, error: type[Exception]) -> None:
    adapter = BilibiliSubtitleAdapter(
        _client(lambda request: httpx.Response(200, json={"code": code}))
    )
    with pytest.raises(error):
        adapter.discover(bvid="BV1xx411c7mD", cid=1)


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout])
def test_transport_failures_are_network_errors(
    failure: type[httpx.RequestError],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise failure("FAKE_NETWORK_DETAIL_CANARY", request=request)

    adapter = BilibiliSubtitleAdapter(_client(handler))
    with pytest.raises(SubtitleNetworkError) as caught:
        adapter.discover(bvid="BV1xx411c7mD", cid=1)
    assert "FAKE_NETWORK_DETAIL_CANARY" not in str(caught.value)
    assert "FAKE_NETWORK_DETAIL_CANARY" not in repr(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"code": 0},
        {"code": 0, "data": {"subtitle": []}},
        {"code": 0, "data": {"subtitle": {"subtitles": "bad"}}},
        {
            "code": 0,
            "data": {
                "subtitle": {
                    "subtitles": [
                        {
                            "id": True,
                            "lan": "x",
                            "lan_doc": "x",
                            "is_ai": 2,
                            "subtitle_url": SIGNED,
                        }
                    ]
                }
            },
        },
    ],
)
def test_malformed_discovery_is_not_no_subtitles(payload: object) -> None:
    adapter = BilibiliSubtitleAdapter(_client(lambda request: httpx.Response(200, json=payload)))
    with pytest.raises(SubtitlePlatformResponseError):
        adapter.discover(bvid="BV1xx411c7mD", cid=1)


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"\xff",
        b"[]",
        b"{}",
        b'{"body":[{"from":true,"to":2,"content":"x"}]}',
        b'{"body":[{"from":-1,"to":2,"content":"x"}]}',
        b'{"body":[{"from":2,"to":1,"content":"x"}]}',
        b'{"body":[{"from":NaN,"to":2,"content":"x"}]}',
        b'{"body":[{"from":1,"to":2,"content":1}]}',
        b'{"body":["not-an-object"]}',
    ],
)
def test_malformed_body_is_classified_without_raw_content(body: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/x/player/v2":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "subtitle": {
                            "subtitles": [
                                {
                                    "id": 1,
                                    "lan": "x",
                                    "lan_doc": "x",
                                    "is_ai": 0,
                                    "subtitle_url": SIGNED,
                                }
                            ]
                        }
                    },
                },
            )
        return httpx.Response(200, content=body)

    adapter = BilibiliSubtitleAdapter(_client(handler))
    selected = adapter.discover(bvid="BV1xx411c7mD", cid=1)[0]
    with pytest.raises(SubtitlePlatformResponseError) as caught:
        adapter.download_selected(bvid="BV1xx411c7mD", cid=1, selected=selected)
    decoded = body.decode(errors="ignore")
    if decoded:
        assert decoded not in str(caught.value)
        assert decoded not in repr(caught.value)


def test_protocol_relative_url_is_https_and_consumed_without_retention() -> None:
    requested_subtitle_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/x/player/v2":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "subtitle": {
                            "subtitles": [
                                {
                                    "id": 1,
                                    "lan": "x",
                                    "lan_doc": "x",
                                    "is_ai": 0,
                                    "subtitle_url": (
                                        "//aisubtitle.hdslb.com/fake.json?token=RELATIVE"
                                    ),
                                }
                            ]
                        }
                    },
                },
            )
        requested_subtitle_urls.append(str(request.url))
        return httpx.Response(200, content=b'{"body":[]}')

    adapter = BilibiliSubtitleAdapter(_client(handler))
    track = adapter.discover(bvid="BV1xx411c7mD", cid=1)[0]
    adapter.download_selected(bvid="BV1xx411c7mD", cid=1, selected=track)
    assert requested_subtitle_urls == ["https://aisubtitle.hdslb.com/fake.json?token=RELATIVE"]
    assert "RELATIVE" not in repr(adapter.__dict__)


def test_download_rejects_track_not_present_in_fresh_discovery() -> None:
    payload = {
        "code": 0,
        "data": {
            "subtitle": {
                "subtitles": [
                    {
                        "id": 1,
                        "lan": "x",
                        "lan_doc": "x",
                        "is_ai": 0,
                        "subtitle_url": SIGNED,
                    }
                ]
            }
        },
    }
    adapter = BilibiliSubtitleAdapter(_client(lambda request: httpx.Response(200, json=payload)))
    selected = SubtitleTrack(2, "x", "x", SubtitleTrackKind.HUMAN)
    with pytest.raises(SubtitlePlatformResponseError):
        adapter.download_selected(bvid="BV1xx411c7mD", cid=1, selected=selected)
