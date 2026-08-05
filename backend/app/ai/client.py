from __future__ import annotations

from time import perf_counter
from typing import Any

import httpx

from app.ai.types import OllamaGenerateResponse
from app.core.config import settings
from app.core.logger import get_logger

_MAX_BODY_LOG_CHARS = 500


def format_ollama_error(
    exc: BaseException,
    *,
    url: str,
    timeout: float,
) -> str:
    """Build a non-empty diagnostic string for Ollama request failures."""
    parts: list[str] = [f"type={type(exc).__name__}"]

    message = str(exc).strip()
    if message:
        parts.append(f"message={message}")

    request_url = url
    request = _safe_request(exc)
    if request is not None:
        request_url = str(getattr(request, "url", request_url) or request_url)
    parts.append(f"url={request_url}")
    parts.append(f"timeout={timeout}")

    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
        if status_code is not None:
            parts.append(f"status={status_code}")
        body = _safe_response_body(response)
        if body:
            parts.append(f"body={body}")

    cause = exc.__cause__ or exc.__context__
    if cause is not None and cause is not exc:
        cause_message = str(cause).strip() or type(cause).__name__
        parts.append(f"cause={type(cause).__name__}: {cause_message}")

    return " ".join(parts)


def _safe_request(exc: BaseException) -> httpx.Request | None:
    # httpx.RequestError.request raises if the request was never attached.
    request = getattr(exc, "_request", None)
    if isinstance(request, httpx.Request):
        return request
    try:
        maybe_request = getattr(exc, "request", None)
    except RuntimeError:
        return None
    if isinstance(maybe_request, httpx.Request):
        return maybe_request
    return None


def _safe_response_body(response: object) -> str:
    text_getter = getattr(response, "text", None)
    raw = ""
    if callable(text_getter):
        try:
            raw = str(text_getter() or "")
        except Exception:
            raw = ""
    elif isinstance(text_getter, str):
        raw = text_getter

    cleaned = " ".join(raw.split())
    if not cleaned:
        return ""
    if len(cleaned) > _MAX_BODY_LOG_CHARS:
        return f"{cleaned[:_MAX_BODY_LOG_CHARS]}..."
    return cleaned


class OllamaClient:
    """HTTP client for the local Ollama /api/generate endpoint."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        client: httpx.AsyncClient | None = None,
        max_retries: int = 2,
    ) -> None:
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout = timeout if timeout is not None else settings.ollama_timeout
        self.temperature = temperature if temperature is not None else settings.ollama_temperature
        self.max_tokens = max_tokens if max_tokens is not None else settings.ollama_max_tokens
        self._client = client
        self.max_retries = max_retries
        self.logger = get_logger(__name__)

    async def generate(self, prompt: str) -> OllamaGenerateResponse:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        url = f"{self.base_url}/api/generate"
        started = perf_counter()
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._post(url, payload)
                parsed = OllamaGenerateResponse.model_validate(response)
                duration_ms = round((perf_counter() - started) * 1000, 2)
                self.logger.info(
                    (
                        "ollama_generate model=%s prompt_length=%d response_time_ms=%.2f "
                        "token_estimate=%d attempt=%d"
                    ),
                    self.model,
                    len(prompt),
                    duration_ms,
                    self._estimate_tokens(parsed.response),
                    attempt + 1,
                )
                return parsed
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                last_error = exc
                detail = format_ollama_error(exc, url=url, timeout=self.timeout)
                self.logger.warning(
                    "ollama_transient_failure attempt=%d error=%s",
                    attempt + 1,
                    detail,
                )
            except httpx.HTTPStatusError as exc:
                detail = format_ollama_error(exc, url=url, timeout=self.timeout)
                if exc.response.status_code >= 500:
                    last_error = exc
                    self.logger.warning(
                        "ollama_server_error attempt=%d error=%s",
                        attempt + 1,
                        detail,
                    )
                else:
                    self.logger.error(
                        "ollama_client_error attempt=%d error=%s",
                        attempt + 1,
                        detail,
                    )
                    raise

        assert last_error is not None
        raise last_error

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._client is not None:
            response = await self._client.post(url, json=payload, timeout=self.timeout)
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Ollama response must be a JSON object")
        return data

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, len(text.split()))

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
