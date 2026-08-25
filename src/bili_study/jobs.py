"""A single-worker persistent queue used by the loopback API."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import Any

from bili_study.domain import DomainError, SubtitleTrackUnavailable, now_iso
from bili_study.provider import ProviderError
from bili_study.storage import StorageError, StudyRepository
from bili_subtitle.domain.errors import (
    AuthenticationRequired,
    MetadataError,
    NoSubtitles,
    SubtitleAccessDenied,
    SubtitleError,
    SubtitleNetworkError,
)

JobHandler = Callable[[dict[str, Any]], dict[str, Any]]


def stable_error_code(exc: BaseException) -> str:
    if isinstance(exc, AuthenticationRequired):
        return "bilibili_authentication_required"
    if isinstance(exc, NoSubtitles):
        return "no_subtitles"
    if isinstance(exc, SubtitleAccessDenied):
        return "subtitle_access_denied"
    if isinstance(exc, SubtitleNetworkError):
        return "bilibili_network_error"
    if isinstance(exc, ProviderError):
        return exc.code
    if isinstance(exc, SubtitleTrackUnavailable):
        return "subtitle_track_unavailable"
    if isinstance(exc, DomainError):
        return "evidence_validation"
    if isinstance(exc, (MetadataError, SubtitleError)):
        return "platform_error"
    if isinstance(exc, StorageError):
        return "storage_error"
    return "internal_error"


class PersistentJobWorker:
    """Execute durable records serially and expose only classified failures."""

    def __init__(self, repository: StudyRepository) -> None:
        self.repository = repository
        self._handlers: dict[str, JobHandler] = {}
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()

    def register(self, kind: str, handler: JobHandler) -> None:
        self._handlers[kind] = handler

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="bili-study-worker", daemon=True)
        self._thread.start()
        for job_id in self.repository.recover_jobs(now_iso()):
            self._queue.put(job_id)

    def stop(self) -> None:
        self._stopping.set()
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=5)

    def submit(self, kind: str, request: dict[str, Any]) -> str:
        if kind not in self._handlers:
            raise StorageError("API 任务类型无效。")
        job_id = self.repository.create_job(kind, request, now_iso())
        self._queue.put(job_id)
        return job_id

    def _run(self) -> None:
        while not self._stopping.is_set():
            job_id = self._queue.get()
            try:
                if job_id is None:
                    return
                record = self.repository.job(job_id)
                handler = self._handlers.get(str(record["kind"]))
                if handler is None or not self.repository.claim_job(job_id, now_iso()):
                    continue
                try:
                    result = handler(record["request"])
                except BaseException as exc:  # worker must preserve the next queued job
                    self.repository.complete_job(
                        job_id,
                        status="failed",
                        result=None,
                        error_code=stable_error_code(exc),
                        timestamp=now_iso(),
                    )
                else:
                    self.repository.complete_job(
                        job_id,
                        status="succeeded",
                        result=result,
                        error_code=None,
                        timestamp=now_iso(),
                    )
            finally:
                self._queue.task_done()
