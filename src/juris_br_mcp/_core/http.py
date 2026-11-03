"""Cliente HTTP async com retry, rate limiting e cache curto."""

from __future__ import annotations

import asyncio
import json as _json
from collections.abc import Callable
from typing import Any

import httpx
from aiolimiter import AsyncLimiter
from cachetools import TTLCache
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from .logging import get_logger

__all__ = ["HTTPClient"]

logger = get_logger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException))


class HTTPClient:
    """Cliente JSON async para serviços externos do Juris BR MCP."""

    def __init__(
        self,
        base_url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        cache_ttl: int = 300,
        rate_limit_per_second: int = 5,
    ) -> None:
        self._base_url = base_url
        self._headers = headers or {}
        self._timeout = timeout
        self._max_retries = max_retries
        self._cache: TTLCache[str, Any] = TTLCache(maxsize=512, ttl=cache_ttl)
        self._rate_limit = rate_limit_per_second
        self._limiter = AsyncLimiter(rate_limit_per_second, 1.0)
        self._client: httpx.AsyncClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def __aenter__(self) -> HTTPClient:
        self._ensure_client()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client:
            try:
                await self._client.aclose()
            except RuntimeError:
                pass  # loop original ja encerrado
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Abre (ou reabre) a conexão de forma preguiçosa.

        O cliente é reaproveitado entre chamadas para que cache, rate limit e
        conexões keep-alive funcionem de fato. Se o event loop mudou (ex.: um
        script que chama asyncio.run várias vezes), recria cliente e limiter,
        pois ambos ficam presos ao loop em que foram usados.
        """
        loop = asyncio.get_running_loop()
        if self._client is None or self._loop is not loop or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._headers,
                timeout=self._timeout,
            )
            self._limiter = AsyncLimiter(self._rate_limit, 1.0)
            self._loop = loop
        return self._client

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET com cache TTL e retry automático."""
        cache_key = f"GET:{path}:{_json.dumps(params, sort_keys=True, default=str)}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = await self._request("GET", path, params=params)
        self._cache[cache_key] = result
        return result

    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        *,
        use_cache: bool = False,
        cache_valido: Callable[[Any], bool] | None = None,
    ) -> Any:
        """POST com retry. Cache TTL opcional (buscas idempotentes, ex.: Elasticsearch).

        cache_valido: se informado, só guarda no cache respostas aprovadas por ele
        (ex.: não cachear resultado parcial do Elasticsearch).
        """
        cache_key = f"POST:{path}:{_json.dumps(json, sort_keys=True, default=str)}"
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]
        result = await self._request("POST", path, json=json)
        if use_cache and (cache_valido is None or cache_valido(result)):
            self._cache[cache_key] = result
        return result

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        client = self._ensure_client()

        async with self._limiter:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._max_retries),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
                retry=retry_if_exception(_is_retryable),
                reraise=True,
            ):
                with attempt:
                    response = await client.request(method, path, **kwargs)
                    response.raise_for_status()
                    logger.debug(
                        "http_request_ok",
                        method=method,
                        path=path,
                        status=response.status_code,
                    )
                    return response.json()
