"""完整 V1 多分集、多轨道串行编排。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, cast

from bili_subtitle.domain.errors import NoSubtitles
from bili_subtitle.domain.models import PageSelection, SubtitleBody, SubtitleTrack, VideoPage
from bili_subtitle.infrastructure.export import (
    BatchPublishError,
    OutputPlan,
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
        plans: list[OutputPlan | None]
        try:
            output_root, complete_plans = plan_output_paths(
                cwd=cwd, video=selection.video, page=page, tracks=selected
            )
            plans = list(_reuse_manifest_plans(output_root, page, selected, complete_plans))
        except Exception:
            # 路径身份包含轨道字段；单条异常轨道不能阻止同分集其他轨道。
            plans = []
            for track in selected:
                try:
                    candidate_root, candidate = plan_output_paths(
                        cwd=cwd, video=selection.video, page=page, tracks=(track,)
                    )
                    output_root = candidate_root
                    plans.append(candidate[0])
                except Exception:
                    plans.append(None)
            collisions: dict[str, list[int]] = {}
            for index, plan in enumerate(plans):
                if plan is not None:
                    collisions.setdefault(plan.basename.casefold(), []).append(index)
            for indexes in collisions.values():
                if len(indexes) > 1:
                    for index in indexes:
                        plans[index] = None
        track_results: list[TrackResult] = []
        for track, plan in zip(selected, plans, strict=True):
            if plan is None:
                track_results.append(TrackResult(track, "failed", error="输出路径规划失败。"))
                continue
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
            except BatchPublishError as exc:
                published = set(exc.published)
                if plan.json_path in published:
                    json_action = "replaced" if json_exists else "written"
                elif force or not json_exists:
                    json_action = "failed"
                else:
                    json_action = "skipped"
                if plan.srt_path in published:
                    srt_action = "replaced" if srt_exists else "written"
                elif force or not srt_exists:
                    srt_action = "failed"
                else:
                    srt_action = "skipped"
                track_results.append(
                    TrackResult(
                        track,
                        "failed",
                        plan.json_path.name if plan.json_path.exists() else None,
                        plan.srt_path.name if plan.srt_path.exists() else None,
                        json_action,
                        srt_action,
                        "字幕文件发布失败。",
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
            "path_history": _manifest_path_history(output_root, page_results),
        }
        try:
            publish_atomic(
                output_root / "manifest.json",
                (json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n").encode(),
                replace=(output_root / "manifest.json").exists(),
            )
        except Exception:
            manifest_failed = True
    else:
        manifest_failed = True
    return FlowResult(tuple(page_results), manifest_failed)


def _reuse_manifest_plans(
    output_root: Path,
    page: VideoPage,
    tracks: tuple[SubtitleTrack, ...],
    planned: tuple[OutputPlan, ...],
) -> tuple[OutputPlan, ...]:
    """Reuse unambiguous prior paths when the platform rotates numeric track IDs."""
    try:
        payload = cast(
            object,
            json.loads((output_root / "manifest.json").read_text(encoding="utf-8")),
        )
        if not isinstance(payload, Mapping):
            return planned
        document = cast(Mapping[object, object], payload)
        history = document.get("path_history")
        history_candidates = (
            [
                cast(Mapping[object, object], item)
                for item in cast(list[object], history)
                if isinstance(item, Mapping)
                and cast(Mapping[object, object], item).get("cid") == page.cid
            ]
            if isinstance(history, list)
            else []
        )
        pages = document.get("pages")
        if not isinstance(pages, list):
            return planned
        previous_page = next(
            cast(Mapping[object, object], item)
            for item in cast(list[object], pages)
            if isinstance(item, Mapping)
            and cast(Mapping[object, object], item).get("cid") == page.cid
        )
        previous_tracks = previous_page.get("tracks")
        if not isinstance(previous_tracks, list):
            return planned
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        return planned

    reused = list(planned)
    claimed: set[int] = set()
    for index, track in enumerate(tracks):
        matches: list[tuple[int, OutputPlan]] = []
        raw_candidates: list[Mapping[object, object]] = history_candidates or [
            cast(Mapping[object, object], item)
            for item in cast(list[object], previous_tracks)
            if isinstance(item, Mapping)
        ]
        for old_index, record in enumerate(raw_candidates):
            if old_index in claimed:
                continue
            identity = record.get("track", record)
            if not isinstance(identity, Mapping):
                continue
            identity_fields = cast(Mapping[object, object], identity)
            # The live player response rotates IDs and occasionally presentation
            # metadata.  A language is reusable only when it identifies exactly
            # one prior record; same-language multi-track pages remain ambiguous.
            if identity_fields.get("language") != track.language:
                continue
            json_name, srt_name = record.get("json_file"), record.get("srt_file")
            if not _safe_manifest_pair(json_name, srt_name):
                continue
            assert isinstance(json_name, str) and isinstance(srt_name, str)
            matches.append(
                (
                    old_index,
                    OutputPlan(
                        json_name.removesuffix(".json"),
                        output_root / json_name,
                        output_root / srt_name,
                    ),
                )
            )
        if len(matches) == 1:
            old_index, reused[index] = matches[0]
            claimed.add(old_index)
    return tuple(reused)


def _manifest_path_history(
    output_root: Path, page_results: list[PageResult]
) -> list[dict[str, object]]:
    history: list[dict[str, object]] = []
    try:
        payload = cast(
            object,
            json.loads((output_root / "manifest.json").read_text(encoding="utf-8")),
        )
        if isinstance(payload, Mapping):
            raw_history = cast(Mapping[object, object], payload).get("path_history")
            if isinstance(raw_history, list):
                for raw in cast(list[object], raw_history):
                    if isinstance(raw, Mapping):
                        item = cast(Mapping[object, object], raw)
                        if isinstance(item.get("cid"), int) and _safe_manifest_pair(
                            item.get("json_file"), item.get("srt_file")
                        ):
                            history.append({str(key): value for key, value in item.items()})
    except (OSError, ValueError, TypeError):
        pass

    for page_result in page_results:
        for result in page_result.tracks:
            if result.status != "success" or not _safe_manifest_pair(
                result.json_file, result.srt_file
            ):
                continue
            same_language = [
                index
                for index, item in enumerate(history)
                if item.get("cid") == page_result.page.cid
                and item.get("language") == result.track.language
            ]
            entry: dict[str, object] = {
                "cid": page_result.page.cid,
                "language": result.track.language,
                "display_name": result.track.display_name,
                "kind": result.track.kind.value,
                "json_file": result.json_file,
                "srt_file": result.srt_file,
            }
            if len(same_language) == 1:
                history[same_language[0]] = entry
            elif not same_language:
                history.append(entry)
    return history


def _safe_manifest_pair(json_name: object, srt_name: object) -> bool:
    if not isinstance(json_name, str) or not isinstance(srt_name, str):
        return False
    json_path, srt_path = Path(json_name), Path(srt_name)
    return (
        json_path.name == json_name
        and srt_path.name == srt_name
        and json_name.endswith(".json")
        and srt_name.endswith(".srt")
        and json_name.removesuffix(".json") == srt_name.removesuffix(".srt")
    )


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
