"""阶段四单分集、明确单轨道闭环。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bili_subtitle.domain.models import SubtitleBody, SubtitleTrack, VideoMetadata, VideoPage


class SubtitlePort(Protocol):
    def discover(self, *, bvid: str, cid: int) -> tuple[SubtitleTrack, ...]: ...
    def download_selected(
        self, *, bvid: str, cid: int, selected: SubtitleTrack
    ) -> SubtitleBody: ...


class ExportPort(Protocol):
    def __call__(
        self,
        *,
        output_dir: Path,
        basename: str,
        video: VideoMetadata,
        page: VideoPage,
        track: SubtitleTrack,
        body: SubtitleBody,
    ) -> tuple[Path, Path, Path]: ...


@dataclass(frozen=True, slots=True)
class ExtractionSuccess:
    track: SubtitleTrack
    files: tuple[Path, Path, Path]


def extract_single_track(
    *,
    video: VideoMetadata,
    page: VideoPage,
    track_id: int,
    basename: str,
    output_dir: Path,
    subtitles: SubtitlePort,
    exporter: ExportPort,
) -> ExtractionSuccess:
    tracks = subtitles.discover(bvid=video.bvid, cid=page.cid)
    selected = tuple(track for track in tracks if track.track_id == track_id)
    if len(selected) != 1:
        from bili_subtitle.domain.errors import SubtitlePlatformResponseError

        raise SubtitlePlatformResponseError("指定的字幕轨道不在本次发现结果中。")
    track = selected[0]
    body = subtitles.download_selected(bvid=video.bvid, cid=page.cid, selected=track)
    files = exporter(
        output_dir=output_dir, basename=basename, video=video, page=page, track=track, body=body
    )
    return ExtractionSuccess(track, files)
