from __future__ import annotations

import json
from pathlib import Path

import pytest

from bili_study.domain import DomainError, build_transcript
from bili_study.provider import ChatResult, ChatUsage, ProviderConfig, ProviderStructureError
from bili_study.services import GuideGenerator, render_guide_markdown
from bili_study.storage import StudyRepository


def transcript():
    return build_transcript(
        bvid="BV1xx411c7mD",
        page=1,
        cid=123,
        title="课程",
        track_id=7,
        language="zh-CN",
        display_name="中文",
        kind="ai",
        cue_values=((0, 900, "一"), (1000, 1900, "二"), (2000, 2900, "三")),
        created_at="2026-08-22T00:00:00+00:00",
    )


def guide_payload(end: str = "c000003") -> dict[str, object]:
    return {
        "learning_objectives": ["理解完整内容"],
        "chapters": [
            {
                "chapter_id": "ch001",
                "title": "完整章节",
                "summary": "只依据字幕。",
                "evidence": {"start_cue_id": "c000001", "end_cue_id": end},
                "questions": [
                    {
                        "question_id": "q1",
                        "text": "核心是什么？",
                        "evidence": {"start_cue_id": "c000001", "end_cue_id": end},
                    }
                ],
            }
        ],
    }


class FakeChat:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str]] = []

    def complete(self, *, system: str, user: str) -> ChatResult:
        self.requests.append((system, user))
        return ChatResult(self.responses.pop(0), ChatUsage(2, 3, 5))


def test_map_reduce_validates_evidence_caches_and_renders(tmp_path: Path) -> None:
    revision = transcript()
    repository = StudyRepository(tmp_path / "study.sqlite3")
    repository.save_transcript(revision)
    chat = FakeChat([json.dumps({"chapters": []}), json.dumps(guide_payload())])
    config = ProviderConfig("p", "https://model.example/v1", "m", context_budget=1000)
    generator = GuideGenerator(chat, repository)
    result = generator.generate(revision, config)
    assert result.metrics.requests == 2
    assert result.metrics.total_tokens == 10
    assert result.guide.chapters[0].evidence.resolve(revision) == revision.cues
    assert "DATA" in chat.requests[0][0]
    assert revision.cues[-1].cue_id in chat.requests[0][1]
    markdown = render_guide_markdown(result.guide, revision)
    assert "rebuildable: true" in markdown and "完整章节" in markdown

    cached = generator.generate(revision, config)
    assert cached.metrics.cache_hit
    assert len(chat.requests) == 2
    assert cached.guide.guide_id == result.guide.guide_id


def test_generation_allows_one_json_repair(tmp_path: Path) -> None:
    revision = transcript()
    repository = StudyRepository(tmp_path / "study.sqlite3")
    repository.save_transcript(revision)
    chat = FakeChat(["not-json", json.dumps({"chapters": []}), json.dumps(guide_payload())])
    result = GuideGenerator(chat, repository).generate(
        revision, ProviderConfig("p", "https://model.example/v1", "m", context_budget=1000)
    )
    assert result.metrics.requests == 3
    assert "修复" in chat.requests[1][1]


def test_generation_rejects_uncovered_or_invalid_evidence(tmp_path: Path) -> None:
    revision = transcript()
    repository = StudyRepository(tmp_path / "study.sqlite3")
    repository.save_transcript(revision)
    chat = FakeChat([json.dumps({"chapters": []}), json.dumps(guide_payload("c000002"))])
    with pytest.raises(DomainError, match="完整"):
        GuideGenerator(chat, repository).generate(
            revision, ProviderConfig("p", "https://model.example/v1", "m", context_budget=1000)
        )


def test_repair_failure_is_stable(tmp_path: Path) -> None:
    revision = transcript()
    repository = StudyRepository(tmp_path / "study.sqlite3")
    repository.save_transcript(revision)
    chat = FakeChat(["bad", "still-bad"])
    with pytest.raises(ProviderStructureError):
        GuideGenerator(chat, repository).generate(
            revision, ProviderConfig("p", "https://model.example/v1", "m", context_budget=1000)
        )


def test_chapter_detail_is_on_demand_and_evidence_checked(tmp_path: Path) -> None:
    revision = transcript()
    repository = StudyRepository(tmp_path / "study.sqlite3")
    repository.save_transcript(revision)
    guide_chat = FakeChat([json.dumps({"chapters": []}), json.dumps(guide_payload())])
    generator = GuideGenerator(guide_chat, repository)
    guide = generator.generate(
        revision, ProviderConfig("p", "https://model.example/v1", "m", context_budget=1000)
    ).guide
    detail_chat = FakeChat(
        [
            json.dumps(
                {
                    "summary": "详情",
                    "key_points": [],
                    "terms": [],
                    "easy_to_miss": [],
                    "evidence": {"start_cue_id": "c000001", "end_cue_id": "c000003"},
                }
            )
        ]
    )
    detail, metrics = GuideGenerator(detail_chat, repository).generate_chapter_detail(
        revision, guide.chapters[0]
    )
    assert detail["summary"] == "详情"
    assert metrics.requests == 1
