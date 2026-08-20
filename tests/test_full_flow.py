from pathlib import Path

import pytest

from bili_subtitle.application.full_flow import run_extraction
from bili_subtitle.domain.models import (
    PageSelection,
    SelectionSource,
    SubtitleBody,
    SubtitleTrack,
    SubtitleTrackKind,
    VideoMetadata,
    VideoPage,
)
from bili_subtitle.infrastructure.export import plan_output_paths


def _selection() -> PageSelection:
    pages = (VideoPage(1, 11, "one"), VideoPage(2, 22, "two"))
    video = VideoMetadata(1, "BV1xx411c7mD", "video", pages)
    return PageSelection(video, pages, SelectionSource.DEFAULT_ALL)


def test_path_planner_is_windows_safe_unique_and_bounded(tmp_path: Path) -> None:
    page = VideoPage(1, 1, "CON. <>:\"/\\|?* .")
    tracks = (
        SubtitleTrack(1, "ZH", "a", SubtitleTrackKind.HUMAN),
        SubtitleTrack(2, "zh", "b", SubtitleTrackKind.AI),
    )
    root, plans = plan_output_paths(
        cwd=tmp_path / ("deep" * 5),
        video=VideoMetadata(1, "BV1xx411c7mD", "NUL." + "长" * 200, (page,)),
        page=page,
        tracks=tracks,
    )
    assert root.name.endswith("[BV1xx411c7mD]")
    assert len({p.json_path.name.casefold() for p in plans}) == 2
    assert all(len(str(path.resolve())) + 40 <= 240 for p in plans for path in (p.json_path, p.srt_path))
    assert all(not any(char in p.basename for char in '<>:"/\\|?*') for p in plans)


class Subtitles:
    def __init__(self) -> None:
        self.downloads: list[int] = []

    def discover(self, *, bvid: str, cid: int) -> tuple[SubtitleTrack, ...]:
        del bvid
        if cid == 22:
            return ()
        return (
            SubtitleTrack(1, "zh-CN", "A", SubtitleTrackKind.HUMAN),
            SubtitleTrack(2, "en-US", "B", SubtitleTrackKind.AI),
            SubtitleTrack(3, "zh-CN", "C", SubtitleTrackKind.AI),
        )

    def download_selected(
        self, *, bvid: str, cid: int, selected: SubtitleTrack
    ) -> SubtitleBody:
        del bvid, cid
        self.downloads.append(selected.track_id)
        return SubtitleBody(b'{"body":[]}', ())


def test_full_flow_filters_in_platform_order_and_skips_existing(tmp_path: Path) -> None:
    subtitles = Subtitles()
    result = run_extraction(
        selection=_selection(), languages=("zh-CN", "zh-CN"), force=False,
        cwd=tmp_path, subtitles=subtitles,
    )
    assert [item.track.track_id for item in result.pages[0].tracks] == [1, 3]
    assert result.pages[1].status == "no_subtitles"
    assert result.exit_code == 0
    assert subtitles.downloads == [1, 3]
    second = run_extraction(
        selection=_selection(), languages=("zh-CN",), force=False,
        cwd=tmp_path, subtitles=subtitles,
    )
    assert subtitles.downloads == [1, 3]
    assert all(t.json_action == t.srt_action == "skipped" for t in second.pages[0].tracks)


def test_track_failure_isolated_and_exit_codes(tmp_path: Path) -> None:
    class Broken(Subtitles):
        def download_selected(
            self, *, bvid: str, cid: int, selected: SubtitleTrack
        ) -> SubtitleBody:
            if selected.track_id == 1:
                raise RuntimeError("secret response")
            return super().download_selected(bvid=bvid, cid=cid, selected=selected)

    partial = run_extraction(
        selection=_selection(), languages=("zh-CN",), force=False,
        cwd=tmp_path, subtitles=Broken(),
    )
    assert partial.exit_code == 1
    assert partial.pages[0].tracks[0].error == "字幕处理失败。"
    assert partial.pages[0].tracks[1].status == "success"

    with pytest.raises(ValueError):
        run_extraction(
            selection=_selection(), languages=("",), force=False,
            cwd=tmp_path, subtitles=Subtitles(),
        )
