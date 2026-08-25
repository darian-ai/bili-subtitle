"""Versioned loopback API for the Chrome/Edge learning side panel."""
# pyright: reportUnusedFunction=false

from __future__ import annotations

import threading
import time
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from bili_study.domain import DomainError, SubtitleTrackUnavailable, build_transcript, new_note
from bili_study.jobs import PersistentJobWorker
from bili_study.provider import OpenAIChatAdapter, ProviderConfigStore, ProviderSecretStore
from bili_study.security import PairingStore, SecurityError, TokenRegistry, valid_extension_origin
from bili_study.services import GuideGenerator, guide_from_payload, render_guide_markdown
from bili_study.storage import (
    AppPaths,
    Library,
    LibraryRegistry,
    StorageError,
    StudyRepository,
    library_database,
    publish_generated,
    publish_note,
    publish_reflection,
)
from bili_subtitle.application.metadata import resolve_selection
from bili_subtitle.domain.auth import CredentialState
from bili_subtitle.domain.errors import AuthenticationRequired, NoSubtitles
from bili_subtitle.infrastructure.auth import BilibiliAuthAdapter
from bili_subtitle.infrastructure.bilibili import BilibiliMetadataAdapter, create_http_client
from bili_subtitle.infrastructure.credentials import KeyringCredentialStore
from bili_subtitle.infrastructure.subtitles import BilibiliSubtitleAdapter

API_VERSION = "1.0.0"
MAX_REQUEST_BYTES = 1_048_576
RATE_LIMIT_PER_MINUTE = 120


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PairRequest(StrictModel):
    code: str = Field(min_length=5, max_length=32)


class PairResponse(StrictModel):
    token: str
    expires_at: str


class VideoInspectRequest(StrictModel):
    library: str = Field(min_length=1, max_length=100)
    bvid: str = Field(pattern=r"^BV[A-Za-z0-9]{10}$")
    page: int = Field(ge=1, le=10_000)


class SourceRequest(StrictModel):
    library: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=100)
    bvid: str = Field(pattern=r"^BV[A-Za-z0-9]{10}$")
    page: int = Field(ge=1, le=10_000)
    cid: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=500)
    # Bilibili track IDs can exceed JavaScript's MAX_SAFE_INTEGER. Keep them as
    # decimal strings at the HTTP boundary and convert only inside Python.
    track_id: str = Field(pattern=r"^[1-9][0-9]*$", max_length=32)
    regenerate: bool = False


class ChapterDetailRequest(StrictModel):
    library: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=100)


class NoteRequest(StrictModel):
    library: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=100)
    timestamp_ms: int = Field(ge=0)
    note_type: Literal["note", "question", "insight"] = "note"
    body: str = Field(min_length=1, max_length=100_000)


class ReflectionRequest(StrictModel):
    library: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=100)
    guide_id: str = Field(min_length=1, max_length=100)
    question_id: str = Field(min_length=1, max_length=100)
    response: str = Field(min_length=1, max_length=100_000)


class JobAccepted(StrictModel):
    job_id: str
    status: Literal["queued"] = "queued"


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def _library(paths: AppPaths, name: str) -> tuple[Library, StudyRepository]:
    library = LibraryRegistry(paths).get(name)
    return library, StudyRepository(library_database(paths, library))


def _extension_origin(request: Request) -> str:
    browser_origin = request.headers.get("origin", "")
    declared_origin = request.headers.get("x-bili-study-origin", "")
    if browser_origin and declared_origin and browser_origin != declared_origin:
        raise SecurityError("origin_mismatch", "浏览器 Origin 与扩展声明不一致。")
    origin = browser_origin or declared_origin
    if not valid_extension_origin(origin):
        raise SecurityError("origin_not_allowed", "只允许浏览器扩展 Origin。")
    return origin


_bearer = HTTPBearer(auto_error=False)


def _authenticated(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    origin = _extension_origin(request)
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise SecurityError("authentication_required", "需要 Bearer token。")
    request.app.state.tokens.authenticate(credentials.credentials, origin)
    return origin


Auth = Annotated[str, Depends(_authenticated)]


def _platform_client() -> tuple[Any, Any]:
    credential = KeyringCredentialStore().read()
    if credential.state is not CredentialState.FOUND or credential.credential is None:
        raise AuthenticationRequired("需要先通过 bili-study auth login 登录。")
    client = create_http_client()
    BilibiliAuthAdapter(client).apply(credential.credential)
    return client, credential


def _inspect_job(_paths: AppPaths, raw: dict[str, Any]) -> dict[str, Any]:
    del _paths
    client, _ = _platform_client()
    with client:
        selection = resolve_selection(
            str(raw["bvid"]),
            page=int(raw["page"]),
            all_pages=False,
            metadata=BilibiliMetadataAdapter(client),
        )
        page = selection.pages[0]
        adapter = BilibiliSubtitleAdapter(client)
        try:
            tracks = adapter.discover(bvid=selection.video.bvid, cid=page.cid)
        except NoSubtitles:
            tracks = ()
        finally:
            adapter.discard_pending(bvid=selection.video.bvid, cid=page.cid)
    return {
        "schema_version": 1,
        "source_id": f"{selection.video.bvid}:p{page.number}",
        "bvid": selection.video.bvid,
        "page": page.number,
        "cid": page.cid,
        "title": selection.video.title,
        "page_title": page.title,
        "subtitle_status": "available" if tracks else "no_subtitles",
        "tracks": [
            {
                "track_id": str(track.track_id),
                "language": track.language,
                "display_name": track.display_name,
                "kind": track.kind.value,
            }
            for track in tracks
        ],
    }


def _download_transcript(raw: dict[str, Any]):
    client, _ = _platform_client()
    with client:
        adapter = BilibiliSubtitleAdapter(client)
        tracks = adapter.discover(bvid=str(raw["bvid"]), cid=int(raw["cid"]))
        try:
            selected = next(track for track in tracks if track.track_id == int(raw["track_id"]))
        except StopIteration as exc:
            raise SubtitleTrackUnavailable("选定字幕轨道已不可用，请重新检查视频。") from exc
        body = adapter.download_selected(
            bvid=str(raw["bvid"]), cid=int(raw["cid"]), selected=selected
        )
    cue_values = tuple(
        (int(cue.start * 1000), max(int(cue.end * 1000), int(cue.start * 1000) + 1), cue.text)
        for cue in body.cues
    )
    return build_transcript(
        bvid=str(raw["bvid"]),
        page=int(raw["page"]),
        cid=int(raw["cid"]),
        title=str(raw["title"]),
        track_id=selected.track_id,
        language=selected.language,
        display_name=selected.display_name,
        kind=selected.kind.value,
        cue_values=cue_values,
    )


def _guide_job(paths: AppPaths, raw: dict[str, Any]) -> dict[str, Any]:
    library, repository = _library(paths, str(raw["library"]))
    transcript = _download_transcript(raw)
    repository.save_transcript(transcript)
    config = ProviderConfigStore(paths).get(str(raw["provider"]))
    with OpenAIChatAdapter(config, ProviderSecretStore().get(config.name)) as chat:
        result = GuideGenerator(chat, repository).generate(
            transcript, config, regenerate=bool(raw.get("regenerate", False))
        )
    publish_generated(
        library, result.guide.guide_id, render_guide_markdown(result.guide, transcript)
    )
    return {
        "guide_id": result.guide.guide_id,
        "source_id": transcript.revision_id,
        "cache_hit": result.metrics.cache_hit,
    }


def _detail_job(paths: AppPaths, raw: dict[str, Any]) -> dict[str, Any]:
    _, repository = _library(paths, str(raw["library"]))
    payload = repository.guide_payload(str(raw["guide_id"]))
    transcript = repository.get_transcript(str(payload["revision_id"]))
    guide = guide_from_payload(
        payload, transcript, str(payload["fingerprint"]), str(payload["output_language"])
    )
    try:
        chapter = next(c for c in guide.chapters if c.chapter_id == str(raw["chapter_id"]))
    except StopIteration as exc:
        raise DomainError("章节不存在。") from exc
    config = ProviderConfigStore(paths).get(str(raw["provider"]))
    with OpenAIChatAdapter(config, ProviderSecretStore().get(config.name)) as chat:
        detail, _ = GuideGenerator(chat, repository).generate_chapter_detail(transcript, chapter)
    repository.save_chapter_detail(guide.guide_id, chapter.chapter_id, detail)
    return {"guide_id": guide.guide_id, "chapter_id": chapter.chapter_id, "detail": detail}


def _reflection_job(paths: AppPaths, raw: dict[str, Any]) -> dict[str, Any]:
    library, repository = _library(paths, str(raw["library"]))
    payload = repository.guide_payload(str(raw["guide_id"]))
    transcript = repository.get_transcript(str(payload["revision_id"]))
    guide = guide_from_payload(
        payload, transcript, str(payload["fingerprint"]), str(payload["output_language"])
    )
    questions = (question for chapter in guide.chapters for question in chapter.questions)
    try:
        question = next(q for q in questions if q.question_id == str(raw["question_id"]))
    except StopIteration as exc:
        raise DomainError("引导问题不存在。") from exc
    reflection_id = str(uuid4())
    publish_reflection(
        library,
        reflection_id=reflection_id,
        revision_id=transcript.revision_id,
        question_id=question.question_id,
        response=str(raw["response"]),
    )
    config = ProviderConfigStore(paths).get(str(raw["provider"]))
    with OpenAIChatAdapter(config, ProviderSecretStore().get(config.name)) as chat:
        feedback, _ = GuideGenerator(chat, repository).generate_reflection(
            transcript, question, str(raw["response"])
        )
    result = {
        "reflection_id": reflection_id,
        "guide_id": guide.guide_id,
        "question_id": question.question_id,
        "feedback": feedback,
    }
    repository.save_reflection(reflection_id, transcript.revision_id, question.question_id, result)
    return result


def create_app(
    *,
    paths: AppPaths | None = None,
    pairing: PairingStore | None = None,
    tokens: TokenRegistry | None = None,
    worker: PersistentJobWorker | None = None,
    allowed_hosts: set[str] | None = None,
) -> FastAPI:
    app_paths = paths or AppPaths.windows_default()
    job_repository = (
        worker.repository
        if worker is not None
        else StudyRepository(app_paths.state_dir / "api.sqlite3")
    )
    app_worker = worker or PersistentJobWorker(job_repository)
    app_worker.register("video_inspect", lambda raw: _inspect_job(app_paths, raw))
    app_worker.register("study_guide", lambda raw: _guide_job(app_paths, raw))
    app_worker.register("chapter_detail", lambda raw: _detail_job(app_paths, raw))
    app_worker.register("reflection", lambda raw: _reflection_job(app_paths, raw))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        app_worker.start()
        try:
            yield
        finally:
            app_worker.stop()

    app = FastAPI(
        title="bili-study Local API",
        version=API_VERSION,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.paths = app_paths
    app.state.pairing = pairing or PairingStore(app_paths)
    app.state.tokens = tokens or TokenRegistry()
    app.state.worker = app_worker
    app.state.job_repository = job_repository
    app.state.allowed_hosts = allowed_hosts or {"127.0.0.1", "localhost", "testserver"}
    app.state.rate_lock = threading.Lock()
    app.state.rate_counts = {}
    app.state.concurrent = threading.BoundedSemaphore(8)

    @app.middleware("http")
    async def _security_boundary(request: Request, call_next: Callable[[Request], Any]) -> Response:
        host = request.headers.get("host", "").split(":", 1)[0].lower()
        if host not in app.state.allowed_hosts:
            return _error(400, "host_not_allowed", "Host 不在 loopback 允许列表中。")
        origin = request.headers.get("origin", "")
        if origin:
            bucket = int(time.monotonic() // 60)
            key = (origin, bucket)
            with app.state.rate_lock:
                app.state.rate_counts = {
                    item: count
                    for item, count in app.state.rate_counts.items()
                    if item[1] == bucket
                }
                count = int(app.state.rate_counts.get(key, 0)) + 1
                app.state.rate_counts[key] = count
            if count > RATE_LIMIT_PER_MINUTE:
                return _error(429, "rate_limit_exceeded", "本地 API 请求过于频繁。")
        if request.method == "OPTIONS":
            if not valid_extension_origin(origin):
                return _error(403, "origin_not_allowed", "Origin 不受支持。")
            response: Response = Response(status_code=204)
        else:
            content_length = request.headers.get("content-length")
            try:
                too_large = bool(content_length) and int(content_length or "0") > MAX_REQUEST_BYTES
            except ValueError:
                return _error(400, "invalid_content_length", "Content-Length 无效。")
            if too_large:
                return _error(413, "request_too_large", "请求正文超过限制。")
            if request.method in {"POST", "PUT", "PATCH"}:
                body = await request.body()
                if len(body) > MAX_REQUEST_BYTES:
                    return _error(413, "request_too_large", "请求正文超过限制。")
            if request.method in {"POST", "PUT", "PATCH"}:
                content_type = request.headers.get("content-type", "").split(";", 1)[0]
                if content_type != "application/json":
                    return _error(415, "unsupported_media_type", "请求必须使用 application/json。")
            if not app.state.concurrent.acquire(blocking=False):
                return _error(429, "concurrency_limit_exceeded", "本地 API 并发请求过多。")
            try:
                response = await call_next(request)
            finally:
                app.state.concurrent.release()
        if valid_extension_origin(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, X-Bili-Study-Origin"
            )
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    @app.exception_handler(SecurityError)
    async def _security_exception(_: Request, exc: SecurityError) -> JSONResponse:
        authentication_codes = {
            "authentication_required",
            "authentication_failed",
            "token_expired",
        }
        code = 401 if exc.code in authentication_codes else 403
        return _error(code, exc.code, str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation_exception(_: Request, __: RequestValidationError) -> JSONResponse:
        return _error(422, "validation_error", "请求字段不符合 API schema。")

    @app.exception_handler(StorageError)
    async def _storage_exception(_: Request, exc: StorageError) -> JSONResponse:
        code = "not_found" if "不存在" in str(exc) else "storage_error"
        return _error(404 if code == "not_found" else 409, code, str(exc))

    @app.exception_handler(Exception)
    async def _unknown_exception(_: Request, __: Exception) -> JSONResponse:
        return _error(500, "internal_error", "本地服务发生未知错误。")

    @app.get("/api/v1/health", operation_id="health")
    def _health() -> dict[str, str]:
        return {"status": "ok", "api_version": API_VERSION}

    @app.post("/api/v1/pair", response_model=PairResponse, operation_id="pair")
    def _pair(body: PairRequest, request: Request) -> PairResponse:
        origin = _extension_origin(request)
        request.app.state.pairing.consume(body.code)
        token, expires = request.app.state.tokens.issue(origin)
        return PairResponse(token=token, expires_at=expires.isoformat())

    @app.get("/api/v1/libraries", operation_id="listLibraries")
    def _libraries(_: Auth) -> dict[str, object]:
        values = LibraryRegistry(app_paths).list()
        return {
            "schema_version": 1,
            "libraries": [{"id": item.library_id, "name": item.name} for item in values],
        }

    @app.post(
        "/api/v1/videos/inspect",
        response_model=JobAccepted,
        status_code=status.HTTP_202_ACCEPTED,
        operation_id="inspectVideo",
    )
    def _inspect_video(body: VideoInspectRequest, _: Auth) -> JobAccepted:
        LibraryRegistry(app_paths).get(body.library)
        return JobAccepted(job_id=app_worker.submit("video_inspect", body.model_dump()))

    @app.post(
        "/api/v1/study-guides",
        response_model=JobAccepted,
        status_code=status.HTTP_202_ACCEPTED,
        operation_id="createStudyGuide",
    )
    def _create_study_guide(body: SourceRequest, _: Auth) -> JobAccepted:
        LibraryRegistry(app_paths).get(body.library)
        return JobAccepted(job_id=app_worker.submit("study_guide", body.model_dump()))

    @app.get("/api/v1/jobs/{job_id}", operation_id="getJob")
    def _get_job(job_id: str, _: Auth) -> dict[str, Any]:
        record = job_repository.job(job_id)
        record.pop("request", None)
        return record

    @app.get("/api/v1/study-guides/{guide_id}", operation_id="getStudyGuide")
    def _get_study_guide(guide_id: str, library: str, authenticated_origin: Auth) -> dict[str, Any]:
        del authenticated_origin
        _library_value, repository = _library(app_paths, library)
        payload = repository.guide_payload(guide_id)
        transcript = repository.get_transcript(str(payload["revision_id"]))
        guide = guide_from_payload(
            payload, transcript, str(payload["fingerprint"]), str(payload["output_language"])
        )
        result: dict[str, Any] = asdict(guide)
        for chapter, domain_chapter in zip(result["chapters"], guide.chapters, strict=True):
            start, end = domain_chapter.evidence.time_range(transcript)
            chapter["start_ms"] = start
            chapter["end_ms"] = end
            for question, domain_question in zip(
                chapter["questions"], domain_chapter.questions, strict=True
            ):
                qstart, qend = domain_question.evidence.time_range(transcript)
                question["start_ms"] = qstart
                question["end_ms"] = qend
        result["details"] = repository.chapter_details(guide_id)
        return result

    @app.post(
        "/api/v1/study-guides/{guide_id}/chapters/{chapter_id}/details",
        response_model=JobAccepted,
        status_code=status.HTTP_202_ACCEPTED,
        operation_id="createChapterDetail",
    )
    def _create_chapter_detail(
        guide_id: str, chapter_id: str, body: ChapterDetailRequest, _: Auth
    ) -> JobAccepted:
        request = {**body.model_dump(), "guide_id": guide_id, "chapter_id": chapter_id}
        return JobAccepted(job_id=app_worker.submit("chapter_detail", request))

    @app.post("/api/v1/notes", status_code=201, operation_id="createNote")
    def _create_note(body: NoteRequest, _: Auth) -> dict[str, Any]:
        library, repository = _library(app_paths, body.library)
        repository.get_transcript(body.source_id)
        note = new_note(
            revision_id=body.source_id,
            timestamp_ms=body.timestamp_ms,
            note_type=body.note_type,
            body=body.body,
        )
        publish_note(library, note)
        repository.save_note(note)
        return asdict(note)

    @app.get("/api/v1/sources/{source_id}/notes", operation_id="listNotes")
    def _list_notes(source_id: str, library: str, authenticated_origin: Auth) -> dict[str, Any]:
        del authenticated_origin
        _library_value, repository = _library(app_paths, library)
        return {"schema_version": 1, "notes": [asdict(n) for n in repository.notes(source_id)]}

    @app.post(
        "/api/v1/reflections",
        response_model=JobAccepted,
        status_code=status.HTTP_202_ACCEPTED,
        operation_id="createReflection",
    )
    def _create_reflection(body: ReflectionRequest, _: Auth) -> JobAccepted:
        return JobAccepted(job_id=app_worker.submit("reflection", body.model_dump()))

    return app
