"""完整 V1 多分集、多轨道串行编排。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from bili_subtitle.domain.errors import NoSubtitles
from bili_subtitle.domain.models import PageSelection, SubtitleBody, SubtitleTrack, VideoPage
from bili_subtitle.infrastructure.export import (
    plan_output_paths,
    publish_atomic,
    publish_batch,
    render_srt,
)


class SubtitlePort(Protocol):
    def discover(self, *, bvid: str, cid: int) -> tuple[SubtitleTrack, ...]: ...
    def download_selected(
        self, *, bvid: str, cid: int, selected: SubtitleTrack
    ) -> SubtitleBody: ...


@dataclass(frozen=True, slots=True)
class TrackResult:
    track: SubtitleTrack
    status: str
    json_file: str | None = None
    srt_file: str | None = None
    json_action: str | None = None
    srt_action: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class PageResult:
    page: VideoPage
    status: str
    tracks: tuple[TrackResult, ...] = ()
    error: str | None = None


@dataclass(frozen=True, slots=True)
class FlowResult:
    pages: tuple[PageResult, ...]
    manifest_failed: bool

    @property
    def exit_code(self) -> int:
        failures = self.manifest_failed or any(
            page.status == "failed" or any(track.status == "failed" for track in page.tracks)
            for page in self.pages
        )
        valid = any(track.status == "success" for page in self.pages for track in page.tracks)
        return 0 if not failures else (1 if valid else 2)


def run_extraction(
    *,
    selection: PageSelection,
    languages: tuple[str, ...],
    force: bool,
    cwd: Path,
    subtitles: SubtitlePort,
) -> FlowResult:
    if any(not language.strip() for language in languages):
        raise ValueError("语言代码不能为空。")
    language_set = frozenset(dict.fromkeys(languages))
    page_results: list[PageResult] = []
    output_root: Path | None = None
    for page in selection.pages:
        try:
            discovered = subtitles.discover(bvid=selection.video.bvid, cid=page.cid)
        except NoSubtitles:
            page_results.append(PageResult(page, "no_subtitles"))
            continue
        except Exception:
            page_results.append(PageResult(page, "failed", error="字幕轨道发现失败。"))
            continue
        if not discovered:
            page_results.append(PageResult(page, "no_subtitles"))
            continue
        selected = tuple(t for t in discovered if not language_set or t.language in language_set)
        if not selected:
            page_results.append(PageResult(page, "no_match"))
            continue
        try:
            output_root, plans = plan_output_paths(
                cwd=cwd, video=selection.video, page=page, tracks=selected
            )
        except Exception:
            page_results.append(PageResult(page, "failed", error="输出路径规划失败。"))
            continue
        track_results: list[TrackResult] = []
        for track, plan in zip(selected, plans, strict=True):
            json_exists, srt_exists = plan.json_path.exists(), plan.srt_path.exists()
            if not force and json_exists and srt_exists:
                track_results.append(
                    TrackResult(
                        track,
                        "success",
                        plan.json_path.name,
                        plan.srt_path.name,
                        "skipped",
                        "skipped",
                    )
                )
                continue
            try:
                body = subtitles.download_selected(
                    bvid=selection.video.bvid, cid=page.cid, selected=track
                )
                srt = render_srt(body.cues).encode("utf-8")
                json_action = "replaced" if json_exists else "written"
                srt_action = "replaced" if srt_exists else "written"
                publications: list[tuple[Path, bytes, bool]] = []
                if force or not json_exists:
                    publications.append((plan.json_path, body.raw_json, json_exists))
                else:
                    json_action = "skipped"
                if force or not srt_exists:
                    publications.append((plan.srt_path, srt, srt_exists))
                else:
                    srt_action = "skipped"
                publish_batch(tuple(publications))
                track_results.append(
                    TrackResult(
                        track,
                        "success",
                        plan.json_path.name,
                        plan.srt_path.name,
                        json_action,
                        srt_action,
                    )
                )
            except Exception:
                track_results.append(TrackResult(track, "failed", error="字幕处理失败。"))
        page_results.append(PageResult(page, "success", tuple(track_results)))
    manifest_failed = False
    if output_root is None:
        try:
            output_root, _ = plan_output_paths(
                cwd=cwd, video=selection.video, page=selection.pages[0], tracks=()
            )
        except Exception:
            output_root = None
    if output_root is not None:
        manifest = {
            "schema_version": 2,
            "video": {
                "aid": selection.video.aid,
                "bvid": selection.video.bvid,
                "title": selection.video.title,
            },
            "pages": [_manifest_page(item) for item in page_results],
        }
        try:
            publish_atomic(
                output_root / "manifest.json",
                (json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n").encode(),
                replace=(output_root / "manifest.json").exists(),
            )
        except Exception:
            manifest_failed = True
    return FlowResult(tuple(page_results), manifest_failed)


def _manifest_page(result: PageResult) -> dict[str, object]:
    return {
        "number": result.page.number,
        "cid": result.page.cid,
        "title": result.page.title,
        "status": result.status,
        "error": result.error,
        "tracks": [
            {
                **asdict(track),
                "track": {
                    "id": track.track.track_id,
                    "language": track.track.language,
                    "display_name": track.track.display_name,
                    "kind": track.track.kind.value,
                },
            }
            for track in result.tracks
        ],
    }
