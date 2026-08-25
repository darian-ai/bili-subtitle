from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from bili_study.domain import build_transcript, new_note
from bili_study.storage import (
    AppPaths,
    LibraryRegistry,
    StorageError,
    StudyRepository,
    library_database,
    publish_generated,
    publish_note,
    publish_reflection,
)


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


def test_library_registry_creates_layout_and_rejects_collisions(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / "config", tmp_path / "state")
    registry = LibraryRegistry(paths)
    library = registry.create("学习库", tmp_path / "vault")
    assert registry.get("学习库") == library
    assert (library.path / ".bili-study.json").exists()
    assert (library.path / "generated" / "videos").is_dir()
    assert (library.path / "notes").is_dir()
    with pytest.raises(StorageError, match="名称"):
        registry.create("学习库", tmp_path / "other")
    with pytest.raises(StorageError, match="已经注册"):
        registry.create("另一个", library.path)


def test_registry_rejects_foreign_nonempty_and_corrupt_config(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / "config", tmp_path / "state")
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "file.txt").write_text("x")
    with pytest.raises(StorageError, match="非空"):
        LibraryRegistry(paths).create("x", foreign)
    paths.config_dir.mkdir()
    (paths.config_dir / "libraries.json").write_text("{}")
    with pytest.raises(StorageError, match="损坏"):
        LibraryRegistry(paths).list()


def test_repository_roundtrip_cache_and_personal_note(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / "config", tmp_path / "state")
    library = LibraryRegistry(paths).create("main", tmp_path / "vault")
    repository = StudyRepository(library_database(paths, library))
    revision = transcript()
    repository.save_transcript(revision)
    assert repository.latest_transcript() == revision
    assert repository.get_transcript(revision.revision_id) == revision
    repository.cache_put("fingerprint", "guide", {"ok": True})
    assert repository.cache_get("fingerprint") == {"ok": True}

    note = new_note(
        revision_id=revision.revision_id, timestamp_ms=1234, note_type="question", body="为什么？"
    )
    target = publish_note(library, note)
    repository.save_note(note)
    assert repository.notes(revision.revision_id) == (note,)
    assert "为什么？" in target.read_text(encoding="utf-8")
    with pytest.raises(StorageError, match="存在"):
        publish_note(library, note)
    generated = publish_generated(library, "guide:1", "# guide\n")
    assert generated.name == "guide_1.md"
    reflection = publish_reflection(
        library,
        reflection_id="reflection-1",
        revision_id=revision.revision_id,
        question_id="q1",
        response="我的复述",
    )
    assert "owner: user" in reflection.read_text(encoding="utf-8")
    assert "我的复述" in reflection.read_text(encoding="utf-8")
    repository.save_reflection(
        "reflection-1", revision.revision_id, "q1", {"status": "pending", "response": "我的复述"}
    )
    repository.save_reflection(
        "reflection-1", revision.revision_id, "q1", {"status": "succeeded", "response": "我的复述"}
    )
    assert repository.reflections(revision.revision_id) == (
        {"status": "succeeded", "response": "我的复述"},
    )
    task_id = repository.start_task("guide", "start")
    assert repository.task_status(task_id) == ("running", None)
    repository.finish_task(task_id, "succeeded", None, "end")
    assert repository.task_status(task_id) == ("succeeded", None)
    with pytest.raises(StorageError, match="终态"):
        repository.finish_task(task_id, "unknown", None, "end")
    with pytest.raises(StorageError, match="任务不存在"):
        repository.task_status("missing")
    with pytest.raises(StorageError, match="任务不存在"):
        repository.finish_task("missing", "failed", "error", "end")
    with pytest.raises(StorageError, match="revision 不存在"):
        repository.get_transcript("missing")


def test_repository_migration_backup_and_corruption(tmp_path: Path) -> None:
    database = tmp_path / "old.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE old(value TEXT)")
        connection.execute("PRAGMA user_version = 0")
    StudyRepository(database)
    assert database.with_suffix(".sqlite3.bak").exists()

    version_two = tmp_path / "version-two.sqlite3"
    with sqlite3.connect(version_two) as connection:
        connection.execute(
            "CREATE TABLE api_jobs (job_id TEXT PRIMARY KEY, kind TEXT, status TEXT, "
            "request TEXT, result TEXT, error_code TEXT, created_at TEXT, updated_at TEXT)"
        )
        connection.execute("PRAGMA user_version = 2")
    StudyRepository(version_two)
    with sqlite3.connect(version_two) as connection:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(api_jobs)")}
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        practice_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'chapter_practices'"
        ).fetchone()
        assert version == 4 and {"progress", "retry_of"} <= columns and practice_table is not None

    corrupt = tmp_path / "broken.sqlite3"
    corrupt.write_bytes(b"not sqlite")
    with pytest.raises(StorageError, match="损坏"):
        StudyRepository(corrupt)


def test_repository_serializes_concurrent_writers(tmp_path: Path) -> None:
    repository = StudyRepository(tmp_path / "concurrent.sqlite3")
    first = transcript()
    second = transcript(("变化",))
    with ThreadPoolExecutor(max_workers=2) as pool:
        tuple(pool.map(repository.save_transcript, (first, second)))
    assert repository.get_transcript(first.revision_id) == first
    assert repository.get_transcript(second.revision_id) == second
