from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from io import BytesIO, TextIOWrapper
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bili_subtitle import cli
from bili_subtitle.application.auth import AuthOutcome
from bili_subtitle.application.full_flow import FlowResult, PageResult, TrackResult
from bili_subtitle.domain import PageSelection, SelectionSource, VideoMetadata, VideoPage
from bili_subtitle.domain.auth import (
    CredentialRead,
    CredentialState,
    LoginState,
    LoginStatus,
    SessionCredential,
)
from bili_subtitle.domain.errors import InputError
from bili_subtitle.domain.models import SubtitleTrack, SubtitleTrackKind

runner = CliRunner()


@pytest.fixture(autouse=True)
def authenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_login(*args: object, **kwargs: object) -> AuthOutcome:
        return AuthOutcome(LoginState.VALID, "已经登录。", SessionCredential({"fake": "cookie"}))

    monkeypatch.setattr(
        cli,
        "login",
        fake_login,
    )

    def fake_flow(**kwargs: object) -> FlowResult:
        del kwargs
        return FlowResult((), False)

    monkeypatch.setattr(cli, "run_extraction", fake_flow)


def test_root_help_describes_full_contract() -> None:
    result = runner.invoke(cli.extract_app, ["--help"])

    assert result.exit_code == 0
    assert "--page" in result.output
    assert "--all-pages" in result.output
    assert "--lang" in result.output
    assert "--force" in result.output
    assert "bili-subtitle auth login" in result.output


def test_root_without_video_shows_help() -> None:
    result = runner.invoke(cli.extract_app)

    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_extract_prints_flow_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    video = VideoMetadata(
        123,
        "BV1xx411c7mD",
        "标题\n伪造行",
        (VideoPage(1, 456, "第一集\x1b"),),
    )

    def fake_resolve(*args: object, **kwargs: object) -> PageSelection:
        return PageSelection(
            video,
            video.pages,
            SelectionSource.EXPLICIT_PAGE,
            ("提示：已覆盖。",),
        )

    monkeypatch.setattr(cli, "resolve_selection", fake_resolve)
    result = runner.invoke(cli.extract_app, ["BV1xx411c7mD", "--page", "1"])

    assert result.exit_code == 0
    assert "提示：已覆盖。" in result.output
    assert "摘要：分集 0" in result.output


def test_extract_maps_domain_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_resolve(*args: object, **kwargs: object) -> PageSelection:
        raise InputError("输入无效。")

    monkeypatch.setattr(cli, "resolve_selection", fake_resolve)
    result = runner.invoke(cli.extract_app, ["bad"])

    assert result.exit_code == 2
    assert "错误：输入无效。" in result.output


def test_extract_rejects_mutually_exclusive_page_options() -> None:
    result = runner.invoke(cli.extract_app, ["BV1xx411c7mD", "--page", "1", "--all-pages"])

    assert result.exit_code == 2
    assert "不能同时使用" in result.output


def test_extract_rejects_empty_language() -> None:
    result = runner.invoke(cli.extract_app, ["BV1xx411c7mD", "--lang", " "])
    assert result.exit_code == 2


def test_render_flow_classifications() -> None:
    page = VideoPage(1, 1, "unsafe\n")
    track = SubtitleTrack(1, "zh-CN", "x", SubtitleTrackKind.HUMAN)
    result = FlowResult(
        (
            PageResult(
                page,
                "success",
                (
                    TrackResult(track, "success", json_action="written", srt_action="skipped"),
                    TrackResult(track, "failed", error="x"),
                ),
            ),
            PageResult(VideoPage(2, 2, "x"), "no_match"),
            PageResult(VideoPage(3, 3, "x"), "failed", error="发现失败。"),
        ),
        True,
    )
    cli._render_flow(result)  # pyright: ignore[reportPrivateUsage]


def test_render_flow_explicitly_labels_all_skipped(capsys: pytest.CaptureFixture[str]) -> None:
    page = VideoPage(1, 1, "x")
    track = SubtitleTrack(1, "zh-CN", "x", SubtitleTrackKind.HUMAN)
    cli._render_flow(  # pyright: ignore[reportPrivateUsage]
        FlowResult(
            (
                PageResult(
                    page,
                    "success",
                    (
                        TrackResult(
                            track,
                            "success",
                            json_action="skipped",
                            srt_action="skipped",
                        ),
                    ),
                ),
            ),
            False,
        )
    )
    assert "全部已有文件跳过" in capsys.readouterr().out


def test_auth_help_lists_commands() -> None:
    result = runner.invoke(cli.auth_app, ["--help"])

    assert result.exit_code == 0
    for command in ("login", "status", "clear"):
        assert command in result.output


def test_auth_login_reports_success() -> None:
    result = runner.invoke(cli.auth_app, ["login"])
    assert result.exit_code == 0
    assert "已经登录" in result.output


def test_auth_login_maps_terminal_failure_to_operation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def expired(*args: object, **kwargs: object) -> AuthOutcome:
        return AuthOutcome(LoginState.EXPIRED, "二维码已过期。")

    monkeypatch.setattr(cli, "login", expired)
    result = runner.invoke(cli.auth_app, ["login"])
    assert result.exit_code == 2
    assert "二维码已过期" in result.stderr


def test_auth_login_handles_ctrl_c_without_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(*args: object, **kwargs: object) -> AuthOutcome:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "login", interrupt)
    result = runner.invoke(cli.auth_app, ["login"])
    assert result.exit_code == 2
    assert "登录已取消" in result.stderr
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("read", "expected"),
    [
        (CredentialRead(CredentialState.MISSING), "未登录"),
        (CredentialRead(CredentialState.INVALID), "凭据无效"),
    ],
)
def test_auth_status_local_states(
    monkeypatch: pytest.MonkeyPatch, read: CredentialRead, expected: str
) -> None:
    class Store:
        def read(self) -> CredentialRead:
            return read

    monkeypatch.setattr(cli, "KeyringCredentialStore", Store)
    result = runner.invoke(cli.auth_app, ["status"])
    assert result.exit_code == 1 and expected in result.output


def test_auth_status_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    credential = SessionCredential({"x": "y"})

    class Store:
        def read(self) -> CredentialRead:
            return CredentialRead(CredentialState.FOUND, credential)

    monkeypatch.setattr(cli, "KeyringCredentialStore", Store)

    def check(self: object, value: object) -> LoginStatus:
        return LoginStatus(LoginState.VALID, "用户\n名")

    monkeypatch.setattr(cli.BilibiliAuthAdapter, "check", check)
    result = runner.invoke(cli.auth_app, ["status"])
    assert result.exit_code == 0 and "用户 名" in result.output


@pytest.mark.parametrize(("removed", "text"), [(True, "已清除"), (False, "没有已保存")])
def test_auth_clear(monkeypatch: pytest.MonkeyPatch, removed: bool, text: str) -> None:
    class Store:
        def clear(self) -> bool:
            return removed

    monkeypatch.setattr(cli, "KeyringCredentialStore", Store)
    result = runner.invoke(cli.auth_app, ["clear"])
    assert result.exit_code == 0 and text in result.output


def test_main_dispatches_extract_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[tuple[str, list[str]]] = []

    def fake_app(*, prog_name: str, args: list[str]) -> None:
        received.append((prog_name, args))

    monkeypatch.setattr(cli, "extract_app", fake_app)
    monkeypatch.setattr(sys, "argv", ["bili-subtitle", "BV1xx411c7mD", "--force"])

    cli.main()

    assert received == [("bili-subtitle", ["BV1xx411c7mD", "--force"])]


def test_main_dispatches_auth_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[tuple[str, list[str]]] = []

    def fake_app(*, prog_name: str, args: list[str]) -> None:
        received.append((prog_name, args))

    typed_fake_app: Callable[..., None] = fake_app
    monkeypatch.setattr(cli, "auth_app", typed_fake_app)
    monkeypatch.setattr(sys, "argv", ["bili-subtitle", "auth", "status"])

    cli.main()

    assert received == [("bili-subtitle auth", ["status"])]


def test_main_reconfigures_non_utf8_standard_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout_bytes = BytesIO()
    stderr_bytes = BytesIO()
    stdout = TextIOWrapper(stdout_bytes, encoding="cp1252")
    stderr = TextIOWrapper(stderr_bytes, encoding="cp1252")

    def fake_app(*, prog_name: str, args: list[str]) -> None:
        del prog_name, args
        print("中文帮助")
        print("中文错误", file=sys.stderr)

    monkeypatch.setattr(cli, "extract_app", fake_app)
    monkeypatch.setattr(sys, "argv", ["bili-subtitle", "--help"])
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    cli.main()
    stdout.flush()
    stderr.flush()

    assert stdout_bytes.getvalue().decode("utf-8").splitlines() == ["中文帮助"]
    assert stderr_bytes.getvalue().decode("utf-8").splitlines() == ["中文错误"]


def test_help_survives_cp1252_fresh_process() -> None:
    command = (
        "import io, sys; "
        "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='cp1252'); "
        "sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='cp1252'); "
        "from bili_subtitle.cli import main; "
        "sys.argv = ['bili-subtitle', '--help']; main()"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    output = result.stdout.decode("utf-8")
    assert "提取一个普通 UGC 投稿" in output
    assert "认证命令" in output
