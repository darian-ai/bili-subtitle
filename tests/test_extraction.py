from pathlib import Path

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
