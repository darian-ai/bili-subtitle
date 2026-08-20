"""忠实 SRT 转换与单轨道安全文件发布。"""

from __future__ import annotations

import json
import os
import tempfile
import hashlib
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from bili_subtitle.domain.errors import ExportError
from bili_subtitle.domain.models import (
    SubtitleBody,
    SubtitleCue,
    SubtitleTrack,
    VideoMetadata,
    VideoPage,
)

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = re.compile(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$")
_PATH_LIMIT = 240
_TEMP_RESERVE = 40


@dataclass(frozen=True, slots=True)
class OutputPlan:
    basename: str
    json_path: Path
    srt_path: Path


def sanitize_component(value: str, *, placeholder: str = "untitled") -> str:
    cleaned = _INVALID.sub("_", value).rstrip(" .")
    if not cleaned:
        cleaned = placeholder
    if _RESERVED.fullmatch(cleaned):
        cleaned = f"_{cleaned}"
    return cleaned


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()[:10]


def plan_output_paths(
    *, cwd: Path, video: VideoMetadata, page: VideoPage, tracks: tuple[SubtitleTrack, ...]
) -> tuple[Path, tuple[OutputPlan, ...]]:
    root_base = f"{sanitize_component(video.title)} [{video.bvid}]"
    output_parent = cwd.resolve() / "subtitles"
    # Reserve room for the immutable page/language/track identity and extension.
    max_root = _PATH_LIMIT - _TEMP_RESERVE - 64 - len(str(output_parent.resolve())) - 1
    if max_root < len(video.bvid) + 15:
        raise ExportError("当前工作目录过长，无法安全规划输出路径。")
    if len(root_base) > max_root:
        suffix = f"~{_digest(video.title)} [{video.bvid}]"
        root_base = sanitize_component(video.title)[: max_root - len(suffix)] + suffix
    root = output_parent / root_base
    raw: list[tuple[SubtitleTrack, str, str]] = []
    for track in tracks:
        identity = f"P{page.number:02d}|{page.cid}|{track.language}|{track.track_id}"
        fixed = f"P{page.number:02d}-.{sanitize_component(track.language, placeholder='lang')}.{track.track_id}"
        max_title = _PATH_LIMIT - _TEMP_RESERVE - len(str(root.resolve())) - 1 - len(fixed) - 5
        if max_title < 1:
            raise ExportError("输出路径预算不足。")
        title = sanitize_component(page.title)
        if len(title) > max_title:
            suffix = f"~{_digest(page.title)}"
            title = title[: max(1, max_title - len(suffix))] + suffix
        raw.append((track, f"P{page.number:02d}-{title}.{sanitize_component(track.language, placeholder='lang')}.{track.track_id}", identity))
    groups: dict[str, list[int]] = {}
    for index, (_, basename, _) in enumerate(raw):
        groups.setdefault(basename.casefold(), []).append(index)
    plans: list[OutputPlan] = []
    for index, (_, basename, identity) in enumerate(raw):
        if len(groups[basename.casefold()]) > 1:
            basename = f"{basename}~{_digest(identity)}"
        plans.append(OutputPlan(basename, root / f"{basename}.json", root / f"{basename}.srt"))
    return root, tuple(plans)


def publish_atomic(target: Path, content: bytes, *, replace: bool) -> None:
    temporary: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, raw_path = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        temporary = Path(raw_path)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, target)
        else:
            os.link(temporary, target)
            temporary.unlink()
    except (OSError, ValueError) as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ExportError(f"无法安全发布文件：{target.name}") from exc


def render_srt(cues: tuple[SubtitleCue, ...]) -> str:
    blocks: list[str] = []
    for number, cue in enumerate(cues, 1):
        blocks.append(f"{number}\n{_timestamp(cue.start)} --> {_timestamp(cue.end)}\n{cue.text}\n")
    return "\n".join(blocks)


def _timestamp(seconds: Decimal) -> str:
    milliseconds = int((seconds * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{millis:03d}"


def export_single_track(
    *,
    output_dir: Path,
    basename: str,
    video: VideoMetadata,
    page: VideoPage,
    track: SubtitleTrack,
    body: SubtitleBody,
) -> tuple[Path, Path, Path]:
    json_path = output_dir / f"{basename}.json"
    srt_path = output_dir / f"{basename}.srt"
    manifest_path = output_dir / "manifest.json"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportError("无法创建字幕输出目录。") from exc
    # Reject the complete operation before publishing anything.  Phase four
    # deliberately has no overwrite, skip, or missing-file repair semantics.
    try:
        if any(path.exists() for path in (json_path, srt_path, manifest_path)):
            raise ExportError("字幕输出目标已经存在。")
        srt_bytes = render_srt(body.cues).encode("utf-8")
        manifest = {
            "schema_version": 1,
            "video": {"aid": video.aid, "bvid": video.bvid, "title": video.title},
            "page": {"number": page.number, "cid": page.cid, "title": page.title},
            "track": {
                "id": track.track_id,
                "language": track.language,
                "display_name": track.display_name,
                "kind": track.kind.value,
            },
            "files": {"json": json_path.name, "srt": srt_path.name},
            "result": "success",
        }
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )
    except ExportError:
        raise
    except (ArithmeticError, OSError, UnicodeError, ValueError) as exc:
        raise ExportError("无法准备字幕输出内容。") from exc
    _publish_new(json_path, body.raw_json)
    _publish_new(srt_path, srt_bytes)
    _publish_new(manifest_path, manifest_bytes)
    return json_path, srt_path, manifest_path


def _publish_new(target: Path, content: bytes) -> None:
    temporary: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(raw_path)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link publication is atomic and cannot overwrite an existing target.
        os.link(temporary, target)
        temporary.unlink()
    except (OSError, ValueError) as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ExportError(f"无法安全发布文件：{target.name}") from exc
