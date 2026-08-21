"""Fail offline when the lockfile drifts from the reviewed license inventory."""

from __future__ import annotations

import csv
import tomllib
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    with (root / "uv.lock").open("rb") as stream:
        locked = {
            (item["name"], item["version"])
            for item in tomllib.load(stream)["package"]
            if item["name"] != "bili-study"
        }
    with (root / "specs/licenses/dependency-audit.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = tuple(csv.DictReader(stream))
    audited = {(row["name"], row["version"]) for row in rows if row["scope"] != "build"}
    if locked != audited:
        raise SystemExit(
            f"license audit drift: missing={sorted(locked - audited)!r}; "
            f"stale={sorted(audited - locked)!r}"
        )
    if any(row["compatible"] != "yes" or not row["spdx"] for row in rows):
        raise SystemExit("license audit contains an unknown or incompatible conclusion")
    print(f"verified {len(rows)} audited dependencies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
