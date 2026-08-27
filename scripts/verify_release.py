"""Validate the wheel and sdist produced by ``uv build`` without importing them."""

from __future__ import annotations

import argparse
import email
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

PROJECT = "bili_study"
VERSION = "0.2.0"
FORBIDDEN_PARTS = {
    ".coverage",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
}
FORBIDDEN_SUFFIXES = {".json.tmp", ".srt", ".tmp"}
FORBIDDEN_TOP_LEVEL = {".agents", ".github", "tests"}
EXPECTED_REQUIRES = {
    "fastapi<1,>=0.116",
    "httpx>=0.28",
    "keyring>=25.6",
    "qrcode>=8.2",
    "rich>=14.0",
    "typer>=0.16",
    "uvicorn<1,>=0.35",
}
SECRET_MARKERS = (
    b"SESS" + b"DATA=",
    b"bili_" + b"jct=",
    b"Dede" + b"UserID=",
    b"https://" + b"aisubtitle.hdslb.com/",
)


def _safe_names(names: list[str]) -> None:
    for raw_name in names:
        name = PurePosixPath(raw_name)
        if name.is_absolute() or ".." in name.parts:
            raise ValueError(f"unsafe archive member: {raw_name}")
        if FORBIDDEN_PARTS.intersection(name.parts) or any(
            raw_name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES
        ):
            raise ValueError(f"development or generated file in archive: {raw_name}")


def _check_sdist_scope(names: list[str]) -> None:
    for raw_name in names:
        parts = PurePosixPath(raw_name).parts
        if len(parts) > 1 and parts[1] in FORBIDDEN_TOP_LEVEL:
            raise ValueError(f"non-release tree in sdist: {raw_name}")


def _check_metadata(raw: bytes) -> None:
    metadata = email.message_from_bytes(raw)
    if metadata["Name"] != "bili-study" or metadata["Version"] != VERSION:
        raise ValueError("unexpected project identity in archive metadata")
    if metadata["Requires-Python"] != ">=3.12":
        raise ValueError("unexpected Python requirement")
    requires = {
        re.split(r";", value, maxsplit=1)[0].strip()
        for value in metadata.get_all("Requires-Dist", [])
    }
    if requires != EXPECTED_REQUIRES:
        raise ValueError(f"unexpected runtime dependencies: {sorted(requires)}")


def _check_contents(members: dict[str, bytes]) -> None:
    for name, content in members.items():
        if any(marker in content for marker in SECRET_MARKERS):
            raise ValueError(f"secret-like content in archive member: {name}")


def verify(dist: Path) -> tuple[Path, Path]:
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("dist must contain exactly one wheel and one sdist")
    wheel, sdist = wheels[0], sdists[0]
    if wheel.name != f"{PROJECT}-{VERSION}-py3-none-any.whl":
        raise ValueError(f"unexpected wheel: {wheel.name}")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        _safe_names(names)
        _check_contents({name: archive.read(name) for name in names if not name.endswith("/")})
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        entry_name = next(name for name in names if name.endswith(".dist-info/entry_points.txt"))
        _check_metadata(archive.read(metadata_name))
        if b"bili-subtitle = bili_subtitle.cli:main" not in archive.read(entry_name):
            raise ValueError("console entry point is missing")
        if b"bili-study = bili_study.cli:main" not in archive.read(entry_name):
            raise ValueError("new console entry point is missing")
        if not any(name.startswith("bili_subtitle/") for name in names):
            raise ValueError("wheel does not contain the package")
        if not any(name.startswith("bili_study/") for name in names):
            raise ValueError("wheel does not contain the new package")
        if not any(name.endswith(".dist-info/licenses/LICENSE") for name in names):
            raise ValueError("wheel does not contain LICENSE")
    with tarfile.open(sdist, "r:gz") as archive:
        names = archive.getnames()
        _safe_names(names)
        _check_sdist_scope(names)
        contents: dict[str, bytes] = {}
        for member in archive.getmembers():
            if member.isfile():
                extracted = archive.extractfile(member)
                if extracted is not None:
                    contents[member.name] = extracted.read()
        _check_contents(contents)
        root = f"{PROJECT}-{VERSION}/"
        required = {
            root + "README.md",
            root + "LICENSE",
            root + "pyproject.toml",
            root + "specs/mission.md",
            root + "specs/tech-stack.md",
            root + "specs/roadmap.md",
        }
        if not required.issubset(names):
            raise ValueError(f"sdist missing required files: {sorted(required.difference(names))}")
        pkg_info = archive.extractfile(root + "PKG-INFO")
        if pkg_info is None:
            raise ValueError("sdist metadata is missing")
        _check_metadata(pkg_info.read())
    return wheel, sdist


def verify_sdist_rebuild(sdist: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="bili-subtitle-sdist-build-") as temporary:
        output = Path(temporary)
        subprocess.run(
            ["uv", "build", "--wheel", str(sdist), "--out-dir", str(output)],
            check=True,
        )
        wheels = list(output.glob("*.whl"))
        if len(wheels) != 1 or wheels[0].name != f"{PROJECT}-{VERSION}-py3-none-any.whl":
            raise ValueError("sdist did not rebuild the expected wheel")
        with zipfile.ZipFile(wheels[0]) as archive:
            names = archive.namelist()
            _safe_names(names)
            if not any(name.startswith("bili_subtitle/") for name in names):
                raise ValueError("wheel rebuilt from sdist does not contain the package")
            if not any(name.startswith("bili_study/") for name in names):
                raise ValueError("wheel rebuilt from sdist does not contain the new package")
        return sdist


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path)
    parser.add_argument("--rebuild-sdist", action="store_true")
    args = parser.parse_args()
    try:
        wheel, sdist = verify(args.dist.resolve())
        if args.rebuild_sdist:
            verify_sdist_rebuild(sdist)
    except (
        OSError,
        ValueError,
        StopIteration,
        subprocess.CalledProcessError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as exc:
        print(f"release verification failed: {exc}", file=sys.stderr)
        return 1
    print(f"verified {wheel.name} and {sdist.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
