from importlib.metadata import version
from typing import cast

import pytest
import typer
from typer.testing import CliRunner

import bili_study
import bili_subtitle.cli as legacy_cli
from bili_study.cli import app as study_app

runner = CliRunner()


def test_distribution_and_both_packages_share_one_version_source() -> None:
    assert bili_study.__version__ == version("bili-study") == "0.1.1"


def test_bili_study_exposes_only_implemented_command_tree() -> None:
    result = runner.invoke(study_app, ["--help"])
    assert result.exit_code == 0
    assert "extract" in result.output and "auth" in result.output
    for unavailable in ("library", "config", "plugin", "serve", "doctor"):
        assert unavailable not in result.output


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
