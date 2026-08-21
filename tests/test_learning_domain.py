from __future__ import annotations

import json
from dataclasses import replace

import pytest

from bili_study.domain import (
    DomainError,
    EvidenceRef,
    TranscriptCue,
    build_transcript,
    generation_fingerprint,
)
from bili_study.services import chunk_transcript, import_bilibili_json


def transcript(texts: tuple[str, ...] = ("第一条", "第二条", "最后一条")):
    return build_transcript(
        bvid="BV1xx411c7mD",
        page=1,
        cid=123,
        title="课程",
        track_id=7,
        language="zh-CN",
        display_name="中文",
        kind="ai",
        cue_values=tuple(
            (index * 1000, index * 1000 + 900, text) for index, text in enumerate(texts)
        ),
        created_at="2026-08-22T00:00:00+00:00",
    )


def test_transcript_identity_evidence_and_hash_are_stable() -> None:
    value = transcript()
    same = transcript()
    assert value.revision_id == same.revision_id
    assert value.content_sha256 == same.content_sha256
    evidence = EvidenceRef(value.revision_id, "c000001", "c000003")
    assert evidence.resolve(value) == value.cues
    assert evidence.time_range(value) == (0, 2900)


def test_transcript_and_evidence_reject_invalid_identity() -> None:
    value = transcript()
    with pytest.raises(DomainError, match="哈希"):
        replace(value, content_sha256="0" * 64)
    with pytest.raises(DomainError, match="当前"):
        EvidenceRef("old", "c000001", "c000001").resolve(value)
    with pytest.raises(DomainError, match="倒序"):
        EvidenceRef(value.revision_id, "c000003", "c000001").resolve(value)
    with pytest.raises(DomainError, match="不存在"):
        EvidenceRef(value.revision_id, "c999999", "c999999").resolve(value)


def test_cue_and_transcript_source_invariants() -> None:
    with pytest.raises(DomainError, match="时间"):
        TranscriptCue("", -1, 0, "x")
    with pytest.raises(DomainError, match="正文"):
        TranscriptCue("c000001", 0, 1, " ")
    with pytest.raises(DomainError, match="来源"):
        build_transcript(
            bvid="",
            page=0,
            cid=0,
            title="x",
            track_id=None,
            language="",
            display_name="x",
            kind="ai",
            cue_values=((0, 1, "x"),),
        )


def test_generation_fingerprint_changes_without_containing_content() -> None:
    value = transcript(("secret transcript",))
    first = generation_fingerprint(
        value, provider="p", model="m", output_language="zh", prompt_version="v1"
    )
    second = generation_fingerprint(
        value, provider="p", model="m2", output_language="zh", prompt_version="v1"
    )
    assert first != second
    assert "secret" not in first


def test_chunking_covers_tail_and_only_overlaps_boundary_cue() -> None:
    value = transcript(("a" * 5, "b" * 5, "c" * 5, "d" * 5))
    chunks = chunk_transcript(value, max_characters=11)
    assert chunks[0].cues == value.cues[:2]
    assert chunks[1].cues[0] == chunks[0].cues[-1]
    assert chunks[-1].cues[-1] == value.cues[-1]
    with pytest.raises(ValueError, match="预算"):
        chunk_transcript(value, max_characters=0)


def test_import_bilibili_json_preserves_unicode_and_video_tail() -> None:
    raw = json.dumps(
        {
            "body": [
                {"from": 0, "to": 1.25, "content": "你好🌍"},
                {"from": 9, "to": 10, "content": "尾部"},
            ]
        },
        ensure_ascii=False,
    ).encode()
    value = import_bilibili_json(
        raw,
        bvid="BV1xx411c7mD",
        page=2,
        cid=9,
        title="标题",
        track_id=None,
        language="zh-CN",
        display_name="AI",
        kind="ai",
    )
    assert value.cues[0].text == "你好🌍"
    assert value.cues[-1].end_ms == 10000
    with pytest.raises(DomainError, match="结构"):
        import_bilibili_json(
            b"{}",
            bvid="x",
            page=1,
            cid=1,
            title="x",
            track_id=None,
            language="x",
            display_name="x",
            kind="ai",
        )
