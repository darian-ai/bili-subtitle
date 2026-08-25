"""Export the canonical Local API schema for generated clients and drift checks."""

from __future__ import annotations

import json
import os
from contextlib import suppress
from pathlib import Path

from bili_study.api import create_app
from bili_study.storage import AppPaths


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    state = root / ".openapi-state"
    paths = AppPaths(state / "config", state / "state")
    schema = create_app(paths=paths).openapi()
    target = root / "extension" / "openapi.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # This state is build-only and must never enter source control.
    database = state / "state" / "api.sqlite3"
    database.unlink(missing_ok=True)
    for directory in (state / "state", state / "config", state):
        with suppress(OSError):
            os.rmdir(directory)


if __name__ == "__main__":
    main()
