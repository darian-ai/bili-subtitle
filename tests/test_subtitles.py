import httpx
import pytest

from bili_subtitle.domain.errors import NoSubtitles, SubtitlePlatformResponseError
from bili_subtitle.domain.models import SubtitleTrackKind
from bili_subtitle.infrastructure.subtitles import BilibiliSubtitleAdapter

SIGNED = "https://aisubtitle.hdslb.com/bfs/subtitle/fake.json?token=FAKE_SIGNATURE_CANARY"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_discovers_in_order_and_immediately_downloads_raw_bytes() -> None:
    raw = b'{ "extra": 1, "body": [{"from":1.0005,"to":2,"content":"  \u4e2d\u6587\\nline "}] }'
    calls = []

    def handler(request):
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
    body = adapter.download_selected(tracks[1])
    assert body.raw_json == raw
    assert body.cues[0].text == "  中文\nline "
    assert len(calls) == 2
    assert SIGNED not in repr(tracks) + repr(body)


@pytest.mark.parametrize("subtitle", [None, {"subtitles": []}])
def test_legal_no_subtitles(subtitle) -> None:
    payload = (
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
        adapter.download_selected(track)
    assert url not in str(caught.value)
