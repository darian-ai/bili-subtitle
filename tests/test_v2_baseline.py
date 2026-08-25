import ast
import sys
from contextlib import nullcontext
from importlib.metadata import version
from pathlib import Path
from typing import cast

import pytest
import typer
from typer.testing import CliRunner

import bili_study
import bili_study.cli as study_cli
import bili_subtitle.cli as legacy_cli
from bili_study.cli import app as study_app
from bili_subtitle.application.auth import AuthOutcome
from bili_subtitle.domain.auth import LoginState, SessionCredential
from bili_subtitle.infrastructure.credentials import DEFAULT_ACCOUNT, SERVICE_NAME

runner = CliRunner()


def test_distribution_and_both_packages_share_one_version_source() -> None:
    assert bili_study.__version__ == version("bili-study") == "0.2.0a1"


def test_bili_study_exposes_only_implemented_command_tree() -> None:
    result = runner.invoke(study_app, ["--help"])
    assert result.exit_code == 0
    assert "extract" in result.output and "auth" in result.output
    for implemented in (
        "library",
        "config",
        "transcript",
        "guide",
        "chapter",
        "note",
        "plugin",
        "serve",
    ):
        assert implemented in result.output
    for unavailable in ("doctor",):
        assert unavailable not in result.output


def test_both_command_trees_share_handlers_and_credential_identity() -> None:
    assert study_cli.extract is legacy_cli.extract
    assert study_cli.auth_app is legacy_cli.auth_app
    assert SERVICE_NAME == "bili-subtitle"
    assert DEFAULT_ACCOUNT == "default"


@pytest.mark.parametrize(
    "args",
    [
        ["not-a-video"],
        ["BV1-invalid!"],
        ["https://example.com/video/BV1xx411c7mD"],
        ["BV1xx411c7mD", "--page", "1", "--all-pages"],
        ["BV1xx411c7mD", "--lang", " "],
    ],
)
def test_pure_input_errors_are_rejected_before_external_io(
    monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("external I/O was attempted")

    for name in ("create_http_client", "KeyringCredentialStore", "login", "render_qr"):
        monkeypatch.setattr(legacy_cli, name, forbidden)

    old_result = runner.invoke(legacy_cli.extract_app, args)
    new_result = runner.invoke(study_app, ["extract", *args])

    assert old_result.exit_code == new_result.exit_code == 2
    assert "Traceback" not in old_result.output + new_result.output


def test_invalid_video_is_rejected_before_any_external_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden() -> None:
        pytest.fail("external I/O was attempted")

    monkeypatch.setattr(legacy_cli, "create_http_client", forbidden)
    monkeypatch.setattr(legacy_cli, "KeyringCredentialStore", forbidden)

    old_result = runner.invoke(legacy_cli.extract_app, ["not-a-video"])
    new_result = runner.invoke(study_app, ["extract", "not-a-video"])

    assert old_result.exit_code == new_result.exit_code == 2
    assert "not-a-video" not in old_result.output


def test_extract_distinguishes_login_and_authenticated_interrupts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "SESSDATA=interrupt-canary"
    monkeypatch.setattr(legacy_cli, "KeyringCredentialStore", lambda: object())
    monkeypatch.setattr(legacy_cli, "create_http_client", lambda: nullcontext(object()))

    def unused_auth(client: object) -> object:
        del client
        return object()

    monkeypatch.setattr(legacy_cli, "BilibiliAuthAdapter", unused_auth)

    def login_interrupt(*args: object, **kwargs: object) -> AuthOutcome:
        del args, kwargs
        raise KeyboardInterrupt(secret)

    monkeypatch.setattr(legacy_cli, "login", login_interrupt)
    login_result = runner.invoke(legacy_cli.extract_app, ["BV1xx411c7mD"])
    assert login_result.exit_code == 2
    assert "登录已取消" in login_result.stderr
    assert secret not in login_result.output

    credential = SessionCredential({"fake": "cookie"})

    def valid_login(*args: object, **kwargs: object) -> AuthOutcome:
        del args, kwargs
        return AuthOutcome(LoginState.VALID, "ok", credential)

    monkeypatch.setattr(
        legacy_cli,
        "login",
        valid_login,
    )

    class Auth:
        def apply(self, value: SessionCredential) -> None:
            assert value is credential

    def authenticated_adapter(client: object) -> Auth:
        del client
        return Auth()

    monkeypatch.setattr(legacy_cli, "BilibiliAuthAdapter", authenticated_adapter)

    def extraction_interrupt(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise KeyboardInterrupt(secret)

    monkeypatch.setattr(legacy_cli, "resolve_selection", extraction_interrupt)
    extraction_result = runner.invoke(legacy_cli.extract_app, ["BV1xx411c7mD"])
    assert extraction_result.exit_code == 2
    assert "字幕提取已取消" in extraction_result.stderr
    assert secret not in extraction_result.output


@pytest.mark.parametrize("expected", [0, 1, 2])
def test_new_console_main_preserves_shared_exit_codes(
    monkeypatch: pytest.MonkeyPatch, expected: int
) -> None:
    def return_exit_code(*args: object, **kwargs: object) -> int:
        del args, kwargs
        return expected

    monkeypatch.setattr(study_cli, "_configure_standard_streams", lambda: None)
    monkeypatch.setattr(study_cli, "_run_app", return_exit_code)
    monkeypatch.setattr(sys, "argv", ["bili-study"])
    assert study_cli.main() == expected


def test_unknown_commands_are_real_parameter_errors() -> None:
    for command in ("doctor",):
        result = runner.invoke(study_app, [command])
        assert result.exit_code == 2
        assert command not in runner.invoke(study_app, ["--help"]).output


def test_application_and_domain_dependency_boundaries_are_static() -> None:
    root = Path(__file__).parents[1] / "src" / "bili_subtitle"
    for layer in ("application", "domain"):
        for source_path in (root / layer).glob("*.py"):
            source = source_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            imports = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
            assert not any(".infrastructure" in name for name in imports), source_path
            if layer == "application":
                caught = [
                    node.type.id
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ExceptHandler) and isinstance(node.type, ast.Name)
                ]
                assert "Exception" not in caught, source_path


def test_cli_boundary_redacts_unknown_exception(capsys: pytest.CaptureFixture[str]) -> None:
    secret = "SESSDATA=must-not-leak"

    class BrokenApp:
        def __call__(self, **kwargs: object) -> None:
            del kwargs
            raise RuntimeError(secret)

    assert (
        legacy_cli._run_app(  # pyright: ignore[reportPrivateUsage]
            cast(typer.Typer, BrokenApp()), prog_name="bili-study", args=[]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert "内部错误" in captured.err
    assert secret not in captured.out + captured.err
