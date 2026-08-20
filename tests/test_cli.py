from __future__ import annotations

import sys
from collections.abc import Callable

import pytest
from typer.testing import CliRunner

from bili_subtitle import cli
from bili_subtitle.application.auth import AuthOutcome
from bili_subtitle.domain import PageSelection, SelectionSource, VideoMetadata, VideoPage
from bili_subtitle.domain.auth import (
    CredentialRead,
    CredentialState,
    LoginState,
    LoginStatus,
    SessionCredential,
)
from bili_subtitle.domain.errors import InputError

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


def test_extract_prints_metadata_summary(monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert "标题：标题 伪造行" in result.output
    assert "BV号：BV1xx411c7mD" in result.output
    assert "av号：av123" in result.output
    assert "所选分集：1" in result.output
    assert "P01 | CID 456 | 第一集 " in result.output


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
