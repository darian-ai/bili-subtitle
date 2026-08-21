import os
from pathlib import Path

import pytest

import bili_subtitle.application.full_flow as flow_module
import bili_subtitle.infrastructure.export as export_module
from bili_subtitle.application.full_flow import run_extraction
from bili_subtitle.domain.errors import ExportError
from bili_subtitle.domain.models import (
    PageSelection,
    SelectionSource,
    SubtitleBody,
    SubtitleTrack,
    SubtitleTrackKind,
    VideoMetadata,
    VideoPage,
)
from bili_subtitle.infrastructure.export import plan_output_paths, sanitize_component


def _selection() -> PageSelection:
    pages = (VideoPage(1, 11, "one"), VideoPage(2, 22, "two"))
    video = VideoMetadata(1, "BV1xx411c7mD", "video", pages)
    return PageSelection(video, pages, SelectionSource.DEFAULT_ALL)


def test_path_planner_is_windows_safe_unique_and_bounded(tmp_path: Path) -> None:
    page = VideoPage(1, 1, 'CON. <>:"/\\|?* .')
    tracks = (
        SubtitleTrack(1, "ZH", "a", SubtitleTrackKind.HUMAN),
        SubtitleTrack(2, "zh", "b", SubtitleTrackKind.AI),
    )
    root, plans = plan_output_paths(
        cwd=tmp_path,
        video=VideoMetadata(1, "BV1xx411c7mD", "NUL." + "长" * 200, (page,)),
        page=page,
        tracks=tracks,
    )
    assert root.name.endswith("[BV1xx411c7mD]")
    assert len({p.json_path.name.casefold() for p in plans}) == 2
    assert all(
        len(str(path.resolve())) + 40 <= 240 for p in plans for path in (p.json_path, p.srt_path)
    )
    assert all(not any(char in p.basename for char in '<>:"/\\|?*') for p in plans)


def _directory_with_resolved_length(base: Path, length: int) -> Path:
    missing = length - len(str(base.resolve())) - 1
    if missing < 1:
        pytest.skip("pytest temporary root is already beyond the requested boundary")
    result = base / ("d" * missing)
    assert len(str(result.resolve())) == length
    return result


def _long_cwd_boundary(tmp_path: Path) -> tuple[Path, Path]:
    page = VideoPage(1, 1, "p" * 200)
    video = VideoMetadata(1, "BV1xx411c7mD", "v" * 200, (page,))
    track = SubtitleTrack(7, "en-US", "English", SubtitleTrackKind.HUMAN)
    last_success: Path | None = None
    for length in range(len(str(tmp_path.parent.resolve())) + 2, 200):
        candidate = _directory_with_resolved_length(tmp_path.parent, length)
        try:
            plan_output_paths(cwd=candidate, video=video, page=page, tracks=(track,))
        except ExportError:
            assert last_success is not None
            return last_success, candidate
        last_success = candidate
    pytest.fail("path planner did not enforce its 240-character boundary")


def test_path_planner_accepts_long_cwd_at_exact_temporary_budget(tmp_path: Path) -> None:
    cwd, _ = _long_cwd_boundary(tmp_path)
    page = VideoPage(1, 1, "p" * 200)
    video = VideoMetadata(1, "BV1xx411c7mD", "v" * 200, (page,))

    root, plans = plan_output_paths(
        cwd=cwd,
        video=video,
        page=page,
        tracks=(SubtitleTrack(7, "en-US", "English", SubtitleTrackKind.HUMAN),),
    )

    plan = plans[0]
    assert root.name.endswith("[BV1xx411c7mD]")
    assert root.name.startswith("~")
    assert plan.basename.startswith("P01-~")
    assert plan.basename.endswith(".en-US.7")
    assert len(str(plan.json_path.resolve())) + 40 == 240


def test_path_planner_rejects_cwd_with_no_identity_and_temp_space(tmp_path: Path) -> None:
    _, cwd = _long_cwd_boundary(tmp_path)
    page = VideoPage(1, 1, "p" * 200)
    video = VideoMetadata(1, "BV1xx411c7mD", "v" * 200, (page,))

    with pytest.raises(ExportError, match="工作目录过长"):
        plan_output_paths(
            cwd=cwd,
            video=video,
            page=page,
            tracks=(SubtitleTrack(7, "en-US", "English", SubtitleTrackKind.HUMAN),),
        )


def test_path_planner_keeps_collision_identity_with_long_titles(tmp_path: Path) -> None:
    page = VideoPage(123, 9, "page" * 100)
    tracks = (
        SubtitleTrack(42, "a:b", "one", SubtitleTrackKind.HUMAN),
        SubtitleTrack(42, "a?b", "two", SubtitleTrackKind.AI),
    )
    video = VideoMetadata(1, "BV1xx411c7mD", "video" * 100, (page,))

    _, plans = plan_output_paths(cwd=tmp_path, video=video, page=page, tracks=tracks)

    assert all(plan.basename.startswith("P123-") for plan in plans)
    assert all(".a_b.42~" in plan.basename for plan in plans)
    assert len({plan.basename.casefold() for plan in plans}) == 2
    assert all(
        len(str(path.resolve())) + 40 <= 240
        for plan in plans
        for path in (plan.json_path, plan.srt_path)
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("CON", "_CON"),
        ("prn.txt", "_prn.txt"),
        ("COM9", "_COM9"),
        ("lpt1.log", "_lpt1.log"),
        ("name. ", "name"),
        ('<>:"/\\|?*\x00', "__________"),
        (" . ", "untitled"),
    ],
)
def test_sanitize_component_covers_windows_edge_cases(source: str, expected: str) -> None:
    assert sanitize_component(source) == expected


def test_collision_resolution_is_stable_when_track_order_changes(tmp_path: Path) -> None:
    page = VideoPage(1, 1, "page")
    tracks = (
        SubtitleTrack(1, "a:b", "one", SubtitleTrackKind.HUMAN),
        SubtitleTrack(1, "a?b", "two", SubtitleTrackKind.AI),
    )
    video = VideoMetadata(1, "BV1xx411c7mD", "video", (page,))
    _, forward = plan_output_paths(cwd=tmp_path, video=video, page=page, tracks=tracks)
    _, reverse = plan_output_paths(cwd=tmp_path, video=video, page=page, tracks=tracks[::-1])
    by_language = {
        track.language: plan.basename for track, plan in zip(tracks, forward, strict=True)
    }
    reverse_by_language = {
        track.language: plan.basename for track, plan in zip(tracks[::-1], reverse, strict=True)
    }
    assert by_language == reverse_by_language
    assert len({name.casefold() for name in by_language.values()}) == 2


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

    def download_selected(self, *, bvid: str, cid: int, selected: SubtitleTrack) -> SubtitleBody:
        del bvid, cid
        self.downloads.append(selected.track_id)
        return SubtitleBody(b'{"body":[]}', ())


def test_full_flow_filters_in_platform_order_and_skips_existing(tmp_path: Path) -> None:
    subtitles = Subtitles()
    result = run_extraction(
        selection=_selection(),
        languages=("zh-CN", "zh-CN"),
        force=False,
        cwd=tmp_path,
        subtitles=subtitles,
    )
    assert [item.track.track_id for item in result.pages[0].tracks] == [1, 3]
    assert result.pages[1].status == "no_subtitles"
    assert result.exit_code == 0
    assert subtitles.downloads == [1, 3]
    second = run_extraction(
        selection=_selection(),
        languages=("zh-CN",),
        force=False,
        cwd=tmp_path,
        subtitles=subtitles,
    )
    assert subtitles.downloads == [1, 3]
    assert all(t.json_action == t.srt_action == "skipped" for t in second.pages[0].tracks)


def test_rotating_platform_track_id_reuses_unambiguous_manifest_paths(tmp_path: Path) -> None:
    class Rotating(Subtitles):
        def __init__(self) -> None:
            super().__init__()
            self.next_id = 100

        def discover(self, *, bvid: str, cid: int) -> tuple[SubtitleTrack, ...]:
            del bvid, cid
            self.next_id += 1
            return (SubtitleTrack(self.next_id, "zh-CN", "stable", SubtitleTrackKind.AI),)

    selection = PageSelection(
        _selection().video, (_selection().pages[0],), SelectionSource.EXPLICIT_PAGE
    )
    subtitles = Rotating()
    first = run_extraction(
        selection=selection, languages=(), force=False, cwd=tmp_path, subtitles=subtitles
    )
    second = run_extraction(
        selection=selection, languages=(), force=False, cwd=tmp_path, subtitles=subtitles
    )

    assert first.pages[0].tracks[0].track.track_id != second.pages[0].tracks[0].track.track_id
    assert second.pages[0].tracks[0].json_action == "skipped"
    assert second.pages[0].tracks[0].srt_action == "skipped"
    assert len(subtitles.downloads) == 1
    output = next((tmp_path / "subtitles").iterdir())
    assert len(tuple(output.glob("*.srt"))) == 1


def test_manifest_path_reuse_rejects_parent_traversal(tmp_path: Path) -> None:
    page = VideoPage(1, 11, "one")
    track = SubtitleTrack(2, "zh-CN", "stable", SubtitleTrackKind.AI)
    video = VideoMetadata(1, "BV1xx411c7mD", "video", (page,))
    root, planned = plan_output_paths(cwd=tmp_path, video=video, page=page, tracks=(track,))
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(
        '{"pages":[{"cid":11,"tracks":[{"track":{"language":"zh-CN",'
        '"display_name":"stable","kind":"ai"},"json_file":"../outside.json",'
        '"srt_file":"../outside.srt"}]}]}',
        encoding="utf-8",
    )

    reused = flow_module._reuse_manifest_plans(  # pyright: ignore[reportPrivateUsage]
        root, page, (track,), planned
    )
    assert reused == planned


def test_path_history_survives_temporarily_unavailable_track(tmp_path: Path) -> None:
    class Intermittent(Subtitles):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def discover(self, *, bvid: str, cid: int) -> tuple[SubtitleTrack, ...]:
            del bvid, cid
            self.calls += 1
            if self.calls == 2:
                return ()
            return (SubtitleTrack(100 + self.calls, "zh-CN", "x", SubtitleTrackKind.AI),)

    selection = PageSelection(
        _selection().video, (_selection().pages[0],), SelectionSource.EXPLICIT_PAGE
    )
    subtitles = Intermittent()
    first = run_extraction(
        selection=selection, languages=(), force=False, cwd=tmp_path, subtitles=subtitles
    )
    absent = run_extraction(
        selection=selection, languages=(), force=False, cwd=tmp_path, subtitles=subtitles
    )
    restored = run_extraction(
        selection=selection, languages=(), force=False, cwd=tmp_path, subtitles=subtitles
    )

    assert first.pages[0].tracks[0].json_action == "written"
    assert absent.pages[0].status == "no_subtitles"
    assert restored.pages[0].tracks[0].json_action == "skipped"
    assert len(subtitles.downloads) == 1


def test_track_failure_isolated_and_exit_codes(tmp_path: Path) -> None:
    class Broken(Subtitles):
        def download_selected(
            self, *, bvid: str, cid: int, selected: SubtitleTrack
        ) -> SubtitleBody:
            if selected.track_id == 1:
                raise RuntimeError("secret response")
            return super().download_selected(bvid=bvid, cid=cid, selected=selected)

    partial = run_extraction(
        selection=_selection(),
        languages=("zh-CN",),
        force=False,
        cwd=tmp_path,
        subtitles=Broken(),
    )
    assert partial.exit_code == 1
    assert partial.pages[0].tracks[0].error == "字幕处理失败。"
    assert partial.pages[0].tracks[1].status == "success"

    with pytest.raises(ValueError):
        run_extraction(
            selection=_selection(),
            languages=("",),
            force=False,
            cwd=tmp_path,
            subtitles=Subtitles(),
        )


def test_invalid_track_path_only_fails_that_track(tmp_path: Path) -> None:
    class AbnormalLanguage(Subtitles):
        def discover(self, *, bvid: str, cid: int) -> tuple[SubtitleTrack, ...]:
            tracks = super().discover(bvid=bvid, cid=cid)
            if not tracks:
                return tracks
            return (
                SubtitleTrack(99, "x" * 500, "bad", SubtitleTrackKind.HUMAN),
                tracks[1],
            )

    result = run_extraction(
        selection=_selection(),
        languages=(),
        force=False,
        cwd=tmp_path,
        subtitles=AbnormalLanguage(),
    )

    assert result.exit_code == 1
    assert result.pages[0].tracks[0].status == "failed"
    assert result.pages[0].tracks[0].error == "输出路径规划失败。"
    assert result.pages[0].tracks[1].status == "success"


def test_second_replace_failure_preserves_first_and_records_partial_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subtitles = Subtitles()
    initial = run_extraction(
        selection=_selection(), languages=("en-US",), force=False, cwd=tmp_path, subtitles=subtitles
    )
    track = initial.pages[0].tracks[0]
    root = next((tmp_path / "subtitles").iterdir())
    assert track.json_file and track.srt_file
    json_path, srt_path = root / track.json_file, root / track.srt_file
    old_json, old_srt = json_path.read_bytes(), srt_path.read_bytes()
    real_replace = os.replace
    replacements = 0

    def fail_second(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("injected second replace failure")
        real_replace(source, target)

    monkeypatch.setattr(export_module.os, "replace", fail_second)
    result = run_extraction(
        selection=_selection(), languages=("en-US",), force=True, cwd=tmp_path, subtitles=subtitles
    )

    failed = result.pages[0].tracks[0]
    assert result.exit_code == 2
    assert failed.status == "failed"
    assert failed.json_action == "replaced"
    assert failed.srt_action == "failed"
    assert json_path.read_bytes() == old_json
    assert srt_path.read_bytes() == old_srt
    assert not list(root.glob(".*.tmp"))
    manifest = __import__("json").loads((root / "manifest.json").read_text("utf-8"))
    manifest_track = manifest["pages"][0]["tracks"][0]
    assert manifest_track["json_action"] == "replaced"
    assert manifest_track["srt_action"] == "failed"
    assert manifest_track["status"] == "failed"


def test_no_match_missing_repair_force_and_manifest_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subtitles = Subtitles()
    no_match = run_extraction(
        selection=_selection(), languages=("fr",), force=False, cwd=tmp_path, subtitles=subtitles
    )
    assert no_match.exit_code == 0
    assert no_match.pages[0].status == "no_match"
    assert subtitles.downloads == []

    first = run_extraction(
        selection=_selection(), languages=("en-US",), force=False, cwd=tmp_path, subtitles=subtitles
    )
    track = first.pages[0].tracks[0]
    root = next((tmp_path / "subtitles").iterdir())
    assert track.json_file is not None and track.srt_file is not None
    json_path = root / track.json_file
    srt_path = root / track.srt_file
    original_json = json_path.read_bytes()
    srt_path.unlink()
    repaired = run_extraction(
        selection=_selection(), languages=("en-US",), force=False, cwd=tmp_path, subtitles=subtitles
    )
    assert repaired.pages[0].tracks[0].json_action == "skipped"
    assert repaired.pages[0].tracks[0].srt_action == "written"
    assert json_path.read_bytes() == original_json
    original_srt = srt_path.read_bytes()
    json_path.unlink()
    repaired_json = run_extraction(
        selection=_selection(), languages=("en-US",), force=False, cwd=tmp_path, subtitles=subtitles
    )
    assert repaired_json.pages[0].tracks[0].json_action == "written"
    assert repaired_json.pages[0].tracks[0].srt_action == "skipped"
    assert srt_path.read_bytes() == original_srt
    forced = run_extraction(
        selection=_selection(), languages=("en-US",), force=True, cwd=tmp_path, subtitles=subtitles
    )
    assert forced.pages[0].tracks[0].json_action == "replaced"

    real_publish = flow_module.publish_atomic

    def fail_manifest(target: Path, content: bytes, *, replace: bool) -> None:
        if target.name == "manifest.json":
            raise OSError("injected")
        real_publish(target, content, replace=replace)

    monkeypatch.setattr(flow_module, "publish_atomic", fail_manifest)
    failed = run_extraction(
        selection=_selection(), languages=("en-US",), force=False, cwd=tmp_path, subtitles=subtitles
    )
    assert failed.manifest_failed and failed.exit_code == 1
