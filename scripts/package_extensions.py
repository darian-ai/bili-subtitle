"""Create deterministic Chrome/Edge extension archives and SHA-256 manifest."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

BROWSERS = ("chrome", "edge")
FIXED_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
SECRET_MARKERS = (
    b"SESS" + b"DATA=",
    b"bili_" + b"jct=",
    b"Dede" + b"UserID=",
    b"Bearer sk-",
    b"https://" + b"aisubtitle.hdslb.com/",
)


def package(extension: Path, dist: Path, version: str) -> tuple[Path, ...]:
    dist.mkdir(parents=True, exist_ok=True)
    archives: list[Path] = []
    for browser in BROWSERS:
        source = extension / ".output" / f"{browser}-mv3"
        if not (source / "manifest.json").is_file():
            raise ValueError(f"missing {browser} production build")
        target = dist / f"bili-study-extension-{version}-{browser}.zip"
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as out:
            for path in sorted(item for item in source.rglob("*") if item.is_file()):
                relative = path.relative_to(source).as_posix()
                content = path.read_bytes()
                if any(marker in content for marker in SECRET_MARKERS):
                    raise ValueError(f"secret-like content in {browser} build: {relative}")
                info = zipfile.ZipInfo(relative, FIXED_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                out.writestr(info, content, compresslevel=9)
        archives.append(target)
    manifest = dist / "SHA256SUMS"
    manifest.write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in archives
        ),
        encoding="ascii",
        newline="\n",
    )
    return (*archives, manifest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extension", type=Path, default=Path("extension"))
    parser.add_argument("--dist", type=Path, default=Path("dist/extensions"))
    parser.add_argument("--version", default="0.2.0")
    args = parser.parse_args()
    try:
        outputs = package(args.extension.resolve(), args.dist.resolve(), args.version)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
