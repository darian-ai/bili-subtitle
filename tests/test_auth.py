from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import pytest
import respx
from keyring.errors import KeyringError, PasswordDeleteError

from bili_subtitle.application.auth import login
from bili_subtitle.domain.auth import (
    CredentialRead,
    CredentialState,
    LoginState,
    LoginStatus,
    PollResult,
    QrSession,
    SessionCredential,
)
from bili_subtitle.domain.errors import NetworkError, PlatformResponseError
from bili_subtitle.infrastructure.auth import BilibiliAuthAdapter
from bili_subtitle.infrastructure.credentials import (
    CredentialStoreError,
    KeyringCredentialStore,
    deserialize_credential,
    serialize_credential,
)
from bili_subtitle.infrastructure.terminal_qr import render_qr

COOKIE = {"SESSDATA": "fake-session", "bili_jct": "fake-csrf", "DedeUserID": "123"}


@dataclass
class MemoryStore:
    read_value: CredentialRead = field(
        default_factory=lambda: CredentialRead(CredentialState.MISSING)
    )
    saved: SessionCredential | None = None

    def read(self) -> CredentialRead:
        return self.read_value

    def save(self, credential: SessionCredential) -> None:
        self.saved = credential

    def clear(self) -> bool:
        self.saved = None
        return True


class FakeAuth:
    def __init__(self, states: list[PollResult], valid: bool = False) -> None:
        self.states = states
        self.valid = valid
        self.requests = 0

    def check(self, credential: SessionCredential) -> LoginStatus:
        return LoginStatus(LoginState.VALID if self.valid else LoginState.INVALID)

    def request_qr(self) -> QrSession:
        self.requests += 1
        return QrSession("fake-qr-content", "fake-key")

    def poll(self, key: str) -> PollResult:
        return self.states.pop(0)


def test_credential_roundtrip_and_secret_repr() -> None:
    credential = SessionCredential(COOKIE)
    assert deserialize_credential(serialize_credential(credential)) == credential
    assert "fake-session" not in repr(credential)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "[]",
        "{}",
        '{"version":2,"cookies":{}}',
        '{"version":1,"cookies":[]}',
        '{"version":1,"cookies":{"x":1}}',
    ],
)
def test_credential_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValueError, match="凭据格式无效") as caught:
        deserialize_credential(raw)
    if raw:
        assert raw not in str(caught.value)


def test_login_reuses_valid_credential() -> None:
    credential = SessionCredential(COOKIE)
    auth = FakeAuth([], True)
    result = login(
        MemoryStore(CredentialRead(CredentialState.FOUND, credential)),
        auth,
        lambda _: None,
        lambda _: None,
    )
    assert result.state is LoginState.VALID and auth.requests == 0


def test_login_state_sequence_saves_without_leaks() -> None:
    credential = SessionCredential(COOKIE)
    store = MemoryStore()
    messages: list[str] = []
    rendered: list[str] = []
    auth = FakeAuth(
        [
            PollResult(LoginState.UNSCANNED),
            PollResult(LoginState.CONFIRM),
            PollResult(LoginState.SUCCESS, credential),
        ]
    )
    result = login(store, auth, rendered.append, messages.append, wait=lambda _: None)
    assert result.state is LoginState.SUCCESS and store.saved == credential and auth.requests == 1
    assert messages.count("已扫码，请在客户端确认登录。") == 1
    assert "fake-key" not in "".join(messages) and rendered == ["fake-qr-content"]


@pytest.mark.parametrize("state", [LoginState.EXPIRED, LoginState.CANCELLED, LoginState.FAILED])
def test_login_terminal_states_do_not_save(state: LoginState) -> None:
    store = MemoryStore()
    result = login(
        store, FakeAuth([PollResult(state)]), lambda _: None, lambda _: None, wait=lambda _: None
    )
    assert result.state is state and store.saved is None


def test_login_times_out_with_fake_clock() -> None:
    ticks = iter([0.0, 0.0, 2.0])
    result = login(
        MemoryStore(),
        FakeAuth([PollResult(LoginState.UNSCANNED)]),
        lambda _: None,
        lambda _: None,
        timeout=1,
        clock=lambda: next(ticks),
        wait=lambda _: None,
    )
    assert "超时" in result.message


@respx.mock
def test_adapter_check_generate_poll_and_apply() -> None:
    respx.get("https://api.bilibili.com/x/web-interface/nav").mock(
        return_value=httpx.Response(
            200, json={"code": 0, "data": {"isLogin": True, "uname": "用户"}}
        )
    )
    respx.get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate").mock(
        return_value=httpx.Response(
            200, json={"code": 0, "data": {"url": "fake-url", "qrcode_key": "fake-key"}}
        )
    )
    respx.get("https://passport.bilibili.com/x/passport-login/web/qrcode/poll").mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"code": 86101}})
    )
    with httpx.Client() as client:
        adapter = BilibiliAuthAdapter(client)
        assert adapter.check(SessionCredential(COOKIE)).state is LoginState.VALID
        assert adapter.request_qr().key == "fake-key"
        assert adapter.poll("fake-key").state is LoginState.UNSCANNED
        adapter.apply(SessionCredential(COOKIE))
        assert client.cookies["SESSDATA"] == "fake-session"


@pytest.mark.parametrize(
    "code,state",
    [(86090, LoginState.CONFIRM), (86038, LoginState.EXPIRED), (86039, LoginState.CANCELLED)],
)
def test_adapter_poll_states(code: int, state: LoginState) -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"code": 0, "data": {"code": code}})
    )
    with httpx.Client(transport=transport) as client:
        assert BilibiliAuthAdapter(client).poll("k").state is state


def test_adapter_success_extracts_cookies() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 0, "data": {"code": 0}},
            headers=[
                ("set-cookie", "SESSDATA=s; Path=/"),
                ("set-cookie", "bili_jct=c; Path=/"),
                ("set-cookie", "DedeUserID=1; Path=/"),
            ],
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert BilibiliAuthAdapter(client).poll("k").state is LoginState.SUCCESS


@pytest.mark.parametrize(
    "payload", [{}, {"code": 0, "data": {}}, {"code": 0, "data": {"code": 999}}]
)
def test_adapter_rejects_bad_poll(payload: object) -> None:
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as client,
        pytest.raises(PlatformResponseError),
    ):
        BilibiliAuthAdapter(client).poll("k")


def test_adapter_maps_network_error() -> None:
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(httpx.ConnectError("secret", request=request))
            )
        ) as client,
        pytest.raises(NetworkError, match="认证网络访问失败"),
    ):
        BilibiliAuthAdapter(client).request_qr()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"code": 1}),
    ],
)
def test_adapter_rejects_http_and_payload_errors(response: httpx.Response) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: response)) as client,
        pytest.raises((NetworkError, PlatformResponseError)),
    ):
        BilibiliAuthAdapter(client).request_qr()


def test_keyring_store_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    values: dict[tuple[str, str], str] = {}

    def get(service: str, account: str) -> str | None:
        return values.get((service, account))

    def set_value(service: str, account: str, value: str) -> None:
        values[(service, account)] = value

    def delete(service: str, account: str) -> None:
        values.pop((service, account))

    monkeypatch.setattr("keyring.get_password", get)
    monkeypatch.setattr("keyring.set_password", set_value)
    monkeypatch.setattr("keyring.delete_password", delete)
    store = KeyringCredentialStore()
    assert store.read().state is CredentialState.MISSING
    assert not store.clear()
    store.save(SessionCredential(COOKIE))
    assert store.read().state is CredentialState.FOUND
    assert store.clear()


def test_keyring_error_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_: object) -> str:
        raise KeyringError("backend detail")

    monkeypatch.setattr("keyring.get_password", fail)
    with pytest.raises(CredentialStoreError) as caught:
        KeyringCredentialStore().read()
    assert "backend detail" not in str(caught.value)


def test_keyring_delete_failure_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def get(service: str, account: str) -> str:
        return "present"

    monkeypatch.setattr("keyring.get_password", get)

    def fail(service: str, account: str) -> None:
        raise PasswordDeleteError("detail")

    monkeypatch.setattr("keyring.delete_password", fail)
    with pytest.raises(CredentialStoreError, match="清除"):
        KeyringCredentialStore().clear()


def test_terminal_qr_does_not_print_raw_content(capsys: pytest.CaptureFixture[str]) -> None:
    render_qr("unique-raw-qr-secret")
    assert "unique-raw-qr-secret" not in capsys.readouterr().out
