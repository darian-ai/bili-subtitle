from __future__ import annotations

import sys
from collections.abc import Callable

import pytest
from typer.testing import CliRunner

from bili_subtitle import cli
from bili_subtitle.domain import PageSelection, SelectionSource, VideoMetadata, VideoPage
from bili_subtitle.domain.errors import InputError

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
