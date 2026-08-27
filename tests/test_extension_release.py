from __future__ import annotations

import hashlib
import importlib.util
import zipfile
from pathlib import Path

import pytest


def _package(extension: Path, dist: Path, version: str) -> tuple[Path, ...]:
    script = Path(__file__).parents[1] / "scripts" / "package_extensions.py"
    spec = importlib.util.spec_from_file_location("package_extensions", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.package(extension, dist, version)


def test_extension_archives_are_reproducible_and_hashed(tmp_path: Path) -> None:
    extension = tmp_path / "extension"
    for browser in ("chrome", "edge"):
        source = extension / ".output" / f"{browser}-mv3"
        source.mkdir(parents=True)
        (source / "manifest.json").write_text('{"manifest_version":3}', encoding="utf-8")
        (source / "background.js").write_text("// deterministic", encoding="utf-8")
    first = _package(extension, tmp_path / "first", "0.2.0")
    second = _package(extension, tmp_path / "second", "0.2.0")
    for left, right in zip(first[:2], second[:2], strict=True):
        assert left.read_bytes() == right.read_bytes()
        with zipfile.ZipFile(left) as archive:
            assert archive.namelist() == ["background.js", "manifest.json"]
            assert all(item.date_time == (2026, 1, 1, 0, 0, 0) for item in archive.infolist())
    sums = first[2].read_text(encoding="ascii").splitlines()
    assert sums == [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in first[:2]
    ]


def test_extension_archive_requires_both_production_builds(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing chrome"):
        _package(tmp_path / "extension", tmp_path / "dist", "0.2.0")


def test_extension_archive_rejects_secret_like_build_content(tmp_path: Path) -> None:
    extension = tmp_path / "extension"
    for browser in ("chrome", "edge"):
        source = extension / ".output" / f"{browser}-mv3"
        source.mkdir(parents=True)
        (source / "manifest.json").write_text('{"manifest_version":3}', encoding="utf-8")
    (extension / ".output" / "chrome-mv3" / "leak.js").write_text(
        "const credential = 'SESSDATA=secret';", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="secret-like"):
        _package(extension, tmp_path / "dist", "0.2.0")
