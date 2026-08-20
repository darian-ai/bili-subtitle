"""不依赖基础设施的认证领域类型。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType


@dataclass(frozen=True, repr=False)
class SessionCredential:
    cookies: Mapping[str, str] = field(compare=True)

    def __post_init__(self) -> None:
        clean = dict(self.cookies)
        if not clean or any(
            not isinstance(k, str) or not k or not isinstance(v, str) or not v
            for k, v in clean.items()
        ):
            raise ValueError("会话凭据格式无效。")
        object.__setattr__(self, "cookies", MappingProxyType(clean))

    def __repr__(self) -> str:
        return "SessionCredential(<secret>)"


class CredentialState(Enum):
    FOUND = "found"
    MISSING = "missing"
    INVALID = "invalid"


@dataclass(frozen=True)
class CredentialRead:
    state: CredentialState
    credential: SessionCredential | None = field(default=None, repr=False)


class LoginState(Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNSCANNED = "unscanned"
    CONFIRM = "confirm"
    SUCCESS = "success"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class LoginStatus:
    state: LoginState
    display_name: str | None = None


@dataclass(frozen=True, repr=False)
class QrSession:
    content: str
    key: str

    def __repr__(self) -> str:
        return "QrSession(<secret>)"


@dataclass(frozen=True, repr=False)
class PollResult:
    state: LoginState
    credential: SessionCredential | None = None

    def __repr__(self) -> str:
        return f"PollResult(state={self.state!r}, credential=<secret>)"
