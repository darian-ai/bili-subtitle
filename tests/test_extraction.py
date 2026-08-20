from pathlib import Path

import httpx
import pytest

from bili_subtitle.application.extraction import extract_single_track
from bili_subtitle.domain.errors import SubtitlePlatformResponseError
from bili_subtitle.domain.models import (
    SubtitleBody,
    SubtitleTrack,
    SubtitleTrackKind,
    VideoMetadata,
    VideoPage,
)
from bili_subtitle.infrastructure.export import export_single_track
from bili_subtitle.infrastructure.subtitles import BilibiliSubtitleAdapter


class FakeSubtitles:
    track = SubtitleTrack(4, "zh-CN", "AI", SubtitleTrackKind.AI)

    def discover(self, *, bvid: str, cid: int):
        assert (bvid, cid) == ("BV1xx411c7mD", 8)
        return (self.track,)

    def download_selected(self, *, bvid: str, cid: int, selected: SubtitleTrack) -> SubtitleBody:
        assert (bvid, cid) == ("BV1xx411c7mD", 8)
        assert selected == self.track
        return SubtitleBody(b'{"body":[]}', ())


def test_offline_single_page_single_track_loop(tmp_path: Path) -> None:
    page = VideoPage(1, 8, "p")
    result = extract_single_track(
        video=VideoMetadata(7, "BV1xx411c7mD", "v", (page,)),
        page=page,
        track_id=4,
        basename="one",
        output_dir=tmp_path,
        subtitles=FakeSubtitles(),
        exporter=export_single_track,
    )
    assert result.track.track_id == 4
    assert [path.name for path in result.files] == ["one.json", "one.srt", "manifest.json"]


def test_explicit_unknown_track_is_rejected(tmp_path: Path) -> None:
    page = VideoPage(1, 8, "p")
    with pytest.raises(SubtitlePlatformResponseError):
        extract_single_track(
            video=VideoMetadata(7, "BV1xx411c7mD", "v", (page,)),
            page=page,
            track_id=99,
            basename="one",
            output_dir=tmp_path,
            subtitles=FakeSubtitles(),
            exporter=export_single_track,
        )


def test_ai_track_full_http_to_files_integration(tmp_path: Path) -> None:
    raw = b'{ "extra": true, "body": [{"from":0.0005,"to":1,"content":" AI\\ntext "}] }'

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
                                    "id": 4,
                                    "lan": "zh-CN",
                                    "lan_doc": "AI字幕",
                                    "is_ai": 1,
                                    "subtitle_url": (
                                        "//aisubtitle.hdslb.com/fake.json?token=INTEGRATION"
                                    ),
                                }
                            ]
                        }
                    },
                },
            )
        return httpx.Response(200, content=raw)

    page = VideoPage(1, 8, "p")
    result = extract_single_track(
        video=VideoMetadata(7, "BV1xx411c7mD", "v", (page,)),
        page=page,
        track_id=4,
        basename="one",
        output_dir=tmp_path,
        subtitles=BilibiliSubtitleAdapter(httpx.Client(transport=httpx.MockTransport(handler))),
        exporter=export_single_track,
    )
    assert result.track.kind is SubtitleTrackKind.AI
    assert result.files[0].read_bytes() == raw
    assert result.files[1].read_text("utf-8") == ("1\n00:00:00,001 --> 00:00:01,000\n AI\ntext \n")
    assert "INTEGRATION" not in result.files[2].read_text("utf-8")
