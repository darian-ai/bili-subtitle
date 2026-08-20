"""Bilibili Web 二维码认证适配器。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import httpx

from bili_subtitle.domain.auth import (
    LoginState,
    LoginStatus,
    PollResult,
    QrSession,
    SessionCredential,
)
from bili_subtitle.domain.errors import NetworkError, PlatformResponseError

_NAV = "https://api.bilibili.com/x/web-interface/nav"
_GENERATE = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
_POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
_REQUIRED_COOKIES = ("SESSDATA", "bili_jct", "DedeUserID")


class BilibiliAuthAdapter:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def check(self, credential: SessionCredential) -> LoginStatus:
        response = self._get(_NAV, cookies=dict(credential.cookies))
        payload = _payload(response)
        if payload.get("code") != 0:
            return LoginStatus(LoginState.INVALID)
        data = payload.get("data")
        if not isinstance(data, Mapping) or not isinstance(data.get("isLogin"), bool):
            raise PlatformResponseError("平台登录状态响应结构异常。")
        if not data["isLogin"]:
            return LoginStatus(LoginState.INVALID)
        name = data.get("uname")
        return LoginStatus(LoginState.VALID, name if isinstance(name, str) else None)

    def request_qr(self) -> QrSession:
        payload = _payload(self._get(_GENERATE))
        if payload.get("code") != 0:
            raise PlatformResponseError("平台拒绝申请登录二维码。")
        data = payload.get("data")
        if (
            not isinstance(data, Mapping)
            or not isinstance(data.get("url"), str)
            or not isinstance(data.get("qrcode_key"), str)
        ):
            raise PlatformResponseError("平台二维码响应结构异常。")
        return QrSession(cast(str, data["url"]), cast(str, data["qrcode_key"]))

    def poll(self, key: str) -> PollResult:
        response = self._get(_POLL, params={"qrcode_key": key})
        payload = _payload(response)
        if payload.get("code") != 0:
            raise PlatformResponseError("平台拒绝二维码状态请求。")
        data = payload.get("data")
        if not isinstance(data, Mapping) or not isinstance(data.get("code"), int):
            raise PlatformResponseError("平台二维码状态响应结构异常。")
        code = data["code"]
        states = {
            86101: LoginState.UNSCANNED,
            86090: LoginState.CONFIRM,
            86038: LoginState.EXPIRED,
            86039: LoginState.CANCELLED,
        }
        if code in states:
            return PollResult(states[cast(int, code)])
        if code != 0:
            raise PlatformResponseError("平台返回未知二维码状态。")
        cookies = {name: response.cookies.get(name) for name in _REQUIRED_COOKIES}
        if any(not value for value in cookies.values()):
            raise PlatformResponseError("登录成功响应缺少必要会话信息。")
        return PollResult(LoginState.SUCCESS, SessionCredential(cast(dict[str, str], cookies)))

    def apply(self, credential: SessionCredential) -> None:
        self._client.cookies.update(dict(credential.cookies))

    def _get(self, url: str, **kwargs: object) -> httpx.Response:
        try:
            response = self._client.get(url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise NetworkError("认证网络访问失败。") from exc


def _payload(response: httpx.Response) -> Mapping[str, object]:
    try:
        payload = cast(object, response.json())
    except ValueError as exc:
        raise PlatformResponseError("平台认证响应不是有效 JSON。") from exc
    if not isinstance(payload, Mapping):
        raise PlatformResponseError("平台认证响应结构异常。")
    return cast(Mapping[str, object], payload)
