from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bili_study.cli import app
from bili_study.provider import ChatResult, ChatUsage

runner = CliRunner()


@pytest.fixture
def app_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    roaming = tmp_path / "roaming"
    local = tmp_path / "local"
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    return roaming, local


def create_library(tmp_path: Path) -> None:
    result = runner.invoke(app, ["library", "create", "main", str(tmp_path / "vault")])
    assert result.exit_code == 0, result.output


def import_transcript(tmp_path: Path) -> str:
    source = tmp_path / "subtitle.json"
    source.write_text(
        json.dumps({"body": [{"from": 0, "to": 1, "content": "内容"}]}), encoding="utf-8"
    )
    result = runner.invoke(
        app,
        [
            "transcript",
            "import",
            "--library",
            "main",
            str(source),
            "BV1xx411c7mD",
            "1",
            "123",
            "标题",
            "zh-CN",
            "中文",
        ],
    )
    assert result.exit_code == 0, result.output
    return result.output.split("：", 1)[1].split("（", 1)[0]


def test_library_cli_create_list_show_and_duplicate(
    app_data: tuple[Path, Path], tmp_path: Path
) -> None:
    del app_data
    create_library(tmp_path)
    listed = runner.invoke(app, ["library", "list"])
    shown = runner.invoke(app, ["library", "show", "main"])
    duplicate = runner.invoke(app, ["library", "create", "main", str(tmp_path / "other")])
    assert listed.exit_code == shown.exit_code == 0
    assert "main" in listed.output and "ID" in shown.output
    assert duplicate.exit_code == 2 and "已经存在" in duplicate.stderr


def test_transcript_and_note_cli_roundtrip(app_data: tuple[Path, Path], tmp_path: Path) -> None:
    del app_data
    create_library(tmp_path)
    revision_id = import_transcript(tmp_path)
    shown = runner.invoke(
        app, ["transcript", "show", "--library", "main", "--revision-id", revision_id]
    )
    assert shown.exit_code == 0 and "Cues：1" in shown.output
    added = runner.invoke(
        app,
        [
            "note",
            "add",
            "--library",
            "main",
            revision_id,
            "500",
            "我的笔记",
            "--note-type",
            "question",
        ],
    )
    assert added.exit_code == 0, added.output
    listed = runner.invoke(app, ["note", "list", "--library", "main", revision_id])
    assert listed.exit_code == 0 and "我的笔记" in listed.output


def test_provider_cli_never_prints_key(
    app_data: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    del app_data
    saved: dict[str, str] = {}

    def save_key(self: object, name: str, key: str) -> None:
        del self
        saved[name] = key

    monkeypatch.setattr("bili_study.cli.ProviderSecretStore.set", save_key)
    secret = "unique-api-key"
    result = runner.invoke(
        app,
        [
            "config",
            "provider",
            "set",
            "test",
            "https://model.example/v1",
            "model",
            "--api-key",
            secret,
        ],
    )
    assert result.exit_code == 0, result.output
    assert saved == {"test": secret}
    assert secret not in result.output
    shown = runner.invoke(app, ["config", "provider", "show", "test"])
    assert shown.exit_code == 0 and secret not in shown.output


def test_generation_confirmation_cancel_has_no_key_or_network(
    app_data: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app_data
    create_library(tmp_path)
    import_transcript(tmp_path)
    config = tmp_path / "roaming" / "bili-study" / "providers.json"
    config.write_text(
        json.dumps(
            {
                "test": {
                    "name": "test",
                    "base_url": "https://model.example/v1",
                    "model": "model",
                    "output_language": "zh-CN",
                    "context_budget": 1000,
                    "temperature": 0.2,
                }
            }
        ),
        encoding="utf-8",
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("secret or network access after cancellation")

    monkeypatch.setattr("bili_study.cli.ProviderSecretStore.get", forbidden)
    result = runner.invoke(
        app, ["guide", "generate", "--library", "main", "--provider", "test"], input="n\n"
    )
    assert result.exit_code == 0
    assert "已取消" in result.output


def test_guide_and_chapter_cli_generate_show_and_clear(
    app_data: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app_data
    create_library(tmp_path)
    import_transcript(tmp_path)

    def save_key(self: object, name: str, key: str) -> None:
        del self, name, key

    def get_key(self: object, name: str) -> str:
        del self, name
        return "secret"

    monkeypatch.setattr("bili_study.cli.ProviderSecretStore.set", save_key)
    config_result = runner.invoke(
        app,
        [
            "config",
            "provider",
            "set",
            "test",
            "https://model.example/v1",
            "model",
            "--api-key",
            "secret",
            "--context-budget",
            "1000",
        ],
    )
    assert config_result.exit_code == 0
    monkeypatch.setattr("bili_study.cli.ProviderSecretStore.get", get_key)

    guide: dict[str, object] = {
        "learning_objectives": ["理解"],
        "chapters": [
            {
                "chapter_id": "ch001",
                "title": "章节",
                "summary": "总结",
                "evidence": {"start_cue_id": "c000001", "end_cue_id": "c000001"},
                "questions": [],
            }
        ],
    }
    instances = 0

    class Chat:
        def __init__(self, responses: list[str]) -> None:
            self.responses = responses

        def __enter__(self) -> Chat:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def complete(self, *, system: str, user: str) -> ChatResult:
            del system, user
            return ChatResult(self.responses.pop(0), ChatUsage(None, None, None))

    def adapter(*args: object, **kwargs: object) -> Chat:
        nonlocal instances
        del args, kwargs
        instances += 1
        responses = (
            [json.dumps({"chapters": []}), json.dumps(guide)]
            if instances == 1
            else [
                json.dumps(
                    {
                        "summary": "详情",
                        "key_points": [],
                        "terms": [],
                        "easy_to_miss": [],
                        "evidence": {
                            "start_cue_id": "c000001",
                            "end_cue_id": "c000001",
                        },
                    }
                )
            ]
        )
        return Chat(responses)

    monkeypatch.setattr("bili_study.cli.OpenAIChatAdapter", adapter)
    generated = runner.invoke(
        app,
        ["guide", "generate", "--library", "main", "--provider", "test", "--yes"],
    )
    assert generated.exit_code == 0, generated.output
    guide_id = generated.output.split("：", 1)[1].splitlines()[0]
    shown = runner.invoke(app, ["guide", "show", "--library", "main", guide_id])
    assert shown.exit_code == 0 and "ch001" in shown.output
    detail = runner.invoke(
        app,
        [
            "chapter",
            "generate",
            "--library",
            "main",
            "--provider",
            "test",
            guide_id,
            "ch001",
            "--yes",
        ],
    )
    assert detail.exit_code == 0 and "详情" in detail.output, detail.output

    def clear_key(self: object, name: str) -> bool:
        del self, name
        return True

    monkeypatch.setattr("bili_study.cli.ProviderSecretStore.clear", clear_key)
    cleared = runner.invoke(app, ["config", "provider", "clear", "test"])
    assert cleared.exit_code == 0 and "已清除" in cleared.output


def test_cli_known_errors_are_stable(app_data: tuple[Path, Path], tmp_path: Path) -> None:
    del app_data
    assert runner.invoke(app, ["library", "show", "missing"]).exit_code == 2
    assert runner.invoke(app, ["config", "provider", "show", "missing"]).exit_code == 2
    create_library(tmp_path)
    assert runner.invoke(app, ["transcript", "show", "--library", "main"]).exit_code == 2
    assert runner.invoke(app, ["guide", "show", "--library", "main", "missing"]).exit_code == 2


def test_stage_nine_commands_are_registered() -> None:
    help_result = runner.invoke(app, ["--help"])
    stage_nine = ("library", "config", "transcript", "guide", "chapter", "note", "serve", "plugin")
    for command in stage_nine:
        assert command in help_result.output
    for unavailable in ("embedding", "review", "quiz"):
        assert runner.invoke(app, [unavailable]).exit_code == 2
