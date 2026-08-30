from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import httpx
import keyring
import pytest
import respx
from keyring.errors import KeyringError

from bili_study.provider import (
    OpenAIChatAdapter,
    ProviderAuthError,
    ProviderConfig,
    ProviderConfigStore,
    ProviderError,
    ProviderNetworkError,
    ProviderQuotaError,
    ProviderSecretStore,
    ProviderStructureError,
    ProviderTimeoutError,
)
from bili_study.storage import AppPaths, StorageError


def config() -> ProviderConfig:
    return ProviderConfig("test", "https://model.example/v1", "chat-model", context_budget=1000)


def test_provider_config_is_non_secret_and_validated(tmp_path: Path) -> None:
    store = ProviderConfigStore(AppPaths(tmp_path, tmp_path / "state"))
    store.set(config())
    assert store.get("test") == config()
    assert "api" not in store.path.read_text(encoding="utf-8").casefold()
    assert store.clear("test")
    with pytest.raises(ProviderError, match="不存在"):
        store.get("test")
    with pytest.raises(ProviderError, match="HTTPS"):
        ProviderConfig("bad", "http://example.com", "model")
    with pytest.raises(ProviderError, match="不能为空"):
        ProviderConfig("", "https://example.com", "model")
    with pytest.raises(ProviderError, match="预算"):
        ProviderConfig("bad", "https://example.com", "model", context_budget=10)
    store.path.write_text("[]", encoding="utf-8")
    with pytest.raises(StorageError, match="配置损坏"):
        store.get("test")
    store.path.write_text(
        json.dumps(
            {
                "test": {
                    "name": "test",
                    "base_url": "https://example.com",
                    "model": "m",
                    "context_budget": "invalid",
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ProviderError, match="字段无效"):
        store.get("test")


def test_provider_prices_are_decimal_optional_and_backward_compatible(tmp_path: Path) -> None:
    store = ProviderConfigStore(AppPaths(tmp_path, tmp_path / "state"))
    priced = ProviderConfig(
        "priced",
        "https://example.com/v1",
        "model",
        input_price_per_million=Decimal("0.125"),
        output_price_per_million=Decimal("1.75"),
        currency="CNY",
    )
    store.set(priced)
    assert store.get("priced") == priced
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    assert raw["priced"]["input_price_per_million"] == "0.125"
    with pytest.raises(ProviderError, match="同时"):
        ProviderConfig(
            "bad",
            "https://example.com/v1",
            "model",
            input_price_per_million=Decimal("1"),
        )
    with pytest.raises(ProviderError, match="负数"):
        ProviderConfig(
            "bad",
            "https://example.com/v1",
            "model",
            input_price_per_million=Decimal("-1"),
            output_price_per_million=Decimal("1"),
            currency="USD",
        )
    with pytest.raises(ProviderError, match="三位大写"):
        ProviderConfig(
            "bad",
            "https://example.com/v1",
            "model",
            input_price_per_million=Decimal("1"),
            output_price_per_million=Decimal("1"),
            currency="usd",
        )


def test_provider_secret_uses_separate_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    values: dict[tuple[str, str], str] = {}

    def set_password(service: str, account: str, value: str) -> None:
        values[(service, account)] = value

    def get_password(service: str, account: str) -> str | None:
        return values.get((service, account))

    def delete_password(service: str, account: str) -> None:
        values.pop((service, account))

    monkeypatch.setattr("keyring.set_password", set_password)
    monkeypatch.setattr("keyring.get_password", get_password)
    monkeypatch.setattr("keyring.delete_password", delete_password)
    store = ProviderSecretStore()
    store.set("test", "secret-key")
    assert store.get("test") == "secret-key"
    assert ("bili-study/provider/test", "api-key") in values
    assert store.clear("test")
    with pytest.raises(ProviderAuthError):
        store.get("test")


def test_provider_secret_backend_errors_are_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise KeyringError("backend-secret")

    monkeypatch.setattr(keyring, "set_password", fail)
    with pytest.raises(ProviderError, match="无法保存") as caught:
        ProviderSecretStore().set("test", "key")
    assert "backend-secret" not in str(caught.value)
    with pytest.raises(ProviderError, match="不能为空"):
        ProviderSecretStore().set("test", " ")


@respx.mock
def test_openai_adapter_success_and_usage() -> None:
    respx.post("https://model.example/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "choices": [{"message": {"content": '{"ok":true}'}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        )
    )
    with OpenAIChatAdapter(config(), "canary-key") as adapter:
        result = adapter.complete(system="system", user="user")
    assert result.content == '{"ok":true}'
    assert result.usage.total_tokens == 5
    request = respx.calls.last.request
    assert request.headers["authorization"] == "Bearer canary-key"
    assert json.loads(request.content)["stream"] is False


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, ProviderAuthError), (429, ProviderQuotaError), (500, ProviderNetworkError)],
)
@respx.mock
def test_openai_adapter_classifies_http_without_leaking_body(
    status: int, error: type[Exception]
) -> None:
    secret = "remote-secret-body"
    respx.post("https://model.example/v1/chat/completions").mock(
        return_value=httpx.Response(status, text=secret)
    )
    with OpenAIChatAdapter(config(), "key") as adapter, pytest.raises(error) as caught:
        adapter.complete(system="s", user="u")
    assert secret not in str(caught.value)


@respx.mock
def test_openai_adapter_rejects_non_json_and_bad_schema() -> None:
    route = respx.post("https://model.example/v1/chat/completions")
    route.mock(return_value=httpx.Response(200, text="html", headers={"content-type": "text/html"}))
    with OpenAIChatAdapter(config(), "key") as adapter, pytest.raises(ProviderStructureError):
        adapter.complete(system="s", user="u")


def test_openai_adapter_classifies_transport_timeout_and_network() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret", request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(timeout)) as client,
        OpenAIChatAdapter(config(), "key", client=client) as adapter,
        pytest.raises(ProviderTimeoutError),
    ):
        adapter.complete(system="s", user="u")

    def network(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret", request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(network)) as client,
        OpenAIChatAdapter(config(), "key", client=client) as adapter,
        pytest.raises(ProviderNetworkError),
    ):
        adapter.complete(system="s", user="u")


@respx.mock
def test_openai_adapter_rejects_oversized_and_invalid_json_schema() -> None:
    route = respx.post("https://model.example/v1/chat/completions")
    route.mock(
        return_value=httpx.Response(
            200, content=b"x" * (2 * 1024 * 1024 + 1), headers={"content-type": "application/json"}
        )
    )
    with OpenAIChatAdapter(config(), "key") as adapter, pytest.raises(ProviderStructureError):
        adapter.complete(system="s", user="u")
    route.mock(
        return_value=httpx.Response(
            200, json={"choices": []}, headers={"content-type": "application/json"}
        )
    )
    with OpenAIChatAdapter(config(), "key") as adapter, pytest.raises(ProviderStructureError):
        adapter.complete(system="s", user="u")
