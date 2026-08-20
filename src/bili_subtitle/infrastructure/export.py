"""忠实 SRT 转换与单轨道安全文件发布。"""

from __future__ import annotations

import json
import os
import tempfile
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
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{basename}.json"
    srt_path = output_dir / f"{basename}.srt"
    manifest_path = output_dir / "manifest.json"
    _publish_new(json_path, body.raw_json)
    _publish_new(srt_path, render_srt(body.cues).encode("utf-8"))
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
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n").encode()
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
