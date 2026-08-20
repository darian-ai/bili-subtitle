import json
from decimal import Decimal

import pytest

from bili_subtitle.domain.errors import ExportError
from bili_subtitle.domain.models import (
    SubtitleCue,
    SubtitleTrack,
    SubtitleTrackKind,
    VideoMetadata,
    VideoPage,
)
from bili_subtitle.infrastructure.export import export_single_track, render_srt
from bili_subtitle.infrastructure.subtitles import SubtitleBody


def test_srt_round_half_up_and_preserves_order_and_text() -> None:
    cues = (
        SubtitleCue(Decimal("3600.0005"), Decimal("3601.2345"), " lead\n尾 "),
        SubtitleCue(Decimal("0"), Decimal("0.0005"), ""),
    )
    assert render_srt(cues) == (
        "1\n01:00:00,001 --> 01:00:01,235\n lead\n尾 \n\n2\n00:00:00,000 --> 00:00:00,001\n\n"
    )


def test_export_preserves_raw_json_and_publishes_manifest_last(tmp_path) -> None:
    page = VideoPage(1, 88, "P标题")
    video = VideoMetadata(7, "BV1xx411c7mD", "视频", (page,))
    track = SubtitleTrack(9, "zh-CN", "中文AI", SubtitleTrackKind.AI)
    raw = b'{  "body": [], "extra": "unchanged" }'
    paths = export_single_track(
        output_dir=tmp_path,
        basename="P01.zh-CN.9",
        video=video,
        page=page,
        track=track,
        body=SubtitleBody(raw, ()),
    )
    assert paths[0].read_bytes() == raw
    manifest = json.loads(paths[2].read_text("utf-8"))
    assert manifest["files"] == {"json": paths[0].name, "srt": paths[1].name}
    assert str(tmp_path) not in paths[2].read_text("utf-8")
    assert not list(tmp_path.glob("*.tmp"))


def test_existing_target_is_not_overwritten_and_temp_is_cleaned(tmp_path) -> None:
    target = tmp_path / "x.json"
    target.write_bytes(b"old")
    page = VideoPage(1, 88, "p")
    with pytest.raises(ExportError):
        export_single_track(
            output_dir=tmp_path,
            basename="x",
            video=VideoMetadata(7, "BV1xx411c7mD", "v", (page,)),
            page=page,
            track=SubtitleTrack(1, "x", "x", SubtitleTrackKind.HUMAN),
            body=SubtitleBody(b"new", ()),
        )
    assert target.read_bytes() == b"old"
    assert not list(tmp_path.glob("*.tmp"))
