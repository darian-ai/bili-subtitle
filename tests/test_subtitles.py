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
from bili_subtitle.domain.models import SubtitleTrackKind
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
    "payload",
    [
        [],
        {"code": 0},
        {"code": 0, "data": {"subtitle": []}},
        {"code": 0, "data": {"subtitle": {"subtitles": "bad"}}},
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
        b"[]",
        b"{}",
        b'{"body":[{"from":true,"to":2,"content":"x"}]}',
        b'{"body":[{"from":-1,"to":2,"content":"x"}]}',
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
    assert body.decode(errors="ignore") not in str(caught.value)
    assert body.decode(errors="ignore") not in repr(caught.value.__context__)
