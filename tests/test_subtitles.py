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
WBI_IMG = "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png"
WBI_SUB = "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    def routed(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/x/web-interface/nav":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"wbi_img": {"img_url": WBI_IMG, "sub_url": WBI_SUB}},
                },
            )
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(routed))


def test_discovers_in_order_and_immediately_downloads_raw_bytes() -> None:
    raw = b'{ "extra": 1, "body": [{"from":1.0005,"to":2,"content":"  \\u4e2d\\u6587\\nline "}] }'
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/x/player/wbi/v2":
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
    assert len(calls) == 2
    assert SIGNED not in repr(tracks) + repr(body)


def test_discovery_sends_complete_identity_without_cache_and_rejects_mismatch() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "aid": 7,
                    "bvid": "BV1xx411c7mD",
                    "cid": 999,
                    "subtitle": {"subtitles": []},
                },
            },
        )

    adapter = BilibiliSubtitleAdapter(_client(handler))
    with pytest.raises(SubtitlePlatformResponseError, match="来源"):
        adapter.discover(bvid="BV1xx411c7mD", cid=8, aid=7)
    request = requests[0]
    params = dict(request.url.params)
    assert {key: params[key] for key in ("aid", "cid")} == {"aid": "7", "cid": "8"}
    assert len(params["w_rid"]) == 32 and int(params["wts"]) > 0
    assert request.headers["cache-control"] == "no-cache"
    assert request.headers["referer"] == "https://www.bilibili.com/video/BV1xx411c7mD"


def test_wbi_signature_is_deterministic_and_key_is_cached() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "aid": 7,
                    "bvid": "BV1xx411c7mD",
                    "cid": 8,
                    "subtitle": {
                        "subtitles": [
                            {
                                "id": 1,
                                "lan": "zh-CN",
                                "lan_doc": "中文",
                                "type": 0,
                                "subtitle_url": SIGNED,
                            }
                        ]
                    },
                },
            },
        )

    adapter = BilibiliSubtitleAdapter(_client(handler), clock=lambda: 1_720_000_000)
    adapter.discover(bvid="BV1xx411c7mD", cid=8, aid=7)
    adapter.discover(bvid="BV1xx411c7mD", cid=8, aid=7)

    assert len(requests) == 2
    assert all(request.url.path == "/x/player/wbi/v2" for request in requests)
    assert dict(requests[0].url.params) == {
        "cid": "8",
        "aid": "7",
        "wts": "1720000000",
        "w_rid": "5710fb53e41d94277d8d202daa256a3a",
    }


def test_wbi_signature_failure_refreshes_key_and_retries_once() -> None:
    nav_calls = 0
    player_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal nav_calls, player_calls
        if request.url.path == "/x/web-interface/nav":
            nav_calls += 1
            suffix = "4932caff0ff746eab6f01bf08b70ac45" if nav_calls == 1 else "a" * 32
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "wbi_img": {
                            "img_url": WBI_IMG,
                            "sub_url": f"https://i0.hdslb.com/{suffix}.png",
                        }
                    },
                },
            )
        player_calls += 1
        if player_calls == 1:
            return httpx.Response(200, json={"code": -352})
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "aid": 7,
                    "bvid": "BV1xx411c7mD",
                    "cid": 8,
                    "subtitle": {"subtitles": []},
                },
            },
        )

    adapter = BilibiliSubtitleAdapter(
        httpx.Client(transport=httpx.MockTransport(handler)), clock=lambda: 1_720_000_000
    )
    with pytest.raises(NoSubtitles):
        adapter.discover(bvid="BV1xx411c7mD", cid=8, aid=7)
    assert (nav_calls, player_calls) == (2, 2)


def test_discovers_current_player_track_schema_without_legacy_is_ai() -> None:
    """播放器当前用 ``type`` 表示 AI 类型，不再保证返回 ``is_ai``。"""
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
                                    "id": 9,
                                    "id_str": "9",
                                    "lan": "zh-CN",
                                    "lan_doc": "中文（自动生成）",
                                    "type": 1,
                                    "ai_type": 0,
                                    "ai_status": 2,
                                    "is_lock": False,
                                    "subtitle_url": SIGNED,
                                }
                            ]
                        }
                    },
                },
            )
        )
    )

    tracks = adapter.discover(bvid="BV1xx411c7mD", cid=1)

    assert len(tracks) == 1
    assert tracks[0].kind is SubtitleTrackKind.AI


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
        if request.url.path == "/x/player/wbi/v2":
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
        if request.url.path == "/x/player/wbi/v2":
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


def test_empty_body_address_is_unavailable_without_hiding_valid_tracks() -> None:
    payload = {
        "code": 0,
        "data": {
            "subtitle": {
                "subtitles": [
                    {"id": 1, "lan": "x", "lan_doc": "x", "type": 0, "subtitle_url": ""},
                    {
                        "id": 2,
                        "lan": "y",
                        "lan_doc": "y",
                        "type": 1,
                        "subtitle_url": SIGNED,
                    },
                ]
            }
        },
    }
    adapter = BilibiliSubtitleAdapter(_client(lambda request: httpx.Response(200, json=payload)))
    tracks = adapter.discover(bvid="BV1xx411c7mD", cid=1)
    assert [track.track_id for track in tracks] == [1, 2]
    with pytest.raises(SubtitleAccessDenied, match="不可访问"):
        adapter.download_selected(bvid="BV1xx411c7mD", cid=1, selected=tracks[0])


def test_only_empty_body_addresses_are_access_denied_not_no_subtitles() -> None:
    payload = {
        "code": 0,
        "data": {
            "subtitle": {
                "subtitles": [{"id": 1, "lan": "x", "lan_doc": "x", "type": 0, "subtitle_url": ""}]
            }
        },
    }
    adapter = BilibiliSubtitleAdapter(_client(lambda request: httpx.Response(200, json=payload)))
    track = adapter.discover(bvid="BV1xx411c7mD", cid=1)[0]
    with pytest.raises(SubtitleAccessDenied, match="不可访问"):
        adapter.download_selected(bvid="BV1xx411c7mD", cid=1, selected=track)


def test_discard_pending_removes_unselected_signed_addresses() -> None:
    payload = {
        "code": 0,
        "data": {
            "subtitle": {
                "subtitles": [
                    {"id": 1, "lan": "x", "lan_doc": "x", "type": 0, "subtitle_url": SIGNED}
                ]
            }
        },
    }
    adapter = BilibiliSubtitleAdapter(_client(lambda request: httpx.Response(200, json=payload)))
    track = adapter.discover(bvid="BV1xx411c7mD", cid=1)[0]
    adapter.discard_pending(bvid="BV1xx411c7mD", cid=1)
    with pytest.raises(SubtitlePlatformResponseError, match="不属于"):
        adapter.download_selected(bvid="BV1xx411c7mD", cid=1, selected=track)
