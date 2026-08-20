import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

import bili_subtitle.infrastructure.export as export_module
from bili_subtitle.domain.errors import ExportError
from bili_subtitle.domain.models import (
    SubtitleBody,
    SubtitleCue,
    SubtitleTrack,
    SubtitleTrackKind,
    VideoMetadata,
    VideoPage,
)
from bili_subtitle.infrastructure.export import export_single_track, render_srt


def test_srt_round_half_up_and_preserves_order_and_text() -> None:
    cues = (
        SubtitleCue(Decimal("3600.0005"), Decimal("3601.2345"), " lead\n尾 "),
        SubtitleCue(Decimal("0"), Decimal("0.0005"), ""),
    )
    assert render_srt(cues) == (
        "1\n01:00:00,001 --> 01:00:01,235\n lead\n尾 \n\n2\n00:00:00,000 --> 00:00:00,001\n\n"
    )


def test_export_preserves_raw_json_and_publishes_manifest_last(tmp_path: Path) -> None:
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


def test_existing_target_is_not_overwritten_and_temp_is_cleaned(tmp_path: Path) -> None:
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


@pytest.mark.parametrize("existing_name", ["x.srt", "manifest.json"])
def test_any_existing_target_rejects_before_publication(tmp_path: Path, existing_name: str) -> None:
    existing = tmp_path / existing_name
    existing.write_bytes(b"old")
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
    assert existing.read_bytes() == b"old"
    assert sorted(path.name for path in tmp_path.iterdir()) == [existing_name]


def test_text_encoding_failure_is_export_error_before_any_publication(tmp_path: Path) -> None:
    page = VideoPage(1, 88, "p")
    body = SubtitleBody(b'{"body":[]}', (SubtitleCue(Decimal("0"), Decimal("1"), "\ud800"),))
    with pytest.raises(ExportError):
        export_single_track(
            output_dir=tmp_path,
            basename="x",
            video=VideoMetadata(7, "BV1xx411c7mD", "v", (page,)),
            page=page,
            track=SubtitleTrack(1, "x", "x", SubtitleTrackKind.HUMAN),
            body=body,
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("failure_point", ["create", "flush"])
def test_temporary_publication_failures_are_cleaned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_point: str
) -> None:
    if failure_point == "create":

        def fail_create(*args: object, **kwargs: object) -> tuple[int, str]:
            del args, kwargs
            raise OSError("injected create failure")

        monkeypatch.setattr(export_module.tempfile, "mkstemp", fail_create)
    else:

        def fail_flush(descriptor: int) -> None:
            del descriptor
            raise OSError("injected flush failure")

        monkeypatch.setattr(export_module.os, "fsync", fail_flush)

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
    assert not list(tmp_path.iterdir())


def test_manifest_failure_keeps_published_subtitles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_link = os.link
    calls = 0

    def fail_manifest(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("injected")
        real_link(source, target)

    monkeypatch.setattr(os, "link", fail_manifest)
    page = VideoPage(1, 88, "p")
    with pytest.raises(ExportError):
        export_single_track(
            output_dir=tmp_path,
            basename="x",
            video=VideoMetadata(7, "BV1xx411c7mD", "v", (page,)),
            page=page,
            track=SubtitleTrack(1, "x", "x", SubtitleTrackKind.HUMAN),
            body=SubtitleBody(b"{}", ()),
        )
    assert (tmp_path / "x.json").exists()
    assert (tmp_path / "x.srt").exists()
    assert not (tmp_path / "manifest.json").exists()
    assert not list(tmp_path.glob("*.tmp"))
