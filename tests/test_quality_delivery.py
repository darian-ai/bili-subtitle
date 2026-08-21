from __future__ import annotations

import importlib.util
import socket
import zipfile
from pathlib import Path

import pytest


def test_default_suite_blocks_unmocked_network() -> None:
    with pytest.raises(AssertionError, match="must not access"):
        socket.create_connection(("127.0.0.1", 9))


def _release_module():
    script = Path(__file__).parents[1] / "scripts" / "verify_release.py"
    spec = importlib.util.spec_from_file_location("verify_release", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "member",
    ["../credential.json", "/absolute", "pkg/.venv/file", "pkg/out.srt", "pkg/cache.tmp"],
)
def test_archive_validator_rejects_unsafe_or_generated_members(member: str) -> None:
    module = _release_module()
    with pytest.raises(ValueError, match="archive|generated"):
        module._safe_names([member])


def test_archive_validator_requires_exact_release_pair(tmp_path: Path) -> None:
    module = _release_module()
    with pytest.raises(ValueError, match="exactly one"):
        module.verify(tmp_path)


def test_sdist_scope_rejects_development_trees() -> None:
    module = _release_module()
    with pytest.raises(ValueError, match="non-release tree"):
        module._check_sdist_scope(["bili_subtitle-0.1.0/tests/test_secret.py"])


def test_archive_validator_rejects_bad_wheel_name(tmp_path: Path) -> None:
    module = _release_module()
    wheel = tmp_path / "unexpected.whl"
    with zipfile.ZipFile(wheel, "w"):
        pass
    (tmp_path / "bili_subtitle-0.1.0.tar.gz").touch()
    with pytest.raises(ValueError, match="unexpected wheel"):
        module.verify(tmp_path)


def test_archive_validator_rejects_secret_like_content() -> None:
    module = _release_module()
    with pytest.raises(ValueError, match="secret-like"):
        marker = b"SESS" + b"DATA=fake-secret"
        module._check_contents({"package/data.txt": b"prefix " + marker + b" suffix"})


def test_sdist_rebuild_rejects_missing_rebuilt_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _release_module()

    def no_build(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(module.subprocess, "run", no_build)
    with pytest.raises(ValueError, match="did not rebuild"):
        module.verify_sdist_rebuild(tmp_path / "source.tar.gz")


def test_isolated_install_preserves_caller_uv_environment() -> None:
    script = Path(__file__).parents[1] / "scripts" / "verify_isolated_install.ps1"
    text = script.read_text(encoding="utf-8")
    assert '$originalToolDir = [Environment]::GetEnvironmentVariable("UV_TOOL_DIR"' in text
    assert '$originalBinDir = [Environment]::GetEnvironmentVariable("UV_TOOL_BIN_DIR"' in text
    assert '[Environment]::SetEnvironmentVariable("UV_TOOL_DIR", $originalToolDir' in text
    assert '[Environment]::SetEnvironmentVariable("UV_TOOL_BIN_DIR", $originalBinDir' in text


def test_committed_delivery_files_do_not_contain_secret_canaries() -> None:
    root = Path(__file__).parents[1]
    files = [
        root / "README.md",
        *(root / "scripts").glob("*.py"),
        *(root / "scripts").glob("*.ps1"),
        *(root / ".github").rglob("*.yml"),
    ]
    canaries = ("SESSDATA=", "bili_jct=", "DedeUserID=", "https://aisubtitle.hdslb.com/")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert all(canary not in text for canary in canaries), path
