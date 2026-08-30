"""Provider configuration, secret storage, and OpenAI-compatible chat adapter."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol, cast
from urllib.parse import urlparse

import httpx
import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from bili_study.storage import AppPaths, StorageError, atomic_write

MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class ProviderError(RuntimeError):
    code = "provider_error"


class ProviderAuthError(ProviderError):
    code = "authentication"


class ProviderQuotaError(ProviderError):
    code = "quota"


class ProviderTimeoutError(ProviderError):
    code = "timeout"


class ProviderNetworkError(ProviderError):
    code = "network"


class ProviderStructureError(ProviderError):
    code = "structure"


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    name: str
    base_url: str
    model: str
    output_language: str = "zh-CN"
    context_budget: int = 12000
    temperature: float = 0.2
    input_price_per_million: Decimal | None = None
    output_price_per_million: Decimal | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ProviderError("Provider base URL 必须是无凭据的 HTTPS 地址。")
        if not self.name.strip() or not self.model.strip() or not self.output_language.strip():
            raise ProviderError("Provider 名称、模型和输出语言不能为空。")
        if not 1000 <= self.context_budget <= 200000 or not 0 <= self.temperature <= 2:
            raise ProviderError("Provider 上下文预算或 temperature 无效。")
        prices = (self.input_price_per_million, self.output_price_per_million)
        if (prices[0] is None) != (prices[1] is None):
            raise ProviderError("Provider 输入和输出单价必须同时设置。")
        if any(value is not None and value < 0 for value in prices):
            raise ProviderError("Provider 单价不能为负数。")
        if prices[0] is not None and (
            self.currency is None
            or len(self.currency) != 3
            or not self.currency.isascii()
            or not self.currency.isalpha()
            or self.currency != self.currency.upper()
        ):
            raise ProviderError("Provider 币种必须是三位大写字母。")
        if prices[0] is None and self.currency is not None:
            raise ProviderError("未设置单价时不能单独设置币种。")


class ProviderConfigStore:
    def __init__(self, paths: AppPaths) -> None:
        self.path = paths.config_dir / "providers.json"

    def _read(self) -> dict[str, dict[str, object]]:
        if not self.path.exists():
            return {}
        try:
            raw = cast(object, json.loads(self.path.read_text(encoding="utf-8")))
            if not isinstance(raw, dict):
                raise ValueError
            result: dict[str, dict[str, object]] = {}
            for name, value in cast(dict[object, object], raw).items():
                if isinstance(name, str) and isinstance(value, dict):
                    result[name] = {
                        str(key): item for key, item in cast(dict[object, object], value).items()
                    }
            return result
        except (OSError, ValueError, TypeError) as exc:
            raise StorageError("Provider 配置损坏。") from exc

    def set(self, config: ProviderConfig) -> None:
        values = self._read()
        serialized = asdict(config)
        for field in ("input_price_per_million", "output_price_per_million"):
            value = serialized[field]
            serialized[field] = str(value) if value is not None else None
        values[config.name] = serialized
        atomic_write(
            self.path, json.dumps(values, ensure_ascii=False, indent=2, sort_keys=True).encode()
        )

    def get(self, name: str) -> ProviderConfig:
        try:
            raw = self._read()[name]
            return ProviderConfig(
                name=str(raw["name"]),
                base_url=str(raw["base_url"]),
                model=str(raw["model"]),
                output_language=str(raw.get("output_language", "zh-CN")),
                context_budget=int(cast(int, raw.get("context_budget", 12000))),
                temperature=float(cast(float, raw.get("temperature", 0.2))),
                input_price_per_million=_optional_decimal(raw.get("input_price_per_million")),
                output_price_per_million=_optional_decimal(raw.get("output_price_per_million")),
                currency=str(raw["currency"]) if raw.get("currency") is not None else None,
            )
        except KeyError as exc:
            raise ProviderError("Provider 配置不存在。") from exc
        except (TypeError, ValueError) as exc:
            raise ProviderError("Provider 配置字段无效。") from exc

    def clear(self, name: str) -> bool:
        values = self._read()
        removed = values.pop(name, None) is not None
        atomic_write(
            self.path, json.dumps(values, ensure_ascii=False, indent=2, sort_keys=True).encode()
        )
        return removed


class ProviderSecretStore:
    ACCOUNT = "api-key"

    @staticmethod
    def service(name: str) -> str:
        return f"bili-study/provider/{name}"

    def set(self, name: str, api_key: str) -> None:
        if not api_key.strip():
            raise ProviderError("API Key 不能为空。")
        try:
            keyring.set_password(self.service(name), self.ACCOUNT, api_key)
        except KeyringError as exc:
            raise ProviderError("无法保存 Provider API Key。") from exc

    def get(self, name: str) -> str:
        try:
            value = keyring.get_password(self.service(name), self.ACCOUNT)
        except KeyringError as exc:
            raise ProviderError("无法读取 Provider API Key。") from exc
        if not value:
            raise ProviderAuthError("Provider API Key 不存在。")
        return value

    def clear(self, name: str) -> bool:
        try:
            if keyring.get_password(self.service(name), self.ACCOUNT) is None:
                return False
            keyring.delete_password(self.service(name), self.ACCOUNT)
            return True
        except PasswordDeleteError:
            return False
        except KeyringError as exc:
            raise ProviderError("无法清除 Provider API Key。") from exc


@dataclass(frozen=True, slots=True)
class ChatUsage:
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True, slots=True)
class ChatResult:
    content: str
    usage: ChatUsage


class ChatPort(Protocol):
    def complete(self, *, system: str, user: str) -> ChatResult: ...


class OpenAIChatAdapter:
    def __init__(
        self,
        config: ProviderConfig,
        api_key: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=httpx.Timeout(60, connect=10))
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OpenAIChatAdapter:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def complete(self, *, system: str, user: str) -> ChatResult:
        endpoint = self.config.base_url.rstrip("/") + "/chat/completions"
        try:
            response = self._client.post(
                endpoint,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self.config.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": self.config.temperature,
                    "response_format": {"type": "json_object"},
                    "stream": False,
                },
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Provider 请求超时。") from exc
        except httpx.HTTPError as exc:
            raise ProviderNetworkError("Provider 网络请求失败。") from exc
        if response.status_code in {401, 403}:
            raise ProviderAuthError("Provider 认证失败。")
        if response.status_code == 429:
            raise ProviderQuotaError("Provider 配额或速率受限。")
        if response.status_code >= 400:
            raise ProviderNetworkError("Provider 返回服务错误。")
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ProviderStructureError("Provider 响应过大。")
        if "application/json" not in response.headers.get("content-type", ""):
            raise ProviderStructureError("Provider 响应类型无效。")
        try:
            payload = cast(dict[str, object], response.json())
            choices = cast(list[object], payload["choices"])
            choice = cast(dict[str, object], choices[0])
            message = cast(dict[str, object], choice["message"])
            content = message["content"]
            if not isinstance(content, str) or not content:
                raise TypeError
            raw_usage = payload.get("usage")
            usage_raw = cast(dict[str, object], raw_usage) if isinstance(raw_usage, dict) else {}
            usage = ChatUsage(
                _optional_int(usage_raw.get("prompt_tokens")),
                _optional_int(usage_raw.get("completion_tokens")),
                _optional_int(usage_raw.get("total_tokens")),
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderStructureError("Provider 响应结构无效。") from exc
        return ChatResult(content, usage)


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ProviderError("Provider 单价格式无效。") from exc
