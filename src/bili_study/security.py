"""Pairing and request authentication for the loopback API."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from bili_study.storage import AppPaths, StorageError, atomic_write

PAIRING_LIFETIME = timedelta(minutes=5)
TOKEN_LIFETIME = timedelta(days=30)
_EXTENSION_ORIGIN = re.compile(r"(?:chrome|moz)-extension://[a-z0-9_-]{8,128}\Z")


class SecurityError(RuntimeError):
    """A stable pairing or authentication failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def valid_extension_origin(origin: str) -> bool:
    """Return whether an Origin is a browser extension, never an ordinary page."""
    return _EXTENSION_ORIGIN.fullmatch(origin) is not None


@dataclass(frozen=True, slots=True)
class TokenBinding:
    origin: str
    expires_at: datetime


class PairingStore:
    """Share a single-use code between the CLI and a separately running server."""

    def __init__(self, paths: AppPaths) -> None:
        self._path = paths.state_dir / "plugin-pairing.json"
        self._lock = threading.Lock()

    def create(self, *, now: datetime | None = None) -> tuple[str, datetime]:
        issued = now or datetime.now(UTC)
        expires = issued + PAIRING_LIFETIME
        code = "-".join((secrets.token_hex(2), secrets.token_hex(2))).upper()
        payload = {
            "schema_version": 1,
            "code_sha256": hashlib.sha256(code.encode("ascii")).hexdigest(),
            "expires_at": expires.isoformat(),
        }
        with self._lock:
            atomic_write(self._path, json.dumps(payload, sort_keys=True).encode("utf-8"))
        return code, expires

    def consume(self, code: str, *, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        with self._lock:
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                expected = str(raw["code_sha256"])
                expires = datetime.fromisoformat(str(raw["expires_at"]))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise SecurityError("pairing_invalid", "配对码无效或已使用。") from exc
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            supplied = hashlib.sha256(code.strip().upper().encode("ascii", "ignore")).hexdigest()
            if current >= expires:
                self._path.unlink(missing_ok=True)
                raise SecurityError("pairing_expired", "配对码已过期。")
            if not hmac.compare_digest(expected, supplied):
                raise SecurityError("pairing_invalid", "配对码无效或已使用。")
            self._path.unlink(missing_ok=True)


class TokenRegistry:
    """Keep bearer values in memory and bind each one to exactly one Origin."""

    def __init__(self) -> None:
        self._bindings: dict[str, TokenBinding] = {}
        self._lock = threading.Lock()

    def issue(self, origin: str, *, now: datetime | None = None) -> tuple[str, datetime]:
        if not valid_extension_origin(origin):
            raise SecurityError("origin_not_allowed", "只允许浏览器扩展 Origin 配对。")
        expires = (now or datetime.now(UTC)) + TOKEN_LIFETIME
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        with self._lock:
            self._bindings[digest] = TokenBinding(origin, expires)
        return token, expires

    def authenticate(self, token: str, origin: str, *, now: datetime | None = None) -> TokenBinding:
        digest = hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()
        with self._lock:
            binding = self._bindings.get(digest)
        if binding is None or not hmac.compare_digest(binding.origin, origin):
            raise SecurityError("authentication_failed", "Bearer token 无效。")
        if (now or datetime.now(UTC)) >= binding.expires_at:
            self.revoke(token)
            raise SecurityError("token_expired", "Bearer token 已过期。")
        return binding

    def revoke(self, token: str) -> None:
        digest = hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()
        with self._lock:
            self._bindings.pop(digest, None)


def pairing_store(paths: AppPaths | None = None) -> PairingStore:
    try:
        return PairingStore(paths or AppPaths.windows_default())
    except StorageError:
        raise
