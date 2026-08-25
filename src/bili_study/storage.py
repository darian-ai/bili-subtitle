"""Local-first library registry, SQLite state, and atomic content publication."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from bili_study.domain import (
    PersonalNote,
    StudyGuide,
    TranscriptRevision,
    to_json,
    transcript_from_dict,
)


class StorageError(RuntimeError):
    """Stable local storage failure without filesystem contents."""


@dataclass(frozen=True, slots=True)
class AppPaths:
    config_dir: Path
    state_dir: Path

    @classmethod
    def windows_default(cls) -> AppPaths:
        appdata = os.environ.get("APPDATA")
        local = os.environ.get("LOCALAPPDATA")
        if not appdata or not local:
            raise StorageError("无法确定 Windows 应用数据目录。")
        return cls(Path(appdata) / "bili-study", Path(local) / "bili-study")


@dataclass(frozen=True, slots=True)
class Library:
    library_id: str
    name: str
    path: Path


def atomic_write(path: Path, content: bytes, *, replace: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise StorageError("目标文件已经存在。")
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise StorageError("无法安全发布本地文件。") from exc


class LibraryRegistry:
    def __init__(self, paths: AppPaths) -> None:
        self._path = paths.config_dir / "libraries.json"

    def _read(self) -> list[dict[str, str]]:
        if not self._path.exists():
            return []
        try:
            raw = cast(object, json.loads(self._path.read_text(encoding="utf-8")))
            if not isinstance(raw, list):
                raise ValueError
            return [
                {str(key): str(value) for key, value in cast(dict[object, object], item).items()}
                for item in cast(list[object], raw)
                if isinstance(item, dict)
            ]
        except (OSError, ValueError, TypeError) as exc:
            raise StorageError("知识库注册信息损坏。") from exc

    def list(self) -> tuple[Library, ...]:
        try:
            return tuple(
                Library(str(item["id"]), str(item["name"]), Path(item["path"]).resolve())
                for item in self._read()
            )
        except (KeyError, OSError) as exc:
            raise StorageError("知识库注册信息损坏。") from exc

    def create(self, name: str, path: Path) -> Library:
        clean_name = name.strip()
        if not clean_name:
            raise StorageError("知识库名称不能为空。")
        resolved = path.resolve()
        libraries = self.list()
        if any(item.name.casefold() == clean_name.casefold() for item in libraries):
            raise StorageError("知识库名称已经存在。")
        if any(item.path == resolved for item in libraries):
            raise StorageError("该目录已经注册为知识库。")
        marker = resolved / ".bili-study.json"
        if resolved.exists() and any(resolved.iterdir()) and not marker.exists():
            raise StorageError("目标目录非空且不是 bili-study 知识库。")
        library = Library(str(uuid4()), clean_name, resolved)
        for child in ("generated/videos", "notes", "reviews"):
            (resolved / child).mkdir(parents=True, exist_ok=True)
        atomic_write(
            marker,
            json.dumps(
                {"schema_version": 1, "library_id": library.library_id, "name": clean_name},
                ensure_ascii=False,
                sort_keys=True,
            ).encode(),
        )
        payload = [
            {"id": item.library_id, "name": item.name, "path": str(item.path)}
            for item in (*libraries, library)
        ]
        atomic_write(self._path, json.dumps(payload, ensure_ascii=False, indent=2).encode())
        return library

    def get(self, name: str) -> Library:
        try:
            return next(item for item in self.list() if item.name.casefold() == name.casefold())
        except StopIteration as exc:
            raise StorageError("知识库不存在。") from exc


class StudyRepository:
    SCHEMA_VERSION = 4

    def __init__(self, database: Path) -> None:
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self.database, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        except sqlite3.Error as exc:
            raise StorageError("无法打开学习数据库。") from exc
        finally:
            if connection is not None:
                connection.close()

    def _migrate(self) -> None:
        existed = self.database.exists() and self.database.stat().st_size > 0
        backup = self.database.with_suffix(".sqlite3.bak")
        version = 0
        if existed:
            try:
                with sqlite3.connect(self.database) as check:
                    check.execute("PRAGMA quick_check").fetchone()
                    version = int(check.execute("PRAGMA user_version").fetchone()[0])
            except sqlite3.Error as exc:
                raise StorageError("学习数据库损坏。") from exc
            if version > self.SCHEMA_VERSION:
                raise StorageError("学习数据库版本高于当前程序。")
            if version < self.SCHEMA_VERSION:
                shutil.copy2(self.database, backup)
        try:
            with self.connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS transcripts (
                        revision_id TEXT PRIMARY KEY,
                        content_hash TEXT NOT NULL,
                        payload TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS guides (
                        guide_id TEXT PRIMARY KEY, revision_id TEXT NOT NULL,
                        fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
                        FOREIGN KEY(revision_id) REFERENCES transcripts(revision_id)
                    );
                    CREATE UNIQUE INDEX IF NOT EXISTS guide_fingerprint ON guides(fingerprint);
                    CREATE TABLE IF NOT EXISTS cache (
                        fingerprint TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
                        error_code TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS notes (
                        note_id TEXT PRIMARY KEY, revision_id TEXT NOT NULL, payload TEXT NOT NULL,
                        FOREIGN KEY(revision_id) REFERENCES transcripts(revision_id)
                    );
                    CREATE TABLE IF NOT EXISTS api_jobs (
                        job_id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
                        request TEXT NOT NULL, result TEXT, error_code TEXT,
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        progress TEXT, retry_of TEXT,
                        FOREIGN KEY(retry_of) REFERENCES api_jobs(job_id)
                    );
                    CREATE TABLE IF NOT EXISTS chapter_details (
                        guide_id TEXT NOT NULL, chapter_id TEXT NOT NULL, payload TEXT NOT NULL,
                        PRIMARY KEY(guide_id, chapter_id),
                        FOREIGN KEY(guide_id) REFERENCES guides(guide_id)
                    );
                    CREATE TABLE IF NOT EXISTS chapter_practices (
                        guide_id TEXT NOT NULL, chapter_id TEXT NOT NULL, payload TEXT NOT NULL,
                        PRIMARY KEY(guide_id, chapter_id),
                        FOREIGN KEY(guide_id) REFERENCES guides(guide_id)
                    );
                    CREATE TABLE IF NOT EXISTS reflections (
                        reflection_id TEXT PRIMARY KEY, revision_id TEXT NOT NULL,
                        question_id TEXT NOT NULL, payload TEXT NOT NULL,
                        FOREIGN KEY(revision_id) REFERENCES transcripts(revision_id)
                    );
                    """
                )
                columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(api_jobs)")}
                if "progress" not in columns:
                    connection.execute("ALTER TABLE api_jobs ADD COLUMN progress TEXT")
                if "retry_of" not in columns:
                    connection.execute("ALTER TABLE api_jobs ADD COLUMN retry_of TEXT")
                connection.execute("PRAGMA user_version = 4")
        except (sqlite3.Error, StorageError) as exc:
            if backup.exists():
                shutil.copy2(backup, self.database)
            raise StorageError("学习数据库 migration 失败。") from exc

    def save_transcript(self, transcript: TranscriptRevision) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO transcripts VALUES (?, ?, ?)",
                (transcript.revision_id, transcript.content_sha256, to_json(transcript)),
            )

    def get_transcript(self, revision_id: str) -> TranscriptRevision:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM transcripts WHERE revision_id = ?", (revision_id,)
            ).fetchone()
        if row is None:
            raise StorageError("Transcript revision 不存在。")
        return transcript_from_dict(json.loads(str(row["payload"])))

    def latest_transcript(self) -> TranscriptRevision:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM transcripts ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        if row is None:
            raise StorageError("知识库中没有 Transcript。")
        return transcript_from_dict(json.loads(str(row["payload"])))

    def latest_transcript_for_video(self, bvid: str, page: int) -> TranscriptRevision | None:
        """Return the newest locally saved revision for exactly one canonical BV/P."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM transcripts ORDER BY rowid DESC"
            ).fetchall()
        for row in rows:
            transcript = transcript_from_dict(json.loads(str(row["payload"])))
            if transcript.bvid == bvid and transcript.page == page:
                return transcript
        return None

    def cache_get(self, fingerprint: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM cache WHERE fingerprint = ?", (fingerprint,)
            ).fetchone()
        return json.loads(str(row["payload"])) if row else None

    def cache_put(self, fingerprint: str, kind: str, payload: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO cache VALUES (?, ?, ?)",
                (fingerprint, kind, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            )

    def start_task(self, kind: str, timestamp: str) -> str:
        task_id = str(uuid4())
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO tasks VALUES (?, ?, 'running', NULL, ?, ?)",
                (task_id, kind, timestamp, timestamp),
            )
        return task_id

    def finish_task(
        self, task_id: str, status: str, error_code: str | None, timestamp: str
    ) -> None:
        if status not in {"succeeded", "failed"}:
            raise StorageError("任务终态无效。")
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE tasks SET status = ?, error_code = ?, updated_at = ? WHERE task_id = ?",
                (status, error_code, timestamp, task_id),
            )
            if cursor.rowcount != 1:
                raise StorageError("任务不存在。")

    def task_status(self, task_id: str) -> tuple[str, str | None]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT status, error_code FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise StorageError("任务不存在。")
        return str(row["status"]), str(row["error_code"]) if row["error_code"] is not None else None

    def save_guide(self, guide: StudyGuide, payload: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO guides VALUES (?, ?, ?, ?)",
                (
                    guide.guide_id,
                    guide.revision_id,
                    guide.fingerprint,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )

    def guide_payload(self, guide_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM guides WHERE guide_id = ?", (guide_id,)
            ).fetchone()
        if row is None:
            raise StorageError("学习指南不存在。")
        return json.loads(str(row["payload"]))

    def latest_guide_for_video(self, bvid: str, page: int) -> dict[str, Any] | None:
        """Return the newest guide for a video page without making a model request."""
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT guides.payload AS guide_payload, transcripts.payload AS transcript_payload
                   FROM guides JOIN transcripts USING (revision_id)
                   ORDER BY guides.rowid DESC"""
            ).fetchall()
        for row in rows:
            transcript = json.loads(str(row["transcript_payload"]))
            if transcript.get("bvid") == bvid and int(transcript.get("page", 0)) == page:
                return json.loads(str(row["guide_payload"]))
        return None

    def latest_guide_for_revision(self, revision_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM guides WHERE revision_id = ? ORDER BY rowid DESC LIMIT 1",
                (revision_id,),
            ).fetchone()
        return json.loads(str(row["payload"])) if row is not None else None

    def save_note(self, note: PersonalNote) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO notes VALUES (?, ?, ?)",
                (note.note_id, note.revision_id, to_json(note)),
            )

    def notes(self, revision_id: str) -> tuple[PersonalNote, ...]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM notes WHERE revision_id = ? ORDER BY rowid", (revision_id,)
            ).fetchall()
        return tuple(PersonalNote(**json.loads(str(row["payload"]))) for row in rows)

    def create_job(
        self,
        kind: str,
        request: dict[str, Any],
        timestamp: str,
        *,
        retry_of: str | None = None,
    ) -> str:
        job_id = str(uuid4())
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO api_jobs "
                "(job_id, kind, status, request, result, error_code, "
                "created_at, updated_at, progress, retry_of) "
                "VALUES (?, ?, 'queued', ?, NULL, NULL, ?, ?, ?, ?)",
                (
                    job_id,
                    kind,
                    json.dumps(request, ensure_ascii=False, sort_keys=True),
                    timestamp,
                    timestamp,
                    json.dumps({"phase": "queued", "percent": 0}),
                    retry_of,
                ),
            )
        return job_id

    def claim_job(self, job_id: str, timestamp: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE api_jobs SET status = 'running', updated_at = ?, progress = ? "
                "WHERE job_id = ? AND status = 'queued'",
                (timestamp, json.dumps({"phase": "starting", "percent": 1}), job_id),
            )
        return cursor.rowcount == 1

    def update_job_progress(self, job_id: str, phase: str, percent: int, timestamp: str) -> None:
        if not phase or not 0 <= percent <= 99:
            raise StorageError("API 任务进度无效。")
        with self.connect() as connection:
            row = connection.execute(
                "SELECT progress FROM api_jobs WHERE job_id = ? AND status = 'running'",
                (job_id,),
            ).fetchone()
            if row is None:
                raise StorageError("API 任务状态转换无效。")
            current = json.loads(str(row["progress"])) if row["progress"] else {"percent": 0}
            if percent < int(current.get("percent", 0)):
                raise StorageError("API 任务进度不得倒退。")
            connection.execute(
                "UPDATE api_jobs SET progress = ?, updated_at = ? WHERE job_id = ?",
                (json.dumps({"phase": phase, "percent": percent}), timestamp, job_id),
            )

    def complete_job(
        self,
        job_id: str,
        *,
        status: str,
        result: dict[str, Any] | None,
        error_code: str | None,
        timestamp: str,
    ) -> None:
        if status not in {"succeeded", "failed", "interrupted", "cancelled"}:
            raise StorageError("API 任务终态无效。")
        payload = json.dumps(result, ensure_ascii=False, sort_keys=True) if result else None
        with self.connect() as connection:
            allowed_status = (
                "('running', 'cancel_requested')" if status == "cancelled" else "('running')"
            )
            phase = {
                "succeeded": "completed",
                "cancelled": "cancelled",
                "interrupted": "interrupted",
                "failed": "failed",
            }[status]
            cursor = connection.execute(
                "UPDATE api_jobs SET status = ?, result = ?, error_code = ?, updated_at = ?, "
                "progress = ? "
                f"WHERE job_id = ? AND status IN {allowed_status}",
                (
                    status,
                    payload,
                    error_code,
                    timestamp,
                    json.dumps({"phase": phase, "percent": 100}),
                    job_id,
                ),
            )
            if cursor.rowcount == 0 and status != "cancelled":
                cursor = connection.execute(
                    "UPDATE api_jobs SET status = 'cancelled', result = NULL, error_code = NULL, "
                    "updated_at = ?, progress = ? WHERE job_id = ? AND status = 'cancel_requested'",
                    (
                        timestamp,
                        json.dumps({"phase": "cancelled", "percent": 100}),
                        job_id,
                    ),
                )
        if cursor.rowcount != 1:
            raise StorageError("API 任务状态转换无效。")

    def job(self, job_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM api_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise StorageError("API 任务不存在。")
        return {
            "job_id": str(row["job_id"]),
            "kind": str(row["kind"]),
            "status": str(row["status"]),
            "request": json.loads(str(row["request"])),
            "result": json.loads(str(row["result"])) if row["result"] else None,
            "error_code": str(row["error_code"]) if row["error_code"] else None,
            "progress": json.loads(str(row["progress"])) if row["progress"] else None,
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "retry_of": str(row["retry_of"]) if row["retry_of"] else None,
        }

    def cancel_job(self, job_id: str, timestamp: str) -> str:
        """Request cancellation atomically and return the resulting status."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT status FROM api_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise StorageError("API 任务不存在。")
            current = str(row["status"])
            if current == "queued":
                resulting = "cancelled"
                phase = "cancelled"
            elif current == "running":
                resulting = "cancel_requested"
                phase = "cancel_requested"
            elif current in {"cancel_requested", "cancelled"}:
                return current
            else:
                return current
            connection.execute(
                "UPDATE api_jobs SET status = ?, updated_at = ?, progress = ? WHERE job_id = ?",
                (
                    resulting,
                    timestamp,
                    json.dumps(
                        {"phase": phase, "percent": 100 if resulting == "cancelled" else 99}
                    ),
                    job_id,
                ),
            )
        return resulting

    def retry_job(self, job_id: str, timestamp: str) -> tuple[str, str, dict[str, Any]] | None:
        """Return the immutable request for retryable terminal work."""
        record = self.job(job_id)
        if record["status"] not in {"failed", "interrupted", "cancelled"}:
            return None
        return str(record["kind"]), job_id, dict(record["request"])

    def recover_jobs(self, timestamp: str) -> tuple[str, ...]:
        """Resume unstarted work, but never replay an in-flight billable request."""
        with self.connect() as connection:
            connection.execute(
                "UPDATE api_jobs SET status = 'interrupted', error_code = 'service_restarted', "
                "updated_at = ?, progress = ? WHERE status IN ('running', 'cancel_requested')",
                (timestamp, json.dumps({"phase": "interrupted", "percent": 100})),
            )
            rows = connection.execute(
                "SELECT job_id FROM api_jobs WHERE status = 'queued' ORDER BY rowid"
            ).fetchall()
        return tuple(str(row["job_id"]) for row in rows)

    def save_chapter_detail(self, guide_id: str, chapter_id: str, payload: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO chapter_details VALUES (?, ?, ?)",
                (guide_id, chapter_id, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            )

    def chapter_details(self, guide_id: str) -> dict[str, dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT chapter_id, payload FROM chapter_details WHERE guide_id = ?", (guide_id,)
            ).fetchall()
        return {str(row["chapter_id"]): json.loads(str(row["payload"])) for row in rows}

    def save_chapter_practice(
        self, guide_id: str, chapter_id: str, payload: dict[str, Any]
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO chapter_practices VALUES (?, ?, ?)",
                (guide_id, chapter_id, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            )

    def chapter_practices(self, guide_id: str) -> dict[str, dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT chapter_id, payload FROM chapter_practices WHERE guide_id = ?",
                (guide_id,),
            ).fetchall()
        return {str(row["chapter_id"]): json.loads(str(row["payload"])) for row in rows}

    def save_reflection(
        self, reflection_id: str, revision_id: str, question_id: str, payload: dict[str, Any]
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO reflections VALUES (?, ?, ?, ?)",
                (
                    reflection_id,
                    revision_id,
                    question_id,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )

    def reflections(self, revision_id: str) -> tuple[dict[str, Any], ...]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM reflections WHERE revision_id = ? ORDER BY rowid",
                (revision_id,),
            ).fetchall()
        return tuple(json.loads(str(row["payload"])) for row in rows)


def library_database(paths: AppPaths, library: Library) -> Path:
    return paths.state_dir / "libraries" / library.library_id / "study.sqlite3"


def publish_note(library: Library, note: PersonalNote) -> Path:
    target = library.path / "notes" / f"{note.note_id}.md"
    content = (
        "---\n"
        f"schema_version: 1\nnote_id: {note.note_id}\nrevision_id: {note.revision_id}\n"
        f"timestamp_ms: {note.timestamp_ms}\ntype: {note.note_type}\n"
        f"created_at: {note.created_at}\n"
        "---\n\n"
        f"{note.body.rstrip()}\n"
    )
    atomic_write(target, content.encode("utf-8"), replace=False)
    return target


def publish_generated(library: Library, name: str, content: str) -> Path:
    safe = "".join(
        character if character.isalnum() or character in "-_" else "_" for character in name
    )
    if not safe:
        raise StorageError("生成文件名无效。")
    target = library.path / "generated" / "videos" / f"{safe}.md"
    atomic_write(target, content.encode("utf-8"))
    return target


def publish_reflection(
    library: Library,
    *,
    reflection_id: str,
    revision_id: str,
    question_id: str,
    response: str,
) -> Path:
    """Publish irreplaceable user text separately from rebuildable AI feedback."""
    target = library.path / "reviews" / f"{reflection_id}.md"
    content = (
        "---\n"
        f"schema_version: 1\nreflection_id: {reflection_id}\nrevision_id: {revision_id}\n"
        f"question_id: {question_id}\nowner: user\n"
        "---\n\n"
        f"{response.rstrip()}\n"
    )
    atomic_write(target, content.encode("utf-8"), replace=False)
    return target
