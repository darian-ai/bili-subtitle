"""Windows Credential Manager 的 keyring 适配器。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from bili_subtitle.domain.auth import CredentialRead, CredentialState, SessionCredential

SERVICE_NAME = "bili-subtitle"
DEFAULT_ACCOUNT = "default"


class CredentialStoreError(Exception):
    """凭据后端操作失败，消息不包含秘密。"""


def serialize_credential(value: SessionCredential) -> str:
    return json.dumps(
        {"version": 1, "cookies": dict(value.cookies)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def deserialize_credential(raw: str) -> SessionCredential:
    try:
        value = cast(object, json.loads(raw))
    except (ValueError, TypeError) as exc:
        raise ValueError("已保存凭据格式无效。") from exc
    if not isinstance(value, Mapping):
        raise ValueError("已保存凭据格式无效。")
    obj = cast(Mapping[object, object], value)
    if set(obj) != {"version", "cookies"} or obj.get("version") != 1:
        raise ValueError("已保存凭据格式无效。")
    cookies = obj.get("cookies")
    if not isinstance(cookies, Mapping):
        raise ValueError("已保存凭据格式无效。")
    cookie_obj = cast(Mapping[object, object], cookies)
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in cookie_obj.items()):
        raise ValueError("已保存凭据格式无效。")
    try:
        return SessionCredential(cast(Mapping[str, str], cookie_obj))
    except ValueError as exc:
        raise ValueError("已保存凭据格式无效。") from exc


class KeyringCredentialStore:
    def read(self) -> CredentialRead:
        try:
            raw = keyring.get_password(SERVICE_NAME, DEFAULT_ACCOUNT)
        except KeyringError as exc:
            raise CredentialStoreError("读取 Credential Manager 失败。") from exc
        if raw is None:
            return CredentialRead(CredentialState.MISSING)
        try:
            return CredentialRead(CredentialState.FOUND, deserialize_credential(raw))
        except ValueError:
            return CredentialRead(CredentialState.INVALID)

    def save(self, credential: SessionCredential) -> None:
        try:
            keyring.set_password(SERVICE_NAME, DEFAULT_ACCOUNT, serialize_credential(credential))
        except KeyringError as exc:
            raise CredentialStoreError("保存 Credential Manager 凭据失败。") from exc

    def clear(self) -> bool:
        try:
            if keyring.get_password(SERVICE_NAME, DEFAULT_ACCOUNT) is None:
                return False
            keyring.delete_password(SERVICE_NAME, DEFAULT_ACCOUNT)
            return True
        except PasswordDeleteError:
            return False
        except KeyringError as exc:
            raise CredentialStoreError("清除 Credential Manager 凭据失败。") from exc
