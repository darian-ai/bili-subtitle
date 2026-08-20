"""认证命令与有界二维码登录编排。"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from bili_subtitle.domain.auth import (
    CredentialRead,
    CredentialState,
    LoginState,
    LoginStatus,
    PollResult,
    QrSession,
    SessionCredential,
)
from bili_subtitle.domain.errors import NetworkError


class Store(Protocol):
    def read(self) -> CredentialRead: ...
    def save(self, credential: SessionCredential) -> None: ...
    def clear(self) -> bool: ...


class AuthPort(Protocol):
    def check(self, credential: SessionCredential) -> LoginStatus: ...
    def request_qr(self) -> QrSession: ...
    def poll(self, key: str) -> PollResult: ...


@dataclass(frozen=True)
class AuthOutcome:
    state: LoginState
    message: str
    credential: SessionCredential | None = None


def login(
    store: Store,
    auth: AuthPort,
    render: Callable[[str], None],
    notify: Callable[[str], None],
    *,
    interval: float = 2,
    timeout: float = 180,
    clock: Callable[[], float] = time.monotonic,
    wait: Callable[[float], None] = time.sleep,
    retries: int = 2,
) -> AuthOutcome:
    saved = store.read()
    if saved.state is CredentialState.FOUND and saved.credential is not None:
        status = auth.check(saved.credential)
        if status.state is LoginState.VALID:
            return AuthOutcome(LoginState.VALID, "已经登录。", saved.credential)
    session = auth.request_qr()
    render(session.content)
    notify("请使用哔哩哔哩客户端扫描二维码。")
    started = clock()
    last: LoginState | None = None
    errors = 0
    while clock() - started < timeout:
        try:
            result = auth.poll(session.key)
            errors = 0
        except NetworkError:
            errors += 1
            if errors > retries:
                raise
            wait(interval)
            continue
        if result.state is LoginState.SUCCESS and result.credential is not None:
            store.save(result.credential)
            return AuthOutcome(LoginState.SUCCESS, "登录成功。", result.credential)
        if result.state in {LoginState.EXPIRED, LoginState.CANCELLED, LoginState.FAILED}:
            labels = {
                LoginState.EXPIRED: "二维码已过期。",
                LoginState.CANCELLED: "登录已取消。",
                LoginState.FAILED: "登录失败。",
            }
            return AuthOutcome(result.state, labels[result.state])
        if result.state != last:
            if result.state is LoginState.CONFIRM:
                notify("已扫码，请在客户端确认登录。")
            last = result.state
        wait(interval)
    return AuthOutcome(LoginState.FAILED, "登录等待超时。")
