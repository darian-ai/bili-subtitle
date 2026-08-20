from __future__ import annotations

import sys
from collections.abc import Callable

import pytest
from typer.testing import CliRunner

from bili_subtitle import cli

runner = CliRunner()


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


def test_extract_placeholder_fails_explicitly() -> None:
    result = runner.invoke(cli.extract_app, ["BV1xx411c7mD"])

    assert result.exit_code == 2
    assert "尚未实现" in result.output


def test_auth_help_lists_commands() -> None:
    result = runner.invoke(cli.auth_app, ["--help"])

    assert result.exit_code == 0
    for command in ("login", "status", "clear"):
        assert command in result.output


@pytest.mark.parametrize("command", ["login", "status", "clear"])
def test_auth_placeholders_fail_explicitly(command: str) -> None:
    result = runner.invoke(cli.auth_app, [command])

    assert result.exit_code == 2
    assert "尚未实现" in result.output


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
