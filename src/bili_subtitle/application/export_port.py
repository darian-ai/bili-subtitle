"""Application-owned boundary for subtitle output publication."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bili_subtitle.domain.errors import ExportError
from bili_subtitle.domain.models import SubtitleCue, SubtitleTrack, VideoMetadata, VideoPage


@dataclass(frozen=True, slots=True)
class OutputPlan:
    basename: str
    json_path: Path
    srt_path: Path


class BatchPublishError(ExportError):
    """A batch failed after zero or more targets had been published."""

    def __init__(self, published: tuple[Path, ...]) -> None:
        super().__init__("无法安全发布字幕文件。")
        self.published = published


class ExportPort(Protocol):
    def plan(
        self,
        *,
        cwd: Path,
        video: VideoMetadata,
        page: VideoPage,
        tracks: tuple[SubtitleTrack, ...],
    ) -> tuple[Path, tuple[OutputPlan, ...]]: ...

    def render_srt(self, cues: tuple[SubtitleCue, ...]) -> str: ...
    def exists(self, path: Path) -> bool: ...
    def read_manifest(self, output_root: Path) -> object | None: ...
    def publish_batch(self, publications: tuple[tuple[Path, bytes, bool], ...]) -> None: ...
    def publish_atomic(self, target: Path, content: bytes, *, replace: bool) -> None: ...
