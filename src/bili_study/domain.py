"""Stage-eight learning domain models and evidence invariants."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

SCHEMA_VERSION = 1


class DomainError(ValueError):
    """A stable, user-correctable learning-domain error."""


class SubtitleTrackUnavailable(DomainError):
    """The subtitle track selected during inspection is no longer available."""


class SubtitleTrackAmbiguous(DomainError):
    """More than one current track matches the inspected stable descriptors."""


class TranscriptSourceMismatch(DomainError):
    """A saved revision does not belong to the caller's expected canonical BV/P."""


@dataclass(frozen=True, slots=True)
class TranscriptCue:
    cue_id: str
    start_ms: int
    end_ms: int
    text: str

    def __post_init__(self) -> None:
        if not self.cue_id or self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise DomainError("字幕 cue 的标识或时间范围无效。")
        if not self.text.strip():
            raise DomainError("字幕 cue 正文不能为空。")


@dataclass(frozen=True, slots=True)
class TranscriptRevision:
    revision_id: str
    schema_version: int
    bvid: str
    page: int
    cid: int
    title: str
    track_id: int | None
    language: str
    display_name: str
    kind: str
    content_sha256: str
    created_at: str
    cues: tuple[TranscriptCue, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or not self.revision_id:
            raise DomainError("Transcript revision 版本无效。")
        if not self.bvid or self.page < 1 or self.cid < 1 or not self.language:
            raise DomainError("Transcript 来源无效。")
        if not self.cues:
            raise DomainError("Transcript 不能为空。")
        for index, cue in enumerate(self.cues):
            if cue.cue_id != f"c{index + 1:06d}":
                raise DomainError("字幕 cue 标识必须稳定且连续。")
            if index and cue.start_ms < self.cues[index - 1].start_ms:
                raise DomainError("字幕 cue 必须按开始时间排序。")
        expected = transcript_hash(self.cues)
        if self.content_sha256 != expected:
            raise DomainError("Transcript 内容哈希无效。")

    def cue_index(self, cue_id: str) -> int:
        try:
            return next(index for index, cue in enumerate(self.cues) if cue.cue_id == cue_id)
        except StopIteration as exc:
            raise DomainError("证据引用了不存在的 cue。") from exc


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    revision_id: str
    start_cue_id: str
    end_cue_id: str

    def resolve(self, transcript: TranscriptRevision) -> tuple[TranscriptCue, ...]:
        if self.revision_id != transcript.revision_id:
            raise DomainError("证据不属于当前 Transcript revision。")
        start = transcript.cue_index(self.start_cue_id)
        end = transcript.cue_index(self.end_cue_id)
        if end < start:
            raise DomainError("证据 cue 范围倒序。")
        return transcript.cues[start : end + 1]

    def time_range(self, transcript: TranscriptRevision) -> tuple[int, int]:
        cues = self.resolve(transcript)
        return cues[0].start_ms, cues[-1].end_ms


@dataclass(frozen=True, slots=True)
class GuidingQuestion:
    question_id: str
    text: str
    evidence: EvidenceRef


@dataclass(frozen=True, slots=True)
class Chapter:
    chapter_id: str
    title: str
    summary: str
    evidence: EvidenceRef
    questions: tuple[GuidingQuestion, ...] = ()


@dataclass(frozen=True, slots=True)
class StudyGuide:
    guide_id: str
    schema_version: int
    revision_id: str
    fingerprint: str
    output_language: str
    learning_objectives: tuple[str, ...]
    chapters: tuple[Chapter, ...]
    created_at: str

    def validate(self, transcript: TranscriptRevision) -> None:
        if self.schema_version != SCHEMA_VERSION or self.revision_id != transcript.revision_id:
            raise DomainError("学习指南版本或来源无效。")
        if not self.chapters:
            raise DomainError("学习指南必须至少包含一个章节。")
        ranges: list[tuple[int, int]] = []
        for chapter in self.chapters:
            resolved = chapter.evidence.resolve(transcript)
            for question in chapter.questions:
                question.evidence.resolve(transcript)
            ranges.append(
                (
                    transcript.cue_index(resolved[0].cue_id),
                    transcript.cue_index(resolved[-1].cue_id),
                )
            )
        if ranges[0][0] != 0 or ranges[-1][1] != len(transcript.cues) - 1:
            raise DomainError("学习指南没有覆盖完整 Transcript。")
        if any(
            current[0] > previous[1] + 1 or current[0] < previous[0]
            for previous, current in zip(ranges, ranges[1:], strict=False)
        ):
            raise DomainError("学习指南章节顺序或覆盖范围无效。")


@dataclass(frozen=True, slots=True)
class PersonalNote:
    note_id: str
    revision_id: str
    timestamp_ms: int
    note_type: str
    body: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        if not self.note_id or self.timestamp_ms < 0 or not self.body.strip():
            raise DomainError("个人笔记无效。")


@dataclass(frozen=True, slots=True)
class Reflection:
    reflection_id: str
    question_id: str
    response: str
    covered: tuple[str, ...]
    missing: tuple[str, ...]
    misconceptions: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def transcript_hash(cues: tuple[TranscriptCue, ...]) -> str:
    payload = [[cue.start_ms, cue.end_ms, cue.text] for cue in cues]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_transcript(
    *,
    bvid: str,
    page: int,
    cid: int,
    title: str,
    track_id: int | None,
    language: str,
    display_name: str,
    kind: str,
    cue_values: tuple[tuple[int, int, str], ...],
    created_at: str | None = None,
) -> TranscriptRevision:
    cues = tuple(
        TranscriptCue(f"c{index + 1:06d}", start, end, text)
        for index, (start, end, text) in enumerate(cue_values)
    )
    digest = transcript_hash(cues)
    identity = f"https://www.bilibili.com/video/{bvid}?p={page}#{cid}/{language}/{kind}/{digest}"
    return TranscriptRevision(
        str(uuid5(NAMESPACE_URL, identity)),
        SCHEMA_VERSION,
        bvid,
        page,
        cid,
        title,
        track_id,
        language,
        display_name,
        kind,
        digest,
        created_at or now_iso(),
        cues,
    )


def generation_fingerprint(
    transcript: TranscriptRevision,
    *,
    provider: str,
    model: str,
    output_language: str,
    prompt_version: str,
    parameters: dict[str, object] | None = None,
) -> str:
    payload = {
        "transcript": transcript.content_sha256,
        "provider": provider,
        "model": model,
        "language": output_language,
        "schema": SCHEMA_VERSION,
        "prompt": prompt_version,
        "parameters": parameters or {},
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def new_note(*, revision_id: str, timestamp_ms: int, note_type: str, body: str) -> PersonalNote:
    timestamp = now_iso()
    return PersonalNote(
        str(uuid4()), revision_id, timestamp_ms, note_type, body, timestamp, timestamp
    )


def to_json(value: TranscriptRevision | StudyGuide | PersonalNote) -> str:
    return json.dumps(asdict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def transcript_from_dict(raw: dict[str, Any]) -> TranscriptRevision:
    page = int(raw["page"])
    return TranscriptRevision(
        revision_id=str(raw["revision_id"]),
        schema_version=int(raw["schema_version"]),
        bvid=str(raw["bvid"]),
        page=page,
        cid=int(raw["cid"]),
        title=str(raw.get("title") or f"P{page}（历史记录）"),
        track_id=int(raw["track_id"]) if raw.get("track_id") is not None else None,
        language=str(raw["language"]),
        display_name=str(raw["display_name"]),
        kind=str(raw["kind"]),
        content_sha256=str(raw["content_sha256"]),
        created_at=str(raw["created_at"]),
        cues=tuple(TranscriptCue(**cue) for cue in raw["cues"]),
    )
