from __future__ import annotations

# pyright: reportUnknownArgumentType=false, reportUnknownLambdaType=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportPrivateUsage=false
import socket
import threading
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from bili_study import api as api_module
from bili_study.api import MAX_REQUEST_BYTES, create_app
from bili_study.cli import app as cli_app
from bili_study.domain import (
    Chapter,
    EvidenceRef,
    GuidingQuestion,
    StudyGuide,
    SubtitleTrackAmbiguous,
    SubtitleTrackUnavailable,
    TranscriptSourceMismatch,
    build_transcript,
    new_note,
    now_iso,
)
from bili_study.jobs import PersistentJobWorker, stable_error_code
from bili_study.provider import ChatResult, ChatUsage, ProviderAuthError, ProviderConfig
from bili_study.security import PairingStore, SecurityError, TokenRegistry, valid_extension_origin
from bili_study.services import (
    GenerationMetrics,
    GenerationResult,
    GuideGenerator,
    guide_to_payload,
)
from bili_study.storage import (
    AppPaths,
    LibraryRegistry,
    StorageError,
    StudyRepository,
    library_database,
)
from bili_subtitle.domain.errors import AuthenticationRequired, NoSubtitles
from bili_subtitle.domain.models import (
    PageSelection,
    SelectionSource,
    SubtitleBody,
    SubtitleCue,
    SubtitleTrack,
    SubtitleTrackKind,
    VideoMetadata,
    VideoPage,
)

ORIGIN = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
OTHER_ORIGIN = "chrome-extension://ponmlkjihgfedcbaponmlkjihgfedcba"
SOCKET_CONNECT = socket.socket.connect
SOCKET_CONNECT_EX = socket.socket.connect_ex


@pytest.fixture
def paths(tmp_path: Path) -> AppPaths:
    return AppPaths(tmp_path / "config", tmp_path / "state")


@pytest.fixture
def allow_testclient_socketpair(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow only the local socketpair AnyIO needs; create_connection stays blocked."""
    monkeypatch.setattr(socket.socket, "connect", SOCKET_CONNECT)
    monkeypatch.setattr(socket.socket, "connect_ex", SOCKET_CONNECT_EX)


def test_pairing_is_single_use_expiring_and_origin_limited(paths: AppPaths) -> None:
    store = PairingStore(paths)
    issued = datetime(2026, 8, 24, tzinfo=UTC)
    code, expires = store.create(now=issued)
    assert expires == issued + timedelta(minutes=5)
    with pytest.raises(SecurityError) as wrong:
        store.consume("WRONG-CODE", now=issued)
    assert wrong.value.code == "pairing_invalid"
    store.consume(code.lower(), now=issued)
    with pytest.raises(SecurityError, match="已使用"):
        store.consume(code, now=issued)

    expired, _ = store.create(now=issued)
    with pytest.raises(SecurityError) as error:
        store.consume(expired, now=issued + timedelta(minutes=6))
    assert error.value.code == "pairing_expired"
    assert valid_extension_origin(ORIGIN)
    assert valid_extension_origin("moz-extension://abcdefgh")
    assert not valid_extension_origin("https://www.bilibili.com")


def test_token_is_bound_to_origin_expires_and_revokes() -> None:
    registry = TokenRegistry()
    now = datetime(2026, 8, 24, tzinfo=UTC)
    token, expires = registry.issue(ORIGIN, now=now)
    assert expires > now and registry.authenticate(token, ORIGIN, now=now).origin == ORIGIN
    with pytest.raises(SecurityError) as wrong:
        registry.authenticate(token, OTHER_ORIGIN, now=now)
    assert wrong.value.code == "authentication_failed"
    registry.revoke(token)
    with pytest.raises(SecurityError):
        registry.authenticate(token, ORIGIN, now=now)
    token, _ = registry.issue(ORIGIN, now=now)
    with pytest.raises(SecurityError) as expired:
        registry.authenticate(token, ORIGIN, now=now + timedelta(days=31))
    assert expired.value.code == "token_expired"
    with pytest.raises(SecurityError, match="Origin"):
        registry.issue("https://evil.example")


def paired_client(paths: AppPaths) -> tuple[TestClient, dict[str, str]]:
    library = LibraryRegistry(paths).create("main", paths.config_dir / "vault")
    repository = StudyRepository(library_database(paths, library))
    repository.save_transcript(
        build_transcript(
            bvid="BV1xx411c7mD",
            page=1,
            cid=1,
            title="标题",
            track_id=1,
            language="zh-CN",
            display_name="中文",
            kind="human",
            cue_values=((0, 1000, "内容"),),
        )
    )
    pairing = PairingStore(paths)
    code, _ = pairing.create()
    client = TestClient(create_app(paths=paths, pairing=pairing))
    response = client.post("/api/v1/pair", headers={"Origin": ORIGIN}, json={"code": code})
    assert response.status_code == 200
    return client, {"Origin": ORIGIN, "Authorization": f"Bearer {response.json()['token']}"}


def test_api_pair_auth_cors_schema_and_personal_note(
    paths: AppPaths, allow_testclient_socketpair: None
) -> None:
    del allow_testclient_socketpair
    client, headers = paired_client(paths)
    with client:
        health = client.get("/api/v1/health")
        assert health.json() == {"status": "ok", "api_version": "1.3.0"}
        assert client.get("/api/v1/libraries", headers={"Origin": ORIGIN}).status_code == 401
        libraries = client.get("/api/v1/libraries", headers=headers)
        assert libraries.status_code == 200 and libraries.json()["libraries"][0]["name"] == "main"
        assert libraries.headers["access-control-allow-origin"] == ORIGIN
        assert (
            client.get("/api/v1/libraries", headers={**headers, "Origin": OTHER_ORIGIN}).status_code
            == 401
        )
        declared = {
            "X-Bili-Study-Origin": ORIGIN,
            "Authorization": headers["Authorization"],
        }
        assert client.get("/api/v1/libraries", headers=declared).status_code == 200
        mismatch = client.get(
            "/api/v1/libraries",
            headers={**headers, "X-Bili-Study-Origin": OTHER_ORIGIN},
        )
        assert mismatch.status_code == 403
        assert mismatch.json()["error"]["code"] == "origin_mismatch"

        repository = StudyRepository(library_database(paths, LibraryRegistry(paths).get("main")))
        revision = repository.latest_transcript()
        note = client.post(
            "/api/v1/notes",
            headers=headers,
            json={
                "library": "main",
                "source_id": revision.revision_id,
                "timestamp_ms": 500,
                "body": "我的 API 笔记",
            },
        )
        assert note.status_code == 201 and note.json()["body"] == "我的 API 笔记"
        listed = client.get(
            f"/api/v1/sources/{revision.revision_id}/notes?library=main", headers=headers
        )
        assert listed.json()["notes"][0]["timestamp_ms"] == 500
        assert (
            client.post(
                "/api/v1/notes", headers={**headers, "Content-Type": "text/plain"}, content="x"
            ).status_code
            == 415
        )
        assert (
            client.post(
                "/api/v1/notes", headers=headers, json={"library": "main", "unknown": True}
            ).json()["error"]["code"]
            == "validation_error"
        )


def test_api_rejects_host_origin_pair_reuse_and_large_request(
    paths: AppPaths, allow_testclient_socketpair: None
) -> None:
    del allow_testclient_socketpair
    pairing = PairingStore(paths)
    code, _ = pairing.create()
    app = create_app(paths=paths, pairing=pairing)
    with TestClient(app) as client:
        assert client.get("/api/v1/health", headers={"Host": "evil.example"}).status_code == 400
        assert (
            client.post(
                "/api/v1/pair", headers={"Origin": "https://evil.example"}, json={"code": code}
            ).status_code
            == 403
        )
        good = client.post("/api/v1/pair", headers={"Origin": ORIGIN}, json={"code": code})
        assert good.status_code == 200
        reused = client.post("/api/v1/pair", headers={"Origin": ORIGIN}, json={"code": code})
        assert reused.status_code == 403
        assert client.options("/api/v1/libraries", headers={"Origin": ORIGIN}).status_code == 204
        assert (
            client.options(
                "/api/v1/libraries", headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        too_large = client.post(
            "/api/v1/pair",
            headers={"Origin": ORIGIN, "Content-Length": str(MAX_REQUEST_BYTES + 1)},
            json={"code": "unused"},
        )
        assert too_large.status_code == 413
        invalid_length = client.post(
            "/api/v1/pair",
            headers={"Origin": ORIGIN, "Content-Length": "invalid"},
            content=b"{}",
        )
        assert invalid_length.status_code == 400


def test_openapi_is_versioned_and_declares_bearer_security(paths: AppPaths) -> None:
    schema = create_app(paths=paths).openapi()
    assert schema["info"]["version"] == "1.3.0"
    assert "/api/v1/reflections" in schema["paths"]
    assert "/api/v1/study-guides/{guide_id}/workspace" in schema["paths"]
    assert "/api/v1/videos/{bvid}/pages/{page}/transcripts" in schema["paths"]
    assert "/api/v1/transcripts/{revision_id}" in schema["paths"]
    assert "/api/v1/jobs/{job_id}/cancel" in schema["paths"]
    source_fields = schema["components"]["schemas"]["SourceRequest"]["properties"]
    assert "cid" not in source_fields and "title" not in source_fields
    assert {"revision_id", "expected_bvid", "expected_page"} <= source_fields.keys()
    assert (
        schema["components"]["schemas"]["StudyWorkspaceResponse"]["additionalProperties"] is False
    )
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    assert schema["paths"]["/api/v1/pair"]["post"].get("security") is None


def test_api_rate_and_concurrency_limits(
    paths: AppPaths,
    allow_testclient_socketpair: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del allow_testclient_socketpair
    monkeypatch.setattr(api_module, "RATE_LIMIT_PER_MINUTE", 1)
    application = create_app(paths=paths)
    with TestClient(application) as client:
        assert client.get("/api/v1/health", headers={"Origin": ORIGIN}).status_code == 200
        limited = client.get("/api/v1/health", headers={"Origin": ORIGIN})
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limit_exceeded"

        for _ in range(8):
            assert application.state.concurrent.acquire(blocking=False)
        try:
            concurrent = client.get("/api/v1/health")
        finally:
            for _ in range(8):
                application.state.concurrent.release()
        assert concurrent.status_code == 429
        assert concurrent.json()["error"]["code"] == "concurrency_limit_exceeded"


def test_persistent_worker_serializes_classifies_and_recovers(paths: AppPaths) -> None:
    repository = StudyRepository(paths.state_dir / "jobs.sqlite3")
    order: list[int] = []
    worker = PersistentJobWorker(repository)
    worker.register("ok", lambda raw, _progress: order.append(int(raw["number"])) or {"ok": True})

    def fail(_: dict[str, object], _progress: object) -> dict[str, object]:
        raise AuthenticationRequired("secret-free")

    worker.register("fail", fail)
    worker.start()
    first = worker.submit("ok", {"number": 1})
    second = worker.submit("ok", {"number": 2})
    failed = worker.submit("fail", {})
    deadline = time.monotonic() + 3
    while repository.job(failed)["status"] not in {"succeeded", "failed"}:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    worker.stop()
    assert order == [1, 2]
    assert repository.job(first)["status"] == repository.job(second)["status"] == "succeeded"
    assert repository.job(second)["progress"] == {"phase": "completed", "percent": 100}
    assert repository.job(failed)["error_code"] == "bilibili_authentication_required"
    with pytest.raises(StorageError):
        worker.submit("missing", {})

    interrupted = repository.create_job("ok", {"number": 3}, "start")
    assert repository.claim_job(interrupted, "running")
    assert repository.recover_jobs("restart") == ()
    assert repository.job(interrupted)["status"] == "interrupted"
    assert repository.job(interrupted)["error_code"] == "service_restarted"


def test_job_progress_is_persisted_and_monotonic(paths: AppPaths) -> None:
    repository = StudyRepository(paths.state_dir / "progress.sqlite3")
    job_id = repository.create_job("guide", {}, "created")
    assert repository.job(job_id)["progress"] == {"phase": "queued", "percent": 0}
    assert repository.claim_job(job_id, "started")
    repository.update_job_progress(job_id, "generating_outline", 35, "running")
    assert repository.job(job_id)["progress"] == {
        "phase": "generating_outline",
        "percent": 35,
    }
    with pytest.raises(StorageError, match="倒退"):
        repository.update_job_progress(job_id, "fetching_transcript", 10, "invalid")


def test_job_cancel_retry_and_restart_do_not_replay_running_work(paths: AppPaths) -> None:
    repository = StudyRepository(paths.state_dir / "cancel.sqlite3")
    queued = repository.create_job("guide", {"value": "original"}, "created")
    assert repository.cancel_job(queued, "cancelled") == "cancelled"
    assert repository.cancel_job(queued, "again") == "cancelled"
    retry = repository.retry_job(queued, "retry")
    assert retry == ("guide", queued, {"value": "original"})
    assert retry is not None

    new_job = repository.create_job(retry[0], retry[2], "retry", retry_of=retry[1])
    assert repository.job(new_job)["retry_of"] == queued
    running = repository.create_job("guide", {}, "created")
    assert repository.claim_job(running, "running")
    assert repository.cancel_job(running, "requested") == "cancel_requested"
    assert repository.recover_jobs("restart") == (new_job,)
    assert repository.job(running)["status"] == "interrupted"

    raced = repository.create_job("guide", {}, "created")
    assert repository.claim_job(raced, "running")
    assert repository.cancel_job(raced, "requested") == "cancel_requested"
    repository.complete_job(
        raced, status="succeeded", result={"late": True}, error_code=None, timestamp="late"
    )
    assert repository.job(raced)["status"] == "cancelled"
    assert repository.job(raced)["result"] is None


def test_inflight_cancel_discards_late_worker_result(paths: AppPaths) -> None:
    repository = StudyRepository(paths.state_dir / "inflight.sqlite3")
    worker = PersistentJobWorker(repository)
    entered = threading.Event()
    release = threading.Event()

    def handler(_raw: dict[str, object], progress: object) -> dict[str, object]:
        entered.set()
        assert release.wait(timeout=2)
        assert callable(progress)
        progress("after_provider", 80)
        return {"must_not_be_saved": True}

    worker.register("guide", handler)
    worker.start()
    job_id = worker.submit("guide", {})
    assert entered.wait(timeout=2)
    assert worker.cancel(job_id) == "cancel_requested"
    release.set()
    deadline = time.monotonic() + 2
    while repository.job(job_id)["status"] not in {"cancelled", "failed"}:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    worker.stop()
    record = repository.job(job_id)
    assert record["status"] == "cancelled"
    assert record["result"] is None


def test_stable_error_codes_do_not_expose_exception_text() -> None:
    assert stable_error_code(NoSubtitles("subtitle body")) == "no_subtitles"
    assert stable_error_code(ProviderAuthError("provider response")) == "authentication"
    assert (
        stable_error_code(SubtitleTrackUnavailable("selected track"))
        == "subtitle_track_unavailable"
    )
    assert stable_error_code(SubtitleTrackAmbiguous("same name")) == "subtitle_track_ambiguous"
    assert stable_error_code(RuntimeError("canary-secret")) == "internal_error"


def test_cli_pair_and_port_conflict_are_stable(
    paths: AppPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APPDATA", str(paths.config_dir.parent))
    monkeypatch.setenv("LOCALAPPDATA", str(paths.state_dir.parent))
    runner = CliRunner()
    paired = runner.invoke(cli_app, ["plugin", "pair"])
    assert paired.exit_code == 0 and "配对码" in paired.output and "有效期" in paired.output

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    try:
        conflict = runner.invoke(cli_app, ["serve", "--port", str(port)])
    finally:
        listener.close()
    assert conflict.exit_code == 2 and "端口已被占用" in conflict.stderr


def _wait_api_job(client: TestClient, job_id: str, headers: dict[str, str]) -> dict[str, object]:
    deadline = time.monotonic() + 3
    while True:
        payload = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
        if payload["status"] in {"succeeded", "failed"}:
            return payload
        assert time.monotonic() < deadline
        time.sleep(0.01)


def test_async_api_routes_and_guide_read_model(
    paths: AppPaths,
    allow_testclient_socketpair: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del allow_testclient_socketpair
    library = LibraryRegistry(paths).create("main", paths.config_dir / "vault")
    repository = StudyRepository(library_database(paths, library))
    transcript = build_transcript(
        bvid="BV1xx411c7mD",
        page=1,
        cid=10,
        title="标题",
        track_id=9,
        language="zh-CN",
        display_name="中文",
        kind="human",
        cue_values=((0, 1000, "第一句"), (1000, 2000, "第二句")),
    )
    repository.save_transcript(transcript)
    evidence = EvidenceRef(transcript.revision_id, "c000001", "c000002")
    question = GuidingQuestion("q001-01", "复述一下？", evidence)
    guide = StudyGuide(
        "guide-1",
        1,
        transcript.revision_id,
        "fingerprint",
        "zh-CN",
        ("理解",),
        (Chapter("ch001", "章节", "概述", evidence, (question,)),),
        now_iso(),
    )
    repository.save_guide(guide, guide_to_payload(guide))
    note = new_note(
        revision_id=transcript.revision_id,
        timestamp_ms=500,
        note_type="note",
        body="保存的笔记",
    )
    repository.save_note(note)
    repository.save_reflection(
        "reflection-saved",
        transcript.revision_id,
        question.question_id,
        {
            "reflection_id": "reflection-saved",
            "guide_id": guide.guide_id,
            "question_id": question.question_id,
            "response": "保存的回答",
            "status": "succeeded",
            "feedback": {"covered": ["要点"], "missing": [], "misconceptions": []},
        },
    )
    jobs = StudyRepository(paths.state_dir / "test-api-jobs.sqlite3")
    worker = PersistentJobWorker(jobs)
    monkeypatch.setattr(
        api_module,
        "_inspect_job",
        lambda _paths, raw, _progress: {
            "bvid": raw["bvid"],
            "page": raw["page"],
            "cid": 10,
            "tracks": [
                {
                    "track_id": "9",
                    "language": "zh-CN",
                    "display_name": "中文",
                    "kind": "human",
                }
            ],
        },
    )
    monkeypatch.setattr(
        api_module,
        "_guide_job",
        lambda _paths, _raw, _progress: {"guide_id": guide.guide_id},
    )
    monkeypatch.setattr(
        api_module,
        "_transcript_job",
        lambda _paths, raw, _progress: {
            "bvid": raw["bvid"],
            "page": raw["page"],
            "revision_id": transcript.revision_id,
        },
    )
    monkeypatch.setattr(
        api_module,
        "_detail_job",
        lambda _paths, raw, _progress: {"chapter_id": raw["chapter_id"]},
    )
    monkeypatch.setattr(
        api_module,
        "_practice_job",
        lambda _paths, raw, _progress: {"chapter_id": raw["chapter_id"]},
    )
    monkeypatch.setattr(
        api_module,
        "_reflection_job",
        lambda _paths, raw, _progress: {"question_id": raw["question_id"]},
    )
    pairing = PairingStore(paths)
    code, _ = pairing.create()
    app = create_app(paths=paths, pairing=pairing, worker=worker)
    with TestClient(app) as client:
        pair = client.post("/api/v1/pair", headers={"Origin": ORIGIN}, json={"code": code})
        headers = {"Origin": ORIGIN, "Authorization": f"Bearer {pair.json()['token']}"}
        inspect = client.post(
            "/api/v1/videos/inspect",
            headers=headers,
            json={"library": "main", "bvid": transcript.bvid, "page": 1},
        )
        assert inspect.status_code == 202
        assert _wait_api_job(client, inspect.json()["job_id"], headers)["status"] == "succeeded"
        mismatched = client.post(
            "/api/v1/videos/BV1yy411c7mD/pages/1/transcripts",
            headers=headers,
            json={
                "library": "main",
                "inspect_job_id": inspect.json()["job_id"],
                "track_id": "9",
                "track_language": "zh-CN",
                "track_display_name": "中文",
                "track_kind": "human",
            },
        )
        assert mismatched.status_code == 409
        assert mismatched.json()["error"]["code"] == "inspection_source_mismatch"
        prepared = client.post(
            f"/api/v1/videos/{transcript.bvid}/pages/1/transcripts",
            headers=headers,
            json={
                "library": "main",
                "inspect_job_id": inspect.json()["job_id"],
                "track_id": "9",
                "track_language": "zh-CN",
                "track_display_name": "中文",
                "track_kind": "human",
            },
        )
        assert _wait_api_job(client, prepared.json()["job_id"], headers)["result"] == {
            "bvid": transcript.bvid,
            "page": 1,
            "revision_id": transcript.revision_id,
        }
        transcript_read = client.get(
            f"/api/v1/transcripts/{transcript.revision_id}?library=main", headers=headers
        )
        assert transcript_read.json()["track_id"] == "9"
        assert transcript_read.json()["cues"][1]["text"] == "第二句"
        source = {
            "library": "main",
            "provider": "test",
            "revision_id": transcript.revision_id,
            "expected_bvid": transcript.bvid,
            "expected_page": 1,
        }
        accepted = client.post("/api/v1/study-guides", headers=headers, json=source)
        assert _wait_api_job(client, accepted.json()["job_id"], headers)["result"] == {
            "guide_id": "guide-1"
        }
        read = client.get("/api/v1/study-guides/guide-1?library=main", headers=headers)
        assert read.json()["chapters"][0]["start_ms"] == 0
        assert read.json()["chapters"][0]["questions"][0]["end_ms"] == 2000
        workspace = client.get(
            f"/api/v1/videos/{transcript.bvid}/pages/1/workspace?library=main",
            headers=headers,
        )
        assert workspace.json()["guide_id"] == guide.guide_id
        assert workspace.json()["revision_id"] == transcript.revision_id
        full_workspace = client.get(
            f"/api/v1/study-guides/{guide.guide_id}/workspace?library=main",
            headers=headers,
        )
        assert full_workspace.status_code == 200
        assert full_workspace.json()["guide"]["guide_id"] == guide.guide_id
        assert full_workspace.json()["notes"][0]["body"] == "保存的笔记"
        assert full_workspace.json()["reflections"][0]["response"] == "保存的回答"
        empty_workspace = client.get(
            f"/api/v1/videos/{transcript.bvid}/pages/2/workspace?library=main",
            headers=headers,
        )
        assert empty_workspace.json()["guide_id"] is None
        assert empty_workspace.json()["revision_id"] is None

        cancellable = jobs.create_job(
            "video_inspect",
            {"library": "main", "bvid": transcript.bvid, "page": 1},
            "queued",
        )
        cancelled = client.post(f"/api/v1/jobs/{cancellable}/cancel", headers=headers)
        assert cancelled.json()["status"] == "cancelled"
        assert client.post(f"/api/v1/jobs/{cancellable}/cancel", headers=headers).status_code == 200
        retried = client.post(f"/api/v1/jobs/{cancellable}/retry", headers=headers)
        assert retried.status_code == 202
        retried_record = _wait_api_job(client, retried.json()["job_id"], headers)
        assert retried_record["retry_of"] == cancellable
        terminal_cancel = client.post(
            f"/api/v1/jobs/{retried.json()['job_id']}/cancel", headers=headers
        )
        assert terminal_cancel.status_code == 409
        assert terminal_cancel.json()["error"]["code"] == "job_not_cancellable"
        assert (
            client.post(
                f"/api/v1/jobs/{retried.json()['job_id']}/retry", headers=headers
            ).status_code
            == 409
        )
        detail = client.post(
            "/api/v1/study-guides/guide-1/chapters/ch001/details",
            headers=headers,
            json={"library": "main", "provider": "test"},
        )
        assert _wait_api_job(client, detail.json()["job_id"], headers)["status"] == "succeeded"
        practice = client.post(
            "/api/v1/study-guides/guide-1/chapters/ch001/practice",
            headers=headers,
            json={"library": "main", "provider": "test"},
        )
        assert _wait_api_job(client, practice.json()["job_id"], headers)["status"] == "succeeded"
        reflection = client.post(
            "/api/v1/reflections",
            headers=headers,
            json={
                "library": "main",
                "provider": "test",
                "guide_id": "guide-1",
                "question_id": "q001-01",
                "response": "我的复述",
            },
        )
        assert _wait_api_job(client, reflection.json()["job_id"], headers)["status"] == "succeeded"
        assert client.get("/api/v1/jobs/missing", headers=headers).status_code == 404
        missing = client.get("/api/v1/study-guides/missing?library=main", headers=headers)
        assert missing.status_code == 404


class ReflectionChat:
    def __init__(self, content: str) -> None:
        self.content = content

    def complete(self, *, system: str, user: str) -> ChatResult:
        assert "不可信数据" in system and "evidence_based_reflection_feedback" in user
        return ChatResult(self.content, ChatUsage(None, None, None))


def test_reflection_generation_validates_response_and_evidence(paths: AppPaths) -> None:
    transcript = build_transcript(
        bvid="BV1xx411c7mD",
        page=1,
        cid=1,
        title="标题",
        track_id=1,
        language="zh-CN",
        display_name="中文",
        kind="human",
        cue_values=((0, 1000, "证据"),),
    )
    question = GuidingQuestion(
        "q1", "问题", EvidenceRef(transcript.revision_id, "c000001", "c000001")
    )
    repository = StudyRepository(paths.state_dir / "reflection.sqlite3")
    valid = (
        '{"covered":["要点"],"missing":[],"misconceptions":[],"evidence":'
        '[{"start_cue_id":"c000001","end_cue_id":"c000001"}]}'
    )
    payload, metrics = GuideGenerator(ReflectionChat(valid), repository).generate_reflection(
        transcript, question, "我的回答"
    )
    assert payload["covered"] == ["要点"] and metrics.requests == 1
    with pytest.raises(Exception, match="不能为空"):
        GuideGenerator(ReflectionChat(valid), repository).generate_reflection(
            transcript, question, " "
        )


class FakePlatformClient:
    def __enter__(self) -> FakePlatformClient:
        return self

    def __exit__(self, *args: object) -> None:
        del args


def test_platform_inspect_and_transcript_download_adapters(
    paths: AppPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = VideoPage(2, 55, "分集")
    selection = PageSelection(
        VideoMetadata(1, "BV1xx411c7mD", "标题", (page,)),
        (page,),
        SelectionSource.EXPLICIT_PAGE,
    )
    track = SubtitleTrack(2_080_600_637_229_272_576, "zh-CN", "中文", SubtitleTrackKind.HUMAN)
    monkeypatch.setattr(api_module, "_platform_client", lambda: (FakePlatformClient(), object()))
    monkeypatch.setattr(api_module, "resolve_selection", lambda *args, **kwargs: selection)

    class InspectAdapter:
        def __init__(self, client: object) -> None:
            del client

        def discover(
            self, *, bvid: str, cid: int, aid: int | None = None
        ) -> tuple[SubtitleTrack, ...]:
            assert bvid == "BV1xx411c7mD" and cid == 55 and aid == 1
            return (track,)

        def discard_pending(self, *, bvid: str, cid: int) -> None:
            assert bvid and cid

    monkeypatch.setattr(api_module, "BilibiliSubtitleAdapter", InspectAdapter)
    inspected = api_module._inspect_job(
        paths, {"library": "main", "bvid": "BV1xx411c7mD", "page": 2}
    )
    assert inspected["subtitle_status"] == "available"
    assert inspected["tracks"] == [
        {
            "track_id": "2080600637229272576",
            "language": "zh-CN",
            "display_name": "中文",
            "kind": "human",
        }
    ]

    class DownloadAdapter(InspectAdapter):
        def download_selected(
            self, *, bvid: str, cid: int, selected: SubtitleTrack
        ) -> SubtitleBody:
            assert bvid and cid == 55 and selected == track
            return SubtitleBody(b"{}", (SubtitleCue(Decimal("1.2"), Decimal("1.2"), "证据"),))

    monkeypatch.setattr(api_module, "BilibiliSubtitleAdapter", DownloadAdapter)
    transcript = api_module._download_transcript(
        {
            "bvid": "BV1xx411c7mD",
            "page": 2,
            "inspected_cid": 55,
            "inspect_job_id": "inspect-1",
            "title": "标题",
            "track_id": "2080600637229272576",
        }
    )
    assert transcript.cues[0].start_ms == 1200 and transcript.cues[0].end_ms == 1201
    library = LibraryRegistry(paths).create("main", paths.config_dir / "vault-transcript")
    progress: list[tuple[str, int]] = []
    prepared = api_module._transcript_job(
        paths,
        {
            "library": "main",
            "bvid": "BV1xx411c7mD",
            "page": 2,
            "inspected_cid": 55,
            "inspect_job_id": "inspect-1",
            "track_id": "2080600637229272576",
            "track_language": "zh-CN",
            "track_display_name": "中文",
            "track_kind": "human",
        },
        lambda phase, percent: progress.append((phase, percent)),
    )
    assert prepared["revision_id"] == transcript.revision_id
    assert progress == [("fetching_transcript", 10), ("validating_transcript", 85)]
    saved = StudyRepository(library_database(paths, library)).latest_transcript()
    assert saved.revision_id == transcript.revision_id
    assert saved.cues == transcript.cues
    with pytest.raises(Exception, match="轨道"):
        api_module._download_transcript(
            {
                "bvid": "BV1xx411c7mD",
                "page": 2,
                "inspected_cid": 55,
                "inspect_job_id": "inspect-1",
                "title": "标题",
                "track_id": 999,
            }
        )


def test_rotated_track_id_uses_only_a_unique_stable_descriptor() -> None:
    old_id = "2080600637229272576"
    replacement = SubtitleTrack(9, "zh-CN", "中文", SubtitleTrackKind.HUMAN)
    raw = {
        "track_id": old_id,
        "track_language": "zh-CN",
        "track_display_name": "中文",
        "track_kind": "human",
    }
    assert api_module._select_subtitle_track((replacement,), raw) == replacement

    duplicate = SubtitleTrack(10, "zh-CN", "中文", SubtitleTrackKind.HUMAN)
    with pytest.raises(SubtitleTrackAmbiguous):
        api_module._select_subtitle_track((replacement, duplicate), raw)

    with pytest.raises(SubtitleTrackUnavailable):
        api_module._select_subtitle_track(
            (SubtitleTrack(11, "en", "English", SubtitleTrackKind.HUMAN),), raw
        )


def test_guide_job_reuses_stage_eight_generation(
    paths: AppPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = LibraryRegistry(paths).create("main", paths.config_dir / "vault-guide")
    transcript = build_transcript(
        bvid="BV1xx411c7mD",
        page=1,
        cid=1,
        title="标题",
        track_id=1,
        language="zh-CN",
        display_name="中文",
        kind="human",
        cue_values=((0, 1000, "内容"),),
    )
    evidence = EvidenceRef(transcript.revision_id, "c000001", "c000001")
    guide = StudyGuide(
        "guide-job",
        1,
        transcript.revision_id,
        "fingerprint",
        "zh-CN",
        ("目标",),
        (Chapter("ch001", "章节", "总结", evidence),),
        now_iso(),
    )
    config = ProviderConfig("test", "https://model.example/v1", "model", "zh-CN", 1000)
    metrics = GenerationMetrics(1, None, None, None, 10, False)
    result = GenerationResult(guide, guide_to_payload(guide), metrics)
    monkeypatch.setattr(api_module, "_download_transcript", lambda _raw: transcript)
    monkeypatch.setattr(api_module.ProviderConfigStore, "get", lambda _self, _name: config)
    monkeypatch.setattr(api_module.ProviderSecretStore, "get", lambda _self, _name: "secret")

    class ChatContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *args: object) -> None:
            del args

    class Generator:
        def __init__(self, chat: object, repository: object) -> None:
            del chat, repository

        def generate(
            self,
            value: object,
            provider: object,
            *,
            regenerate: bool,
            progress: object,
        ) -> GenerationResult:
            assert value == transcript and provider == config and regenerate and progress
            return result

    monkeypatch.setattr(api_module, "OpenAIChatAdapter", lambda *_args: ChatContext())
    monkeypatch.setattr(api_module, "GuideGenerator", Generator)
    StudyRepository(library_database(paths, library)).save_transcript(transcript)
    completed = api_module._guide_job(
        paths,
        {
            "library": "main",
            "provider": "test",
            "regenerate": True,
            "revision_id": transcript.revision_id,
            "expected_bvid": transcript.bvid,
            "expected_page": 1,
        },
    )
    assert completed == {
        "guide_id": "guide-job",
        "source_id": transcript.revision_id,
        "revision_id": transcript.revision_id,
        "bvid": transcript.bvid,
        "page": 1,
        "cache_hit": False,
    }
    repository = StudyRepository(library_database(paths, library))
    assert repository.get_transcript(transcript.revision_id) == transcript
    assert (library.path / "generated" / "videos" / "guide-job.md").exists()


def test_existing_guide_short_circuits_before_platform_and_provider(
    paths: AppPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = LibraryRegistry(paths).create("main", paths.config_dir / "vault-existing")
    repository = StudyRepository(library_database(paths, library))
    transcript = build_transcript(
        bvid="BV1xx411c7mD",
        page=1,
        cid=1,
        title="标题",
        track_id=1,
        language="zh-CN",
        display_name="中文",
        kind="human",
        cue_values=((0, 1000, "内容"),),
    )
    repository.save_transcript(transcript)
    evidence = EvidenceRef(transcript.revision_id, "c000001", "c000001")
    guide = StudyGuide(
        "guide-existing",
        1,
        transcript.revision_id,
        "fingerprint",
        "zh-CN",
        ("目标",),
        (Chapter("ch001", "章节", "总结", evidence),),
        now_iso(),
    )
    repository.save_guide(guide, guide_to_payload(guide))
    monkeypatch.setattr(
        api_module,
        "_download_transcript",
        lambda _raw: pytest.fail("已有指南不得再次访问 Bilibili"),
    )
    monkeypatch.setattr(
        api_module.ProviderConfigStore,
        "get",
        lambda _self, _name: pytest.fail("已有指南不得读取 Provider"),
    )

    result = api_module._guide_job(
        paths,
        {
            "library": "main",
            "provider": "missing",
            "regenerate": False,
            "revision_id": transcript.revision_id,
            "expected_bvid": transcript.bvid,
            "expected_page": 1,
        },
    )

    assert result["guide_id"] == guide.guide_id
    assert result["reused_existing"] is True


def test_guide_revision_must_match_expected_page_before_provider(
    paths: AppPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = LibraryRegistry(paths).create("main", paths.config_dir / "vault-mismatch")
    repository = StudyRepository(library_database(paths, library))
    transcript = build_transcript(
        bvid="BV1xx411c7mD",
        page=1,
        cid=1,
        title="第一集",
        track_id=1,
        language="zh-CN",
        display_name="中文",
        kind="human",
        cue_values=((0, 1000, "内容"),),
    )
    repository.save_transcript(transcript)
    monkeypatch.setattr(
        api_module.ProviderConfigStore,
        "get",
        lambda *_args: pytest.fail("来源不匹配时不得读取 Provider"),
    )
    with pytest.raises(TranscriptSourceMismatch):
        api_module._guide_job(
            paths,
            {
                "library": "main",
                "provider": "unused",
                "revision_id": transcript.revision_id,
                "expected_bvid": transcript.bvid,
                "expected_page": 2,
            },
        )
    assert stable_error_code(TranscriptSourceMismatch("mismatch")) == "transcript_source_mismatch"


def test_detail_job_persists_generated_content(
    paths: AppPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = LibraryRegistry(paths).create("main", paths.config_dir / "vault-detail")
    repository = StudyRepository(library_database(paths, library))
    transcript = build_transcript(
        bvid="BV1xx411c7mD",
        page=1,
        cid=1,
        title="标题",
        track_id=1,
        language="zh-CN",
        display_name="中文",
        kind="human",
        cue_values=((0, 1000, "内容"),),
    )
    repository.save_transcript(transcript)
    evidence = EvidenceRef(transcript.revision_id, "c000001", "c000001")
    guide = StudyGuide(
        "guide-detail",
        1,
        transcript.revision_id,
        "fp",
        "zh-CN",
        ("目标",),
        (Chapter("ch001", "章节", "总结", evidence),),
        now_iso(),
    )
    repository.save_guide(guide, guide_to_payload(guide))
    config = ProviderConfig("test", "https://model.example/v1", "model", "zh-CN", 1000)
    monkeypatch.setattr(api_module.ProviderConfigStore, "get", lambda _self, _name: config)
    monkeypatch.setattr(api_module.ProviderSecretStore, "get", lambda _self, _name: "secret")

    class DetailChatContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *args: object) -> None:
            del args

    monkeypatch.setattr(api_module, "OpenAIChatAdapter", lambda *_args: DetailChatContext())

    class DetailGenerator:
        def __init__(self, chat: object, repo: object) -> None:
            del chat, repo

        def generate_chapter_detail(
            self, value: object, chapter: Chapter, *, progress: object
        ) -> tuple[dict[str, object], GenerationMetrics]:
            assert value == transcript and chapter.chapter_id == "ch001" and progress
            return {"summary": "详情"}, GenerationMetrics(1, None, None, None, 1, False)

    monkeypatch.setattr(api_module, "GuideGenerator", DetailGenerator)
    result = api_module._detail_job(
        paths,
        {"library": "main", "provider": "test", "guide_id": "guide-detail", "chapter_id": "ch001"},
    )
    assert result["detail"] == {"summary": "详情"}
    assert repository.chapter_details("guide-detail") == {"ch001": {"summary": "详情"}}
    monkeypatch.setattr(
        api_module.ProviderConfigStore,
        "get",
        lambda _self, _name: pytest.fail("已有详情不得读取 Provider"),
    )
    reused = api_module._detail_job(
        paths,
        {
            "library": "main",
            "provider": "missing",
            "guide_id": "guide-detail",
            "chapter_id": "ch001",
        },
    )
    assert reused["reused_existing"] is True


def test_practice_job_persists_questions(paths: AppPaths, monkeypatch: pytest.MonkeyPatch) -> None:
    library = LibraryRegistry(paths).create("main", paths.config_dir / "vault-practice")
    repository = StudyRepository(library_database(paths, library))
    transcript = build_transcript(
        bvid="BV1xx411c7mD",
        page=1,
        cid=1,
        title="标题",
        track_id=1,
        language="zh-CN",
        display_name="中文",
        kind="human",
        cue_values=((0, 1000, "内容"),),
    )
    repository.save_transcript(transcript)
    evidence = EvidenceRef(transcript.revision_id, "c000001", "c000001")
    guide = StudyGuide(
        "guide-practice",
        1,
        transcript.revision_id,
        "fp-practice",
        "zh-CN",
        ("目标",),
        (Chapter("ch001", "章节", "总结", evidence),),
        now_iso(),
    )
    repository.save_guide(guide, guide_to_payload(guide))
    config = ProviderConfig("test", "https://model.example/v1", "model", "zh-CN", 1000)
    monkeypatch.setattr(api_module.ProviderConfigStore, "get", lambda _self, _name: config)
    monkeypatch.setattr(api_module.ProviderSecretStore, "get", lambda _self, _name: "secret")

    class ChatContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *args: object) -> None:
            del args

    practice: dict[str, object] = {
        "questions": [
            {
                "question_id": "q-ch001-01",
                "text": "核心是什么？",
                "evidence": {"start_cue_id": "c000001", "end_cue_id": "c000001"},
            }
        ]
    }

    class Generator:
        def __init__(self, chat: object, repo: object) -> None:
            del chat, repo

        def generate_chapter_practice(
            self, value: object, chapter: Chapter, *, progress: object
        ) -> tuple[dict[str, object], GenerationMetrics]:
            assert value == transcript and chapter.chapter_id == "ch001" and progress
            return practice, GenerationMetrics(1, None, None, None, 1, False)

        def generate_reflection(
            self, value: object, question: GuidingQuestion, response: str
        ) -> tuple[dict[str, object], GenerationMetrics]:
            assert value == transcript and question.question_id == "q-ch001-01"
            assert response == "我的回答"
            return {
                "covered": ["要点"],
                "missing": [],
                "misconceptions": [],
                "evidence": [{"start_cue_id": "c000001", "end_cue_id": "c000001"}],
            }, GenerationMetrics(1, None, None, None, 1, False)

    monkeypatch.setattr(api_module, "OpenAIChatAdapter", lambda *_args: ChatContext())
    monkeypatch.setattr(api_module, "GuideGenerator", Generator)
    result = api_module._practice_job(
        paths,
        {
            "library": "main",
            "provider": "test",
            "guide_id": guide.guide_id,
            "chapter_id": "ch001",
        },
    )
    assert result["chapter_id"] == "ch001"
    assert repository.chapter_practices(guide.guide_id) == {"ch001": practice}
    monkeypatch.setattr(
        api_module.ProviderConfigStore,
        "get",
        lambda _self, _name: pytest.fail("已有练习不得读取 Provider"),
    )
    reused_practice = api_module._practice_job(
        paths,
        {
            "library": "main",
            "provider": "missing",
            "guide_id": guide.guide_id,
            "chapter_id": "ch001",
        },
    )
    assert reused_practice["reused_existing"] is True
    monkeypatch.setattr(api_module.ProviderConfigStore, "get", lambda _self, _name: config)
    reflection = api_module._reflection_job(
        paths,
        {
            "library": "main",
            "provider": "test",
            "guide_id": guide.guide_id,
            "question_id": "q-ch001-01",
            "response": "我的回答",
        },
    )
    assert reflection["feedback"] == {
        "covered": ["要点"],
        "missing": [],
        "misconceptions": [],
        "evidence": [{"start_cue_id": "c000001", "end_cue_id": "c000001"}],
    }
    assert any((library.path / "reviews").glob("*.md"))
    saved_reflection = repository.reflections(transcript.revision_id)[0]
    assert saved_reflection["status"] == "succeeded"
    assert saved_reflection["response"] == "我的回答"
    monkeypatch.setattr(
        api_module.ProviderConfigStore,
        "get",
        lambda _self, _name: pytest.fail("已有反馈不得读取 Provider"),
    )
    reused_reflection = api_module._reflection_job(
        paths,
        {
            "library": "main",
            "provider": "missing",
            "guide_id": guide.guide_id,
            "question_id": "q-ch001-01",
            "response": "我的回答",
        },
    )
    assert reused_reflection["reused_existing"] is True
    monkeypatch.setattr(api_module.ProviderConfigStore, "get", lambda _self, _name: config)

    class FailingGenerator(Generator):
        def generate_reflection(
            self, value: object, question: GuidingQuestion, response: str
        ) -> tuple[dict[str, object], GenerationMetrics]:
            del value, question, response
            raise RuntimeError("invalid provider output")

    monkeypatch.setattr(api_module, "GuideGenerator", FailingGenerator)
    with pytest.raises(RuntimeError, match="invalid provider output"):
        api_module._reflection_job(
            paths,
            {
                "library": "main",
                "provider": "test",
                "guide_id": guide.guide_id,
                "question_id": "q-ch001-01",
                "response": "不能丢失的回答",
            },
        )
    failed_reflection = repository.reflections(transcript.revision_id)[-1]
    assert failed_reflection["status"] == "feedback_failed"
    assert failed_reflection["response"] == "不能丢失的回答"


def test_evidence_times_are_added_recursively() -> None:
    transcript = build_transcript(
        bvid="BV1xx411c7mD",
        page=1,
        cid=1,
        title="标题",
        track_id=1,
        language="zh-CN",
        display_name="中文",
        kind="human",
        cue_values=((0, 1000, "内容"),),
    )
    enriched = api_module._with_evidence_times(
        {
            "items": [
                {
                    "text": "要点",
                    "evidence": {"start_cue_id": "c000001", "end_cue_id": "c000001"},
                }
            ]
        },
        transcript,
    )
    assert enriched == {
        "items": [
            {
                "text": "要点",
                "evidence": {
                    "start_cue_id": "c000001",
                    "end_cue_id": "c000001",
                    "start_ms": 0,
                    "end_ms": 1000,
                },
            }
        ]
    }
