from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

import pytest


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
